"""API-level tests for the /tasks + /upload endpoints via FastAPI's TestClient.

Supabase, SQS and S3 are all replaced with in-memory fakes, and the auth
dependency is overridden so we don't need a real JWT.
"""
import pytest
from fastapi.testclient import TestClient

import main
from routers import tasks as tasks_module
from routers.auth import get_current_user, User


# --- fakes for the external boundaries -------------------------------------
class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    """Minimal supabase-py table chain: .insert(row).execute()."""

    def __init__(self, insert_id="job-123"):
        self.insert_id = insert_id
        self.inserted = None

    def insert(self, row):
        self.inserted = row
        return self

    def execute(self):
        return FakeResult([{"id": self.insert_id}])


class FakeDB:
    def __init__(self):
        self.jobs = FakeTable()

    def table(self, name):
        assert name == "jobs"
        return self.jobs


class FakeQueue:
    def __init__(self):
        self.messages = []

    def send(self, body):
        self.messages.append(body)


# --- fixtures ---------------------------------------------------------------
@pytest.fixture
def fake_queue(monkeypatch):
    q = FakeQueue()
    monkeypatch.setattr(tasks_module, "queue", q)
    return q


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(tasks_module, "database", db)
    return db


@pytest.fixture
def client(fake_queue, fake_db):
    main.app.dependency_overrides[get_current_user] = lambda: User(id="u1", username="alice")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


# --- tests ------------------------------------------------------------------
def test_create_video_quality_task_enqueues_with_user_id(client, fake_queue, fake_db):
    resp = client.post(
        "/tasks",
        json={"type": "video_quality", "file_url": "uploads/u1/a.mp4", "resolution": "1080p"},
    )
    assert resp.status_code == 200
    assert resp.json()["task_id"] == "job-123"

    # DB row: request fields mapped onto the jobs columns
    assert fake_db.jobs.inserted["job_type"] == "video_quality"
    assert fake_db.jobs.inserted["input_key"] == "uploads/u1/a.mp4"
    assert fake_db.jobs.inserted["user_id"] == "u1"

    # SQS payload: job_id + user_id + the full typed job
    msg = fake_queue.messages[0]
    assert msg["job_id"] == "job-123"
    assert msg["user_id"] == "u1"
    assert msg["type"] == "video_quality"
    assert msg["resolution"] == "1080p"


def test_create_task_rejects_unknown_type(client):
    resp = client.post("/tasks", json={"type": "nope", "file_url": "k"})
    assert resp.status_code == 422


def test_create_task_rejects_bad_resolution(client):
    resp = client.post(
        "/tasks",
        json={"type": "video_quality", "file_url": "k", "resolution": "480p"},
    )
    assert resp.status_code == 422


def test_tasks_requires_auth():
    # No dependency override here → HTTPBearer rejects the missing header
    # (401/403 depending on the FastAPI version).
    main.app.dependency_overrides.clear()
    c = TestClient(main.app)
    resp = c.post(
        "/tasks",
        json={"type": "video_quality", "file_url": "k", "resolution": "720p"},
    )
    assert resp.status_code in (401, 403)


def test_upload_returns_key(monkeypatch):
    pytest.importorskip("multipart")  # needs python-multipart
    monkeypatch.setattr(
        tasks_module.s3,
        "upload_stream",
        lambda user_id, filename, fileobj, content_type, prefix="uploads": f"uploads/{user_id}/{filename}",
    )
    main.app.dependency_overrides[get_current_user] = lambda: User(id="u1", username="alice")
    try:
        c = TestClient(main.app)
        resp = c.post("/upload", files={"file": ("a.mp4", b"data", "video/mp4")})
        assert resp.status_code == 200
        assert resp.json()["file_key"] == "uploads/u1/a.mp4"
    finally:
        main.app.dependency_overrides.clear()


def test_health_endpoint():
    c = TestClient(main.app)
    assert c.get("/").json() == {"status": "backend running"}
