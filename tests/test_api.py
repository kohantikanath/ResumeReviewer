"""API smoke tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "samples"


def test_health():
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_index_html():
    client = TestClient(app)
    res = client.get("/dashboard", follow_redirects=True)
    assert res.status_code == 200
    assert "ResumeVerify" in res.text

    root = client.get("/", follow_redirects=True)
    assert root.status_code == 200
    assert "dashboard" in str(root.url) or "ResumeVerify" in root.text


def test_batch_upload_and_poll():
    client = TestClient(app)
    good_pdf = FIXTURES / "Good 1.pdf"
    meta = FIXTURES / "metadata.xlsx"

    with good_pdf.open("rb") as pdf, meta.open("rb") as m:
        res = client.post(
            "/api/batch?check_links=false",
            files=[
                ("resumes", ("Good 1.pdf", pdf, "application/pdf")),
                ("metadata", ("metadata.xlsx", m, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )

    assert res.status_code == 200
    job_id = res.json()["job_id"]

    # Background tasks run inline in TestClient
    status = client.get(f"/api/jobs/{job_id}")
    assert status.status_code == 200
    data = status.json()
    assert data["status"] == "completed"
    assert data["report_ready"]
    assert data["outcomes_summary"]

    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_job_persists_across_store_reload():
    """Job JSON on disk survives a fresh in-memory store (server restart)."""
    from app.api.jobs import JobStatus, JobStore, _DEFAULT_INDEX

    store = JobStore(persist_dir=_DEFAULT_INDEX)
    job = store.create(total=1)
    store.update(
        job.id,
        status=JobStatus.COMPLETED,
        processed=1,
        outcomes_summary=[{"name": "Test", "verdict": "PASS", "issues": []}],
    )

    reloaded = JobStore(persist_dir=_DEFAULT_INDEX)
    loaded = reloaded.get(job.id)
    assert loaded is not None
    assert loaded.status.value == "completed"
    assert len(loaded.outcomes_summary) == 1
