from app.database import SessionLocal
from app.models import Application, ApplicationStatus, Role, User
from app.security import hash_password
from tests.conftest import auth, login, register


def make_admin():
    with SessionLocal() as db:
        db.add(
            User(
                email="admin@example.com",
                full_name="Admin",
                password_hash=hash_password("Password123!"),
                role=Role.ADMIN,
                email_verified=True,
            )
        )
        db.commit()


def test_application_validation_duplicate_and_employer_access(client, monkeypatch):
    register(client, "employer", "employer@example.com", "Employer")
    register(client, "applicant", "applicant@example.com", "Applicant")
    employer = login(client, "employer@example.com")
    applicant = login(client, "applicant@example.com")
    job = client.post(
        "/api/v1/employer/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Develop secure and scalable backend APIs.",
            "required_skills": ["Python", "SQL"],
            "status": "open",
        },
        headers=auth(employer["access_token"]),
    ).json()["data"]
    invalid = client.post(
        f"/api/v1/jobs/{job['id']}/applications",
        files={"resume": ("resume.txt", b"hello", "text/plain")},
        headers=auth(applicant["access_token"]),
    )
    assert invalid.status_code == 422
    monkeypatch.setattr("app.api.process_application", lambda *args: None)
    pdf = b"%PDF-1.4\n% test fixture"
    accepted = client.post(
        f"/api/v1/jobs/{job['id']}/applications",
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=auth(applicant["access_token"]),
    )
    assert accepted.status_code == 202, accepted.text
    duplicate = client.post(
        f"/api/v1/jobs/{job['id']}/applications",
        files={"resume": ("resume.pdf", pdf, "application/pdf")},
        headers=auth(applicant["access_token"]),
    )
    assert duplicate.status_code == 409
    own = client.get("/api/v1/applicant/applications", headers=auth(applicant["access_token"]))
    assert len(own.json()["data"]) == 1
    ranked = client.get(
        f"/api/v1/employer/jobs/{job['id']}/applications", headers=auth(employer["access_token"])
    )
    assert ranked.status_code == 200
    application_id = ranked.json()["data"][0]["id"]
    download = client.get(
        f"/api/v1/employer/applications/{application_id}/resume",
        headers=auth(employer["access_token"]),
    )
    assert download.status_code == 200


def test_admin_dashboard_suspend_and_moderate(client):
    make_admin()
    register(client, "employer", "employer@example.com", "Employer")
    admin = login(client, "admin@example.com")
    employer = login(client, "employer@example.com")
    job = client.post(
        "/api/v1/employer/jobs",
        json={
            "title": "Data Engineer",
            "description": "Create production data processing pipelines.",
            "required_skills": ["Python"],
            "status": "open",
        },
        headers=auth(employer["access_token"]),
    ).json()["data"]
    users = client.get("/api/v1/admin/users", headers=auth(admin["access_token"])).json()["data"]
    target = next(user for user in users if user["email"] == "employer@example.com")
    suspended = client.patch(
        f"/api/v1/admin/users/{target['id']}/status",
        json={"status": "suspended"},
        headers=auth(admin["access_token"]),
    )
    assert suspended.status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(employer["access_token"])).status_code == 401
    assert (
        client.delete(
            f"/api/v1/admin/jobs/{job['id']}", headers=auth(admin["access_token"])
        ).status_code
        == 200
    )
    dashboard = client.get("/api/v1/admin/dashboard", headers=auth(admin["access_token"]))
    assert dashboard.status_code == 200
    assert dashboard.json()["data"]["employers"] == 1


def test_existing_admin_can_provision_another_admin(client):
    make_admin()
    admin = login(client, "admin@example.com")
    payload = {
        "full_name": "Operations Admin",
        "email": "operations.admin@example.com",
        "password": "StrongAdmin@2026",
    }
    created = client.post(
        "/api/v1/admin/users/admin",
        json=payload,
        headers=auth(admin["access_token"]),
    )
    assert created.status_code == 201, created.text
    user = created.json()["data"]
    assert user["role"] == "admin"
    assert user["status"] == "active"
    assert user["email_verified"] is True
    assert client.post(
        "/api/v1/admin/users/admin",
        json=payload,
        headers=auth(admin["access_token"]),
    ).status_code == 409
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login_response.status_code == 200


def test_admin_user_list_tolerates_legacy_local_email(client):
    make_admin()
    with SessionLocal() as db:
        db.add(
            User(
                email="legacy.user@smarthire.local",
                full_name="Legacy User",
                password_hash=hash_password("Password123!"),
                role=Role.APPLICANT,
                email_verified=True,
            )
        )
        db.commit()
    admin = login(client, "admin@example.com")
    response = client.get("/api/v1/admin/users", headers=auth(admin["access_token"]))
    assert response.status_code == 200, response.text
    assert any(user["email"] == "legacy.user@smarthire.local" for user in response.json()["data"])


def test_admin_can_review_applications_and_download_resume(client, monkeypatch):
    make_admin()
    register(client, "employer", "review.employer@example.com", "Review Employer")
    register(client, "applicant", "review.applicant@example.com", "Review Applicant")
    admin = login(client, "admin@example.com")
    employer = login(client, "review.employer@example.com")
    applicant = login(client, "review.applicant@example.com")
    job = client.post(
        "/api/v1/employer/jobs",
        json={
            "title": "Platform Engineer",
            "description": "Build and operate secure production platform services.",
            "required_skills": ["Python", "PostgreSQL"],
            "status": "open",
        },
        headers=auth(employer["access_token"]),
    ).json()["data"]
    monkeypatch.setattr("app.api.process_application", lambda *args: None)
    monkeypatch.setattr("app.api.settings.gemini_api_key", "test-key")
    accepted = client.post(
        f"/api/v1/jobs/{job['id']}/applications",
        files={"resume": ("candidate.pdf", b"%PDF-1.4\n% admin review fixture", "application/pdf")},
        headers=auth(applicant["access_token"]),
    )
    application_id = accepted.json()["data"]["id"]
    with SessionLocal() as db:
        application = db.get(Application, application_id)
        application.status = ApplicationStatus.COMPLETED
        application.deterministic_score = 62.5
        application.final_score = 62.5
        application.ai_status = "failed"
        application.component_scores = {
            "semantic": 50.0,
            "skills": 100.0,
            "title": 25.0,
            "experience": 50.0,
            "deterministic_total": 62.5,
        }
        db.commit()
    reviewed = client.get(
        f"/api/v1/admin/jobs/{job['id']}/applications",
        headers=auth(admin["access_token"]),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"][0]["applicant"]["email"] == "review.applicant@example.com"
    resume = client.get(
        f"/api/v1/admin/applications/{application_id}/resume",
        headers=auth(admin["access_token"]),
    )
    assert resume.status_code == 200
    assert resume.headers["content-type"].startswith("application/pdf")
    retried = client.post(
        f"/api/v1/admin/applications/{application_id}/retry-ai",
        headers=auth(admin["access_token"]),
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["data"]["ai_status"] == "processing"
