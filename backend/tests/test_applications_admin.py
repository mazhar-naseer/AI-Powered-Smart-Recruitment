from app.database import SessionLocal
from app.models import Role, User
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
    monkeypatch.setattr("app.api.process_application", lambda application_id: None)
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
