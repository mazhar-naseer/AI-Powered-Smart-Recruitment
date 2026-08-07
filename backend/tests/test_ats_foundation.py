from tests.conftest import auth, login, register


JOB = {
    "title": "Platform Engineer",
    "description": "Build reliable production infrastructure and backend services.",
    "required_skills": ["Python", "PostgreSQL"],
    "status": "open",
}


def test_workspace_team_invitation_switching_and_viewer_permissions(client):
    register(client, "employer", "owner.ats@example.com", "Workspace Owner")
    register(client, "employer", "viewer.ats@example.com", "Read Only Recruiter")
    register(client, "employer", "revoked.ats@example.com", "Revoked Recruiter")
    owner = login(client, "owner.ats@example.com")
    viewer = login(client, "viewer.ats@example.com")
    owner_headers, viewer_headers = auth(owner["access_token"]), auth(viewer["access_token"])

    workspace = client.get("/api/v1/workspace", headers=owner_headers)
    assert workspace.status_code == 200
    assert workspace.json()["data"]["membership"]["role"] == "owner"
    assert "team.manage" in workspace.json()["data"]["membership"]["permissions"]

    invited = client.post(
        "/api/v1/workspace/team/invitations",
        headers=owner_headers,
        json={"email": "viewer.ats@example.com", "role": "viewer"},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["data"]["invitation_token"]
    accepted = client.post(f"/api/v1/workspace/team/invitations/{token}/accept", headers=viewer_headers)
    assert accepted.status_code == 200, accepted.text

    workspaces = client.get("/api/v1/workspaces", headers=viewer_headers).json()["data"]
    assert len(workspaces) == 2
    assert sum(item["active"] for item in workspaces) == 1
    assert next(item for item in workspaces if item["active"])["role"] == "viewer"
    forbidden = client.post("/api/v1/employer/jobs", headers=viewer_headers, json=JOB)
    assert forbidden.status_code == 403

    revoked = client.post(
        "/api/v1/workspace/team/invitations",
        headers=owner_headers,
        json={"email": "revoked.ats@example.com", "role": "recruiter"},
    )
    invitation_id = revoked.json()["data"]["id"]
    assert client.delete(f"/api/v1/workspace/team/invitations/{invitation_id}", headers=owner_headers).status_code == 200
    assert client.delete(f"/api/v1/workspace/team/invitations/{invitation_id}", headers=owner_headers).status_code == 404


def test_pipeline_collaboration_notifications_and_private_storage(client):
    register(client, "employer", "pipeline.owner@example.com", "Pipeline Owner")
    register(client, "applicant", "pipeline.candidate@example.com", "Casey Candidate")
    owner = login(client, "pipeline.owner@example.com")
    applicant = login(client, "pipeline.candidate@example.com")
    owner_headers, applicant_headers = auth(owner["access_token"]), auth(applicant["access_token"])

    job = client.post("/api/v1/employer/jobs", headers=owner_headers, json=JOB)
    assert job.status_code == 201, job.text
    job_id = job.json()["data"]["id"]
    applied = client.post(
        f"/api/v1/jobs/{job_id}/applications",
        headers=applicant_headers,
        files={"resume": ("candidate.pdf", b"%PDF-1.4\n% ATS fixture", "application/pdf")},
    )
    assert applied.status_code == 202, applied.text
    application_id = applied.json()["data"]["id"]

    stages = client.get("/api/v1/workspace/pipeline/stages", headers=owner_headers).json()["data"]
    assert [stage["name"] for stage in stages] == ["Applied", "Screening", "Interview", "Offer", "Hired", "Rejected"]
    custom = client.post(
        "/api/v1/workspace/pipeline/stages",
        headers=owner_headers,
        json={"name": "Technical Exercise", "color": "#4455aa", "category": "active"},
    )
    assert custom.status_code == 201, custom.text
    custom_id = custom.json()["data"]["id"]
    assert client.patch(
        f"/api/v1/workspace/pipeline/stages/{custom_id}",
        headers=owner_headers,
        json={"name": "Technical Interview", "position": 2},
    ).status_code == 200
    assert client.delete(f"/api/v1/workspace/pipeline/stages/{custom_id}", headers=owner_headers).status_code == 200
    assert client.delete(f"/api/v1/workspace/pipeline/stages/{stages[0]['id']}", headers=owner_headers).status_code == 404
    candidates = client.get("/api/v1/workspace/candidates", headers=owner_headers).json()["data"]
    candidate = next(item for item in candidates if item["id"] == application_id)
    assert candidate["stage_id"] == next(stage["id"] for stage in stages if stage["name"] == "Applied")

    screening = next(stage for stage in stages if stage["name"] == "Screening")
    assert client.patch(f"/api/v1/workspace/candidates/{application_id}/stage", headers=owner_headers, json={"stage_id": screening["id"]}).status_code == 200
    assert client.patch(f"/api/v1/workspace/candidates/{application_id}/tags", headers=owner_headers, json={"tags": ["priority", "backend", "priority"]}).json()["data"]["tags"] == ["priority", "backend"]
    assert client.patch(f"/api/v1/workspace/candidates/{application_id}/assignment", headers=owner_headers, json={"user_id": owner["user"]["id"]}).status_code == 200
    note = client.post(f"/api/v1/workspace/candidates/{application_id}/notes", headers=owner_headers, json={"body": "Strong infrastructure evidence; schedule a technical interview."})
    assert note.status_code == 201, note.text

    collaboration = client.get(f"/api/v1/workspace/candidates/{application_id}/collaboration", headers=owner_headers).json()["data"]
    assert collaboration["notes"][0]["body"].startswith("Strong infrastructure")
    event_types = {event["event_type"] for event in collaboration["timeline"]}
    assert {"application_received", "stage_changed", "tags_updated", "assignment_changed", "note_added"}.issubset(event_types)

    notifications = client.get("/api/v1/notifications", headers=applicant_headers).json()["data"]
    assert notifications["unread_count"] == 1
    assert notifications["items"][0]["type"] == "application_stage"
    assert client.post("/api/v1/notifications/read-all", headers=applicant_headers).status_code == 200
    assert client.get("/api/v1/notifications", headers=applicant_headers).json()["data"]["unread_count"] == 0

    from app.database import SessionLocal
    from app.models import BackgroundJob, Resume
    from sqlalchemy import select
    db = SessionLocal()
    try:
        resume = db.scalar(select(Resume).where(Resume.applicant_id == owner["user"]["id"]))
        stored = db.scalar(select(Resume).where(Resume.applicant_id == applicant["user"]["id"]))
        background = db.scalars(select(BackgroundJob)).all()
        assert stored and "/" not in stored.storage_key
        assert background and background[0].status.value == "completed"
    finally:
        db.close()

    from app.models import Role, User
    from app.security import hash_password
    with SessionLocal() as db:
        db.add(User(email="ats.admin@example.com", full_name="ATS Administrator", password_hash=hash_password("Password123!"), role=Role.ADMIN, email_verified=True))
        db.commit()
    administrator = login(client, "ats.admin@example.com")
    admin_headers = auth(administrator["access_token"])
    monitoring = client.get("/api/v1/admin/operations/monitoring", headers=admin_headers)
    assert monitoring.status_code == 200
    background_jobs = client.get("/api/v1/admin/operations/background-jobs", headers=admin_headers)
    assert background_jobs.status_code == 200
    completed = background_jobs.json()["data"][0]
    retried = client.post(f"/api/v1/admin/operations/background-jobs/{completed['id']}/retry", headers=admin_headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["status"] == "queued"
