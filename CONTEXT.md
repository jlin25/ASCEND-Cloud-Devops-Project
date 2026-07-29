# ASCEND — Project Context

A cloud media-processing platform. Users submit media jobs (transcode, trim,
extract-audio) through a web UI; jobs are queued, processed asynchronously by a
worker, and results are stored and made available for download.

This file is a high-level map of the system. For setup commands see the
per-component notes below.

---

## Architecture

```
React/Vite frontend  ──HTTP──▶  FastAPI backend  ──insert──▶  Supabase (Postgres)
   (port 5173)                    (port 8000)                    "jobs" / "users"
                                       │                                 ▲
                                       └──send──▶  AWS SQS queue  ──poll──▶  worker.py
                                                        │                      │
                                                   AWS S3 (input/output objects)
                                                                   updates job status + output_file_url
```

- **Frontend** submits jobs and (eventually) displays status/results.
- **Backend** (FastAPI) validates requests, writes a row to the `jobs` table,
  and enqueues the job on SQS. It does **not** process jobs itself.
- **Worker** (`worker.py`) long-polls SQS, runs the job (downloads input from S3,
  runs `ffmpeg`, uploads output to S3), and updates the DB row (`status`,
  `progress`, `output_file_url`). The `video_quality` job type is **fully
  implemented**; `transcode` / `trim` / `extract_audio` are still stubbed (`pass`).
- **Infra** (Terraform) provisions the SQS queue, a dead-letter queue, and IAM
  credentials.

---

## Components

### Frontend — `frontend/`
- **Stack:** React 19 + TypeScript + Vite 8, `react-router-dom` v7.
- **Run:** `cd frontend && npm install && npm run dev` → http://localhost:5173
- **Structure:**
  - `src/App.tsx` — router; routes: `/` (Home), `/login`, `/dashboard`,
    `/marketplace`, `/jobs`, `/tutorial`. (Sidebar links to `/pricing`,
    `/settings` have **no route** yet → blank page.)
  - `src/pages/LoginPage.tsx` — **wired.** Register/login → stores JWT +
    username in `localStorage` → navigates to `/dashboard`.
  - `src/pages/DashboardPage.tsx` — **wired, the real app.** Upload a file →
    `api.upload` → `api.createTask` → polls `api.listTasks` (Recent Jobs) →
    `api.getTaskResult` opens the output. Only the **Image Resize/Upscale**
    task is connected (`TASK_TYPE`); other dropdown options `alert(...)`.
  - `src/pages/HomePage.tsx` — landing page; the search box submit is still a
    placeholder `alert()` (`HomePage.tsx:24`). Real entry is "Get Started" → `/login`.
  - `src/pages/JobsPage.tsx`, `MarketplacePage.tsx`, `TutorialPage.tsx` — **static
    mockups** (no API calls). Real job list is the Dashboard's Recent Jobs panel.
  - `src/api.ts` — typed API client (`api.*`, `ApiError`, `VITE_API_BASE`);
    attaches `Bearer` token from `localStorage`.
  - `src/api-types.ts` — types generated from the backend OpenAPI schema
    (`npm run gen:api`, backend must be running).
- **Integration status:** login + image-resize flow are wired end-to-end.
  Remaining task types and the Jobs/Marketplace pages are mockups. See *Next steps*.

### Backend — `backend/`
- **Stack:** FastAPI + Uvicorn, Pydantic v2, Supabase (Postgres) client, boto3 (SQS + S3).
- **Run:** `cd backend && uvicorn main:app --reload` → http://localhost:8000
- **CORS:** already allows `http://localhost:5173`.
- **Endpoints:**
  - `GET /` and `GET /api/message` — health checks (no external deps).
  - `POST /tasks` — submit a job (`JobRequest`); writes to DB + enqueues on SQS.
    Returns `{ message, task_id }`. **Needs Supabase + SQS configured.**
  - `POST /upload` — upload a file to S3; returns `{ file_key }` (use as `file_url`).
  - `GET /tasks` — list the caller's jobs.
  - `GET /tasks/{id}` — fetch one job.
  - `GET /tasks/{id}/result` — presigned output URL (404 until job done).
  - `DELETE /tasks/{id}` — delete a job.
  - `POST /auth/register|login|logout` — **implemented** (JWT). All `/tasks` and
    `/upload` routes require a `Bearer` token (`get_current_user`).
- **Auth signing:** JWTs are signed with the `SECRET_KEY` env var (self-generated).
- **Job types** (`jobs/jobs.py`) — Pydantic discriminated union on `type`:
  - `image_resize`: `file_url`, `width`, `height` — **implemented; the type the
    frontend Dashboard actually submits.**
  - `video_quality`: `file_url`, `resolution` (720p/1080p/4k) — **implemented.**
  - `transcode`: `file_url`, `format` (mp4/webm/mov), `resolution` — stub.
  - `extract_audio`: `file_url`, `format` (mp3/wav/aac) — stub.
  - `trim`: `file_url`, `start_seconds`, `end_seconds` — stub.
