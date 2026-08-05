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
    res = client.get("/")
    assert res.status_code == 200
    assert "ResumeVerify" in res.text


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

    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
