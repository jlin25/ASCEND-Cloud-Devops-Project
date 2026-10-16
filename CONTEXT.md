# ASCEND — Project Context

A cloud media-processing platform. Users upload an image or video through a web
UI and pick a task (resize, deblur, format conversion); jobs are queued,
processed asynchronously by a worker, and results are stored and made available
for download.

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
  runs `ffmpeg` or OpenCV, uploads output to S3), and updates the DB row
  (`status`, `progress`, `output_key`). Five job types have real handlers:
  `image_resize`, `deblur`, `format_converter`, `trim`, `video_quality`.
  `transcode` / `extract_audio` are `pass` stubs and `transcribe` has no handler
  at all — see *Job types* below.
- **Infra** (Terraform) provisions the SQS queue, a dead-letter queue, and IAM
  credentials.

---

## Components

### Frontend — `frontend/`
- **Stack:** React 19 + TypeScript + Vite 8, `react-router-dom` v7.
- **Run:** `cd frontend && npm install && npm run dev` → http://localhost:5173
- **Structure:**
  - `src/App.tsx` — router; routes: `/` (Home), `/login`, `/dashboard`,
    `/marketplace` (Task Catalog), `/jobs`, `/tutorial`, `*` (NotFound).
  - `src/tasks.ts` — **the task registry: single source of truth.** Task ids are
    the backend's `type` discriminators, derived from the generated API types so
    a server-side rename breaks `tsc` rather than failing as a runtime 422. Also
    owns the format-family rules and the job-status label/badge mapping. The
    Dashboard picker, Task Catalog, Home cards and Tutorial all read from it —
    add a task here and it appears everywhere.
  - `src/useJobs.ts` — shared `useJobs()` hook (`api.listTasks`, newest first)
    plus `openJobResult` / `deleteJob`. Used by both Dashboard and Jobs.
  - `src/components/AppLayout.tsx` — nav + sidebar for the signed-in pages
    (Dashboard, Task Catalog, My Jobs) and the shared CSS primitives
    (`.dash-card`, `.dash-table`, `.badge-*`, `.dash-notice`).
  - `src/pages/LoginPage.tsx` — **wired.** Register/login via `api.ts` → stores
    JWT + username in `localStorage` → navigates to `/dashboard`.
  - `src/pages/DashboardPage.tsx` — **wired, the real app.** Pick a task →
    upload → `api.upload` → `api.createTask` → `useJobs` (Recent Jobs, latest 5)
    → `api.getTaskResult` opens the output. Accepts `?task=<id>` to preselect.
  - `src/pages/JobsPage.tsx` — **wired.** Full history with status filters,
    download, and delete.
  - `src/pages/MarketplacePage.tsx` — Task Catalog; cards deep-link to
    `/dashboard?task=<id>`.
  - `src/pages/HomePage.tsx` — landing page. Entry is "Get Started" → `/login`.
  - `src/pages/TutorialPage.tsx` — static walkthrough of the real flow.
  - `src/api.ts` — typed API client (`api.*`, `ApiError`, `VITE_API_BASE`);
    attaches `Bearer` token from `localStorage`.
  - `src/api-types.ts` — types generated from the backend OpenAPI schema
    (`npm run gen:api`, backend must be running).
- **Integration status:** every task offered in the UI works end-to-end. The UI
  deliberately exposes only 3 of the 5 implemented job types — see *Next steps*.
- **No route guards:** `/dashboard`, `/jobs`, `/marketplace` render for signed-out
  users; the API calls just 401. A `<RequireAuth>` wrapper is still to do.

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
- **Job types** (`jobs/jobs.py`) — Pydantic discriminated union on `type`.
  "In UI" means the frontend can submit it (`frontend/src/tasks.ts`):
  - `image_resize`: `file_url`, `width`, `height` — **implemented, in UI.**
  - `deblur`: `file_url` — **implemented, in UI** (OpenCV, not ffmpeg).
  - `format_converter`: `file_url`, `input_format`, `output_format` —
    **implemented, in UI.** A `model_validator` rejects video↔image conversion
    and same-format conversion; the UI derives `input_format` from the uploaded
    filename and only offers valid targets, so those errors are unreachable.
  - `video_quality`: `file_url`, `resolution` (720p/1080p/4k) — **implemented,
    not in UI.**
  - `trim`: `file_url`, `start_seconds`, `end_seconds` — **implemented, not in
    UI.**
  - `transcode`: `file_url`, `format` (mp4/webm/mov), `resolution` — ⚠️ `pass`
    stub: marks the job `done` with `output_key = None` (silent success).
  - `extract_audio`: `file_url`, `format` (mp3/wav/aac) — ⚠️ same `pass` stub.
  - `transcribe`: `file_url` — ⚠️ schema and IAM permissions only. **No worker
    handler**, so it falls through to `assert_never` and the message is redelivered
    until it lands in the DLQ. Do not expose in the UI.
