# ASCEND — Launch & Manual Test Runbook

Everything needed to stand up the infra, run the app, manually test a job, and
tear it all down. Region is **us-east-2** (pinned in `infra/terraform.tfvars`).

See `CONTEXT.md` for architecture and `PROJECT_TRACKER.md` for component status.

---

## 0. AWS credentials (do this first, every session)

Auth uses static IAM keys (`aws configure`). Stale env vars from earlier
browser logins shadow them, so clear them once per shell:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION
aws sts get-caller-identity        # must succeed, no ExpiredToken
```

If you ever see "No valid credential sources found" when running Terraform,
bridge the creds into the shell first:
```bash
eval "$(aws configure export-credentials --format env)"
```

---

## 1. Provision infrastructure

Supabase values are NOT Terraform outputs, so export them before applying:

```bash
export TF_VAR_db_url="https://<your-ref>.supabase.co"
export TF_VAR_db_service_key="<supabase key>"
# optional: deploy the worker onto EC2 (else box boots without the worker)
export TF_VAR_worker_repo_url="https://github.com/<owner>/ASCEND-Cloud-Devops-Project.git"
export TF_VAR_worker_branch="backend_integration"

./infra/init.sh
```

`init.sh` runs `terraform apply` and writes AWS values into `backend/.env`.

> ⚠️ `init.sh` APPENDS to `backend/.env`. Running it multiple times duplicates
> keys and can leave stale (wrong-region) values. After re-running, verify:
> ```bash
> grep -oE '^[A-Z_]+=' backend/.env | sort | uniq -c   # every key should show count 1
> grep -E '^AWS_REGION=|^SQS_QUEUE_URL=' backend/.env    # must be us-east-2
> ```
> If duplicated, delete the old lines (keep the last/us-east-2 set).

---

## 2. Finish backend/.env

Add the values `init.sh` can't provide:
```
DB_URL=https://<your-ref>.supabase.co
DB_SERVICE_KEY=<supabase key>
SECRET_KEY=<random string — generate with: python3 -c "import secrets;print(secrets.token_hex(32))">
```
Backend reads: `AWS_REGION`, `SQS_QUEUE_URL`, `S3_BUCKET_NAME`, `DB_URL`,
`DB_SERVICE_KEY`, `SECRET_KEY`, plus the AWS keys.

Also ensure the Supabase schema is applied (`backend/db/schema.sql` → `jobs`, `users`).

---

## 3. Run the backend + worker locally

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # needs Python >=3.10 (anyio pin)

# terminal A — API
uvicorn main:app --reload               # http://localhost:8000

# terminal B — worker (needs ffmpeg installed locally)
python worker.py                        # prints "worker started, polling for jobs..."
```

> Env vars are read at startup — after editing `.env`, RESTART both processes.

---

## 4. Manual test (send a request)

```bash
BASE=http://localhost:8000

# health
curl -s $BASE/

# register → JWT
TOKEN=$(curl -s $BASE/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"test","password":"pass123"}' | jq -r .token)

# upload a file → S3 key (response field: file_key)
KEY=$(curl -s $BASE/upload -H "Authorization: Bearer $TOKEN" \
  -F file=@sample.mp4 | jq -r .file_key)

# submit a job (video_quality is the only fully-implemented type)
curl -s $BASE/tasks -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"type\":\"video_quality\",\"file_url\":\"$KEY\",\"resolution\":\"720p\"}"

# poll status
curl -s $BASE/tasks -H "Authorization: Bearer $TOKEN" | jq

# once "done": get presigned download URL
curl -s $BASE/tasks/<task_id>/result -H "Authorization: Bearer $TOKEN"
```

Expected: status goes `pending → processing → done`. Verify output resolution:
```bash
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 output.mp4
# height should equal the requested resolution (720p → 720)
```

Needs `jq` and a real `sample.mp4`. Only `video_quality` processes;
`transcode`/`trim`/`extract_audio` enqueue but the worker no-ops them.

---

## 5. Troubleshooting

- **Job stuck at `pending`** → nothing is consuming the queue. Check the message
  is queued: `aws sqs get-queue-attributes --queue-url <url> --region us-east-2
  --attribute-names ApproximateNumberOfMessages`. If a message sits there, the
  worker isn't running or points at the wrong queue/region (see the `.env`
  duplicate-key check in step 1).
- **401/403 on any /tasks or /upload call** → missing/expired `Bearer` token.
- **register errors** → Supabase schema/creds wrong.
- **EC2 worker won't connect via SSM** → give it ~3 min after boot; if the
  bootstrap failed check `aws ec2 get-console-output --instance-id <id>
  --region us-east-2`. AL2023 needs Python 3.11 (the pinned deps require >=3.10).

---

## 6. Tear down

```bash
cd infra
eval "$(aws configure export-credentials --format env)"
terraform destroy            # or: ./infra/init.sh destroy
```

Confirm it's fully gone:
```bash
terraform state list                                   # empty
aws s3 ls | grep ascend || echo "no buckets"
aws sqs list-queues --region us-east-2 --query QueueUrls --output text | grep ascend || echo "no queues"
```
`terraform destroy` also prints `Destroy complete! Resources: N destroyed.`
