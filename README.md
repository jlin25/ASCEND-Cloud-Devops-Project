# Cloud-Based Task Execution Marketplace

## Running the project

Three processes run locally: the **API** (FastAPI), the **worker** (pulls jobs off SQS and runs them), and the **frontend** (React + Vite). The API and worker talk to AWS (S3 + SQS) and Supabase, so those need to exist first. See [RUNBOOK.md](RUNBOOK.md) for provisioning them with Terraform.

### Prerequisites

- Python 3.10+
- Node.js 20.19+ (required by Vite 8)
- `ffmpeg` on your `PATH` (used by the worker)
- AWS credentials (`aws configure`) and the infra from `./infra/init.sh`
- A Supabase project with `backend/db/schema.sql` applied

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`. `./infra/init.sh` writes the AWS values; add the rest yourself:

```
AWS_REGION=us-east-2
SQS_QUEUE_URL=<from init.sh>
S3_BUCKET_NAME=<from init.sh>
DB_URL=https://<your-ref>.supabase.co
DB_SERVICE_KEY=<supabase service key>
SECRET_KEY=<python3 -c "import secrets;print(secrets.token_hex(32))">
```

Then run the API and the worker in two terminals (both from `backend/`, venv activated):

```bash
uvicorn main:app --reload      # API on http://localhost:8000
python worker.py               # first start downloads the deblur model
```

Restart both after editing `.env`. Run the tests with `pytest`.

> If you move or rename the project folder, recreate `.venv`. Its scripts hard-code the old path and fail with "bad interpreter".

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Open http://localhost:5173, create an account, and submit a job. The frontend calls the API at `http://localhost:8000` by default; set `VITE_API_BASE` to point it elsewhere. The API only accepts browser requests from `http://localhost:5173` (CORS in `backend/main.py`).

After changing backend request models, regenerate the frontend's API types with `npm run gen:api` (the API must be running).

---

## Summary

This project is a cloud-based task execution marketplace that enables users to run compute-intensive workflows without needing technical expertise. It provides an abstraction layer over scalable cloud infrastructure, allowing users to submit tasks, provision temporary compute environments, execute workloads, and retrieve results through a simple web interface.

The platform combines a marketplace model with on-demand cloud computing to support tasks such as video processing, content generation, and other resource-heavy workloads.

---

## System Overview

### Frontend

- Web interface for task submission and workspace interaction  
- Real-time job status tracking  
- Output visualization and delivery  

### Backend

- API layer for authentication, task routing, and job scheduling  
- Handles marketplace logic, payments, and data management  
- Interfaces between frontend and cloud compute layer  

### Cloud Compute Layer

- On-demand virtual machines or containerized environments  
- Executes user-submitted workloads  
- Automatically scales based on demand  
- Returns processed outputs and terminates resources after completion  

---

## Workflow

1. User submits or selects a task via the web interface  
2. Backend routes the task to the compute system  
3. A cloud workspace is provisioned  
4. Task executes in an isolated environment  
5. Results are stored and returned to the user  
6. Workspace is terminated to optimize cost and resources  

---

## Project Timeline (9–12 Months)

### Phase 1: Problem Validation (Month 1)

- Identify target users and validate use cases  
- Define MVP requirements  
- Establish pricing and market assumptions  

### Phase 2: System Design (Month 2)

- Define full system architecture  
- Select technology stack  
- Create system design documentation  

### Phase 3: Core Infrastructure (Month 3)

- Set up cloud and backend environment  
- Implement authentication and base APIs  
- Establish database systems  

### Phase 4: Compute Engine (Months 4–5)

- Build virtual workspace provisioning  
- Implement task execution pipeline  
- Enable file transfer workflows  

### Phase 5: Frontend Development (Months 6–7)

- Build UI dashboard  
- Connect frontend to backend APIs  
- Implement job tracking system  

### Phase 6: Marketplace System (Months 7–8)

- Build task marketplace and job queue  
- Integrate pricing and payment systems  
- Enable automated task execution flow  

### Phase 7: Optimization (Month 9)

- Improve performance and reduce compute costs  
- Implement auto-scaling and load balancing  
- Conduct stress testing  

### Phase 8: Testing & Launch (Months 10–12)

- Run beta testing with users  
- Fix system issues and refine UX  
- Collect metrics and prepare final demo  

---

## Team

- Joyce Lin  
- Kevin Dang  
- Princeden Hom  
- Amber Wang  

### Mentors

- Chris Chen  
- Professor Hakim Weatherspoon  

---

## Tech Stack (Planned)

- Frontend: React  
- Backend: FastAPI / Python  
- Cloud: Scalable VM or container-based infrastructure  
- Database: TBD
