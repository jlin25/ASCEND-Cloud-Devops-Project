"""API tests for the internal ZIP download endpoints (/bundles).

Supabase, SQS and S3 are replaced with in-memory fakes.
"""
import json

import pytest
from fastapi.testclient import TestClient

import main
from routers import bundles as bundles_module
from routers.auth import User, get_current_user


# --- fakes ------------------------------------------------------------------
class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, db):
        self.db = db
        self.op = None
        self.payload = None
        self.filters = []

    def select(self, *columns):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def insert(self, row):
        self.op = "insert"
        self.payload = row
        return self

    def eq(self, column, value):
        self.filters.append(lambda r: r.get(column) == value)
        return self

    def neq(self, column, value):
        self.filters.append(lambda r: r.get(column) != value)
        return self

    def in_(self, column, values):
        values = list(values)
        self.db.in_sizes.append((column, len(values)))
        self.filters.append(lambda r: r.get(column) in values)
        return self

    def execute(self):
        if self.op == "insert":
            row = {"id": f"new-{len(self.db.rows)}", "status": "pending", "progress": 0, "output_key": None}
            row.update(self.payload)
            self.db.rows.append(row)
            return FakeResult([row])
        matched = [r for r in self.db.rows if all(f(r) for f in self.filters)]
        if self.op == "delete":
            self.db.rows = [r for r in self.db.rows if r not in matched]
        return FakeResult(matched)


class FakeDB:
    def __init__(self):
        self.rows = []
        self.in_sizes = []

    def table(self, name):
        assert name == "jobs"
        return FakeQuery(self)


class FakeQueue:
    def __init__(self):
        self.messages = []

    def send(self, body):
        self.messages.append(body)


class FakeS3:
    def __init__(self):
        self.uploads = {}
        self.deleted = []

    def upload_stream(self, user_id, filename, fileobj, content_type, prefix="uploads"):
        key = f"{prefix}/{user_id}/{filename}"
        self.uploads[key] = fileobj.read()
        return key

    def delete_object(self, key):
        self.deleted.append(key)

    def get_output_url(self, key, expires_in=None, download_name=None):
        return f"https://signed/{key}?name={download_name}"


def job(id, user="u1", status="done", job_type="image_resize", output=True):
    return {
        "id": id,
        "user_id": user,
        "status": status,
        "job_type": job_type,
        "progress": 100 if status == "done" else 0,
        "input_key": f"uploads/{user}/{id}.png",
        "output_key": f"processed/{user}/{id}.png" if output and status == "done" else None,
    }


def bundle(id, user="u1", status="done"):
    return {
        "id": id,
        "user_id": user,
        "status": status,
        "job_type": "bundle",
        "progress": 100 if status == "done" else 0,
        "input_key": f"bundles/{user}/{id}.json",
        "output_key": f"bundles/{user}/{id}.zip" if status == "done" else None,
    }


@pytest.fixture
def fakes(monkeypatch):
    db, q, s3 = FakeDB(), FakeQueue(), FakeS3()
    monkeypatch.setattr(bundles_module, "database", db)
    monkeypatch.setattr(bundles_module, "queue", q)
    monkeypatch.setattr(bundles_module, "s3", s3)
    return db, q, s3


@pytest.fixture
def client(fakes):
    main.app.dependency_overrides[get_current_user] = lambda: User(id="u1", username="alice")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def manifest(s3):
    [key] = [k for k in s3.uploads if k.endswith(".json")]
    return key, json.loads(s3.uploads[key])


# --- POST /bundles ------------------------------------------------------------
def test_create_bundle_includes_only_own_finished_results(client, fakes):
    db, q, s3 = fakes
    db.rows = [
        job("j1"),
        job("j2", status="processing"),
        job("j3", user="u2"),  # someone else's
        job("j4", status="failed"),
        bundle("b0", status="processing"),  # a bundle id must never be zipped into a bundle
    ]

    resp = client.post("/bundles", json={"task_ids": ["j1", "j2", "j3", "j4", "b0", "j1"]})
    assert resp.status_code == 200
    bundle_id = resp.json()["bundle_id"]

    key, body = manifest(s3)
    assert body == {"files": ["processed/u1/j1.png"]}
    assert key.startswith("bundles/u1/")

    row = next(r for r in db.rows if r["id"] == bundle_id)
    assert row["job_type"] == "bundle"
    assert row["input_key"] == key
    assert row["user_id"] == "u1"

    assert q.messages == [{"job_id": bundle_id, "user_id": "u1", "type": "bundle", "file_url": key}]


