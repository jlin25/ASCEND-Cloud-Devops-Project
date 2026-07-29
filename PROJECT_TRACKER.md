# ASCEND — Project Tracker

Status of every part of the project. Legend:
✅ done · 🟡 partial · ⏳ not started · 🔴 blocked

Last updated: 2026-07-21. Architecture → `CONTEXT.md`. Launch/test/teardown → `RUNBOOK.md`.

**Region:** all AWS infra in `us-east-2`. As of last update the stack is
**deployed and running** (S3 + SQS + EC2 worker). Backend is testable end-to-end.

---

## Overview

| Part | Status | Notes |
|------|--------|-------|
| Frontend | 🟡 | API client done; UI not wired to it (no login/upload/submit UI) |
| Backend API | ✅ | Endpoints + validation + SQS/S3 enqueue working |
| Worker | 🟡 | `video_quality` works; 3 job types stubbed |
| Storage (S3) | ✅ | `S3Client` upload/download/presign/delete |
| Database | ✅ | `jobs` + `users` schema in place |
| Auth | ✅ | JWT register/login/get_current_user; all routes token-guarded |
| Infra (Terraform) | ✅ | SQS/DLQ/IAM/S3 + EC2 worker (instance role, SSM config, systemd, ffmpeg) |
| Tests | 🟡 | Backend tests exist; no frontend tests |

---

## Frontend — `frontend/`

| Item | Status | Notes |
|------|--------|-------|
| API client (`src/api.ts`, `api-types.ts`) | ✅ | Typed `api.*`, `ApiError`, `VITE_API_BASE` |
| Routing / pages | ✅ | `HomePage`, `TutorialPage` |
| Submit → `POST /tasks` | ⏳ | `HomePage.tsx:24` still an `alert()` |
| File upload flow | ⏳ | No way to turn a user file into an S3 `file_url` |
| Job status / results UI | ⏳ | No display of progress or download link |
| Backend connectivity indicator | ⏳ | Could use `GET /api/message` |
| Frontend tests | ⏳ | None |

## Backend — `backend/`

| Item | Status | Notes |
|------|--------|-------|
| Health endpoints (`/`, `/api/message`) | ✅ | No external deps |
| `POST /tasks` (create + enqueue) | ✅ | Writes DB row + sends to SQS |
| `GET /tasks`, `GET /tasks/{id}` | ✅ | Needs Supabase |
| `GET /tasks/{id}/result` | ✅ | Presigned S3 URL when done |
| `DELETE /tasks/{id}` | ✅ | |
| `POST /upload` (file → S3 key) | ✅ | Returns the S3 key used as `file_url` |
| Job type models (`jobs/jobs.py`) | ✅ | Discriminated union, 4 types |
| Auth (`routers/auth.py`) | ✅ | JWT register/login/logout; `get_current_user` guards all routes |
| CORS | ✅ | Allows `http://localhost:5173` |

## Worker — `backend/worker.py`

| Job type | Status | Notes |
|----------|--------|-------|
| `video_quality` | ✅ | S3 download → ffmpeg rescale → S3 upload (`processed/`) |
| `transcode` | ⏳ | `pass` stub |
| `trim` | ⏳ | `pass` stub |
| `extract_audio` | ⏳ | `pass` stub |
| SQS poll loop + status updates | ✅ | `processing` → `done`/`failed` |

## Storage — `backend/s3_client.py`

| Item | Status |
|------|--------|
| `upload_stream` / `download_stream` | ✅ |
| `get_output_url` (24h presigned) | ✅ |
| `delete_object` | ✅ |

## Database — `backend/db/schema.sql`

| Item | Status | Notes |
|------|--------|-------|
| `jobs` table | ✅ | status/input+output url/type/progress/user_id |
| `users` table | ✅ | username, hashed_password, created_at |
| Migrations tooling | ⏳ | Schema applied manually |

## Infrastructure — `infra/` (Terraform)

| Item | Status |
|------|--------|
| SQS queue + DLQ | ✅ | `infra/sqs.tf` |
| IAM user/credentials | ✅ | `infra/iam.tf` (local-dev user + worker instance role) |
| S3 bucket | ✅ | `infra/s3.tf` |
| EC2 worker instance | ✅ | `infra/ec2.tf` — AL2023, instance role, egress-only SG, SSM access |
| Provisioning script (`user_data.sh.tftpl`) | ✅ | Installs Python 3.11 + static ffmpeg, pulls SSM config, runs `worker.py` via systemd |
| Worker runtime config via SSM | ✅ | queue/dlq/region/**bucket**/db creds; bucket name wired to worker |
| `init.sh` provision/destroy wrapper | ✅ | `infra/init.sh` |
| Private-repo deploy auth | ⏳ | `git clone` assumes a public repo / no deploy key |
| Log shipping (CloudWatch) | ⏳ | Worker logs only to journald on the box |

## Tests

| Suite | Status |
|-------|--------|
| `backend/tests/test_jobs.py` | ✅ |
| `backend/tests/test_tasks_api.py` | ✅ |
| `backend/tests/test_worker.py` | ✅ |
| Frontend tests | ⏳ |
| CI pipeline | ⏳ |

---

## Prioritized backlog

1. Frontend auth UI (login/register form → store JWT → send as `Bearer`).
2. Frontend upload UI → `POST /upload`, then `HomePage` submit → `api.createTask`
   (build around `video_quality`; backend `/upload` + `/tasks` already work).
3. Job status / results UI (progress + download link via `GET /tasks/{id}/result`).
4. Implement remaining worker job types (`transcode`, `trim`, `extract_audio`).
5. Infra polish: private-repo deploy auth + CloudWatch log shipping.
6. Fix `init.sh` `>>` append bug — re-runs duplicate keys in `backend/.env`
   (stale wrong-region values); should rewrite the managed keys instead.
7. CI + frontend tests.