- **S3** (`s3_client.py`, `S3Client`): `upload_stream` / `download_stream` /
  `get_output_url` (24h presigned) / `delete_object`. `file_url` values are S3 keys.
- **Worker** (`worker.py`): polls SQS, sets `processing` → `done` (with
  `progress: 100` + `output_key`) / `failed`. Both handlers use `ffmpeg`:
  `process_image_resize` (`scale=width:height`) and `process_video_quality`
  (`scale=-2:height`, libx264/aac → `processed/`). `transcode`/`trim`/
  `extract_audio` are still `pass` stubs (`worker.py:120`).
- **Tests** (`backend/tests/`): `test_jobs.py`, `test_tasks_api.py`,
  `test_worker.py`; run with `pytest` (config in `pytest.ini`, fixtures in `conftest.py`).

### Database — `backend/db/schema.sql` (Supabase / Postgres)
- `jobs`: `id`, `status` (enum: pending/processing/done/failed), `input_file_url`,
  `output_file_url`, `job_type`, `created_at`, `retry_count`, `progress`, `user_id`.
- `users`: `id`, `username` (unique), `hashed_password`, `created_at`.
- Note the column mapping: request `type`→`job_type`, `file_url`→`input_file_url`.

### Infrastructure — `infra/` (Terraform / AWS)
- **Region: `us-east-2`** (pinned in `terraform.tfvars`). Provisions: S3 bucket
  (`ascend-cloud-uploads`), SQS queue + DLQ, IAM user (local dev) + IAM instance
  role (EC2), SSM Parameter Store config, and an **EC2 worker** that runs
  `worker.py` as a systemd service.
- **Worker bootstrap** (`user_data.sh.tftpl`): installs **Python 3.11** (AL2023's
  default 3.9 is too old for the pinned deps) + static ffmpeg, pulls config from
  SSM, clones the repo, runs the worker. Needs `TF_VAR_worker_repo_url` /
  `worker_branch` set to actually deploy code.
- **Workflow:** `./infra/init.sh` (apply + write `backend/.env`) /
  `./infra/init.sh destroy`. Full step-by-step in **`RUNBOOK.md`**.
- ⚠️ `init.sh` appends to `backend/.env`; re-runs duplicate keys — dedupe after.

---

## Environment / configuration

`backend/.env` (see `.env.example` for the Supabase half):
```
# AWS / SQS / S3 (written by init.sh from terraform output)
SQS_QUEUE_URL, SQS_DLQ_URL, S3_BUCKET_NAME, AWS_REGION,
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
# Supabase (from project settings) — add manually
DB_URL, DB_SERVICE_KEY
# App JWT signing secret — self-generated, add manually
SECRET_KEY
```
`SECRET_KEY`: any random string (`python3 -c "import secrets;print(secrets.token_hex(32))"`).
Frontend reads `VITE_API_BASE` (defaults to `http://localhost:8000` — no `.env` needed for local dev).

**Dependency tiers when running locally:**
- Health endpoints (`/`, `/api/message`) — no external services.
- `GET /tasks`, `GET /tasks/{id}` — need Supabase.
- `POST /tasks` — needs Supabase **and** AWS SQS.
- Full job completion — also needs the worker running.

---

## Current status & next steps

From `next_steps.md` and code review:
- [ ] Wire the remaining Dashboard task types (only `image_resize` is connected;
      others `alert(...)`). Needs matching worker handlers too.
- [ ] Make the `/jobs` and `/marketplace` pages real (currently static mockups) —
      `/jobs` should use `api.listTasks`.
- [ ] Add routes for the `/pricing` and `/settings` sidebar links (blank today).
- [ ] Implement the remaining `worker.py` job types (`transcode`, `trim`,
      `extract_audio`) — reuse the `process_image_resize`/`video_quality` pattern.
- [ ] Infra polish: private-repo deploy auth + CloudWatch log shipping.
- [x] Backend auth (JWT register/login/logout; routes token-guarded).
- [x] File upload endpoint (`POST /upload` → S3 key).
- [x] Typed frontend API client + `LoginPage`/`DashboardPage` wired.
- [x] **`image_resize` wired end-to-end** (Dashboard → upload → job → result).
- [x] `video_quality` implemented in the worker (not yet exposed in the UI).
- [x] EC2 worker provisioning (Terraform + systemd + Python 3.11 + static ffmpeg).

**Testable end-to-end today** (see `RUNBOOK.md`): via the UI — register at
`/login` → Dashboard → "Image Resize/Upscale" → upload an image → job processes →
view result. Or via curl against the backend directly.

**Suggested next task:** expose `video_quality` in the Dashboard (worker handler
already exists) so both a photo and a video path work end-to-end, then make the
`/jobs` page real using `api.listTasks`.