def test_create_bundle_400_when_nothing_is_done(client, fakes):
    db, q, s3 = fakes
    db.rows = [job("j1", status="processing"), job("j2", user="u2")]
    resp = client.post("/bundles", json={"task_ids": ["j1", "j2"]})
    assert resp.status_code == 400
    assert q.messages == []
    assert s3.uploads == {}


def test_create_bundle_rejects_empty_list(client):
    assert client.post("/bundles", json={"task_ids": []}).status_code == 422


def test_create_bundle_looks_up_ids_in_chunks(client, fakes):
    db, _, s3 = fakes
    db.rows = [job(f"j{i}") for i in range(250)]
    resp = client.post("/bundles", json={"task_ids": [f"j{i}" for i in range(250)]})
    assert resp.status_code == 200

    id_lookups = [n for column, n in db.in_sizes if column == "id"][:3]
    assert id_lookups == [100, 100, 50]
    assert len(manifest(s3)[1]["files"]) == 250


def test_create_bundle_cleans_up_previous_finished_bundles(client, fakes):
    db, _, s3 = fakes
    db.rows = [job("j1"), bundle("old"), bundle("failed-old", status="failed"), bundle("busy", status="processing")]

    client.post("/bundles", json={"task_ids": ["j1"]})

    ids = {r["id"] for r in db.rows}
    assert "old" not in ids and "failed-old" not in ids
    assert "busy" in ids  # the worker may still be writing it
    assert set(s3.deleted) == {"bundles/u1/old.json", "bundles/u1/old.zip", "bundles/u1/failed-old.json"}


def test_create_bundle_never_cleans_up_other_users_bundles(client, fakes):
    db, _, s3 = fakes
    db.rows = [job("j1"), bundle("theirs", user="u2")]
    client.post("/bundles", json={"task_ids": ["j1"]})
    assert any(r["id"] == "theirs" for r in db.rows)
    assert s3.deleted == []


# --- GET /bundles/{id} --------------------------------------------------------
def test_get_bundle_has_no_link_until_done(client, fakes):
    db, _, _ = fakes
    db.rows = [bundle("b1", status="processing")]
    assert client.get("/bundles/b1").json() == {"status": "processing", "progress": 0, "download_url": None}


def test_get_bundle_returns_named_download_link_when_done(client, fakes):
    db, _, _ = fakes
    db.rows = [bundle("b1")]
    db.rows[0]["output_key"] = "bundles/u1/0b4a9f3e-1c2d-4e5f-8a9b-0c1d2e3f4a5b-results-3-files.zip"
    body = client.get("/bundles/b1").json()
    assert body["status"] == "done"
    assert body["download_url"].endswith("?name=results-3-files.zip")


@pytest.mark.parametrize("method", ["get", "delete"])
def test_bundle_endpoints_404_for_normal_jobs(client, fakes, method):
    db, _, s3 = fakes
    db.rows = [job("j1")]
    assert getattr(client, method)("/bundles/j1").status_code == 404
    assert db.rows == [job("j1")]
    assert s3.deleted == []


@pytest.mark.parametrize("method", ["get", "delete"])
def test_bundle_endpoints_404_for_other_users(client, fakes, method):
    db, _, _ = fakes
    db.rows = [bundle("b1", user="u2")]
    assert getattr(client, method)("/bundles/b1").status_code == 404


# --- DELETE /bundles/{id} -----------------------------------------------------
def test_delete_bundle_removes_zip_and_manifest_but_not_results(client, fakes):
    db, _, s3 = fakes
    db.rows = [job("j1"), bundle("b1")]

    assert client.delete("/bundles/b1").status_code == 200
    assert [r["id"] for r in db.rows] == ["j1"]
    assert set(s3.deleted) == {"bundles/u1/b1.json", "bundles/u1/b1.zip"}