- **S3** (`s3_client.py`, `S3Client`): `upload_stream` / `download_stream` /
  `get_output_url` (24h presigned) / `delete_object`. `file_url` values are S3 keys.
- **Worker** (`worker.py`): polls SQS, sets `processing` → `done` (with
  `progress: 100` + `output_key`) / `failed`. Handlers: `process_image_resize`
  (ffmpeg `scale=width:height`), `process_video_quality` (ffmpeg `scale=-2:height`,
  libx264/aac → `processed/`), `process_trim` (ffmpeg `-ss`/`-to`),
  `convert_format` (ffmpeg), `process_image_deblur` (OpenCV + a model pulled from
  Hugging Face). Dispatch is a `match` on the job class in `handle()`.
  - ⚠️ On a handler exception the row is marked `failed` but the SQS message is
    **not** deleted, so it is redelivered until it reaches the DLQ.
  - Local runs need `opencv-python` (`import cv2`) — not installed in
    `backend/.venv_run`, so the worker only runs on the provisioned EC2 instance
    unless you install it.
- **Tests** (`backend/tests/`): `test_jobs.py`, `test_tasks_api.py`,
  `test_worker.py`; run with `pytest` (config in `pytest.ini`, fixtures in `conftest.py`).

### Database — `backend/db/schema.sql` (Supabase / Postgres)
- `jobs`: `id`, `status` (enum: pending/processing/done/failed), `input_key`,
  `output_key`, `job_type`, `created_at`, `retry_count`, `progress`, `user_id`.
- `users`: `id`, `username` (unique), `hashed_password`, `created_at`.
- Note the column mapping: request `type`→`job_type`, `file_url`→`input_key`
  (the values are S3 keys, not URLs).
- `retry_count` exists but is never written by the app.

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

- [ ] **Expose `video_quality` and `trim` in the UI.** Both have working worker
      handlers but are not in `frontend/src/tasks.ts`. Add an entry to `TASKS`
      (plus a `TaskParam` for the resolution picker / start+end seconds) and they
      appear in the Dashboard picker, Task Catalog, Home and Tutorial at once.
- [ ] Add route guards — `/dashboard`, `/jobs`, `/marketplace` currently render
      for signed-out users and the API calls just 401.
- [ ] Fix the two silent-success stubs: `transcode` and `extract_audio` mark jobs
      `done` with no output instead of failing.
- [ ] Give `transcribe` a worker handler, or drop it from the `JobRequest` union —
      today it would retry to the DLQ. IAM permissions are already in place.
- [ ] Don't re-deliver permanently failed jobs: `worker.py` marks the row `failed`
      but never deletes the SQS message.
- [ ] Job status needs a refresh (poll or manual button) — the list is fetched
      once on mount, so a running job's status only updates on reload.
- [ ] Infra polish: private-repo deploy auth + CloudWatch log shipping.
- [x] Backend auth (JWT register/login/logout; routes token-guarded).
- [x] File upload endpoint (`POST /upload` → S3 key).
- [x] Typed frontend API client; `LoginPage` now goes through it (it used to
      hardcode `http://localhost:8000` and ignore `VITE_API_BASE`).
- [x] **`image_resize`, `deblur` and `format_converter` wired end-to-end**
      (Dashboard → upload → job → result).
- [x] `video_quality` + `trim` implemented in the worker (not exposed in the UI).
- [x] `/jobs` is real (`useJobs` → `api.listTasks`), with status filters, download
      and delete. `/marketplace` is a real Task Catalog that deep-links into the
      Dashboard.
- [x] UI cleanup: removed the 11 fictional task options, the mock job list, the
      invented pricing, and the dead `/pricing` + `/settings` sidebar links;
      consolidated the triplicated nav into `components/AppLayout.tsx`.
- [x] EC2 worker provisioning (Terraform + systemd + Python 3.11 + static ffmpeg).

**Testable end-to-end today** (see `RUNBOOK.md`): via the UI — register at
`/login` → Dashboard → pick Image Resize, Deblur, or Format Converter → upload a
file → job processes → view result. Or via curl against the backend directly.

**Suggested next task:** add `video_quality` and `trim` to `TASKS` in
`frontend/src/tasks.ts` so the video path is reachable from the UI — the worker
handlers already exist, so this is a frontend-only change.
