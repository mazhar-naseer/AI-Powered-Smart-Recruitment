from tests.conftest import auth, login, register


def test_registration_login_refresh_logout_and_me(client):
    register(client, "applicant", "applicant@example.com")
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Again",
            "email": "APPLICANT@example.com",
            "password": "Password123!",
            "role": "applicant",
        },
    )
    assert duplicate.status_code == 409
    tokens = login(client, "applicant@example.com")
    me = client.get("/api/v1/auth/me", headers=auth(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["data"]["role"] == "applicant"
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": refreshed.json()["data"]["refresh_token"]}
        ).status_code
        == 200
    )


def test_admin_cannot_self_register(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Admin",
            "email": "admin@example.com",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_job_crud_visibility_and_ownership(client):
    register(client, "employer", "owner@example.com", "Owner")
    register(client, "employer", "other@example.com", "Other")
    register(client, "applicant", "candidate@example.com", "Candidate")
    owner = login(client, "owner@example.com")
    other = login(client, "other@example.com")
    applicant = login(client, "candidate@example.com")
    payload = {
        "title": "Python Developer",
        "description": "Build reliable production FastAPI services.",
        "required_skills": ["Python", "FastAPI", "SQL"],
        "location": "Lahore",
        "status": "open",
    }
    created = client.post(
        "/api/v1/employer/jobs", json=payload, headers=auth(owner["access_token"])
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["data"]["id"]
    assert (
        client.patch(
            f"/api/v1/employer/jobs/{job_id}",
            json={"status": "closed"},
            headers=auth(other["access_token"]),
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/employer/jobs/{job_id}",
            json={"status": "closed"},
            headers=auth(owner["access_token"]),
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/jobs/{job_id}", headers=auth(applicant["access_token"])).status_code
        == 404
    )
    updated = client.patch(
        f"/api/v1/employer/jobs/{job_id}",
        json={"status": "open"},
        headers=auth(owner["access_token"]),
    )
    assert updated.status_code == 200
    listing = client.get("/api/v1/jobs?q=python", headers=auth(applicant["access_token"]))
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1


def test_role_boundaries(client):
    register(client, "applicant", "applicant@example.com")
    applicant = login(client, "applicant@example.com")
    assert (
        client.get(
            "/api/v1/employer/dashboard", headers=auth(applicant["access_token"])
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/dashboard", headers=auth(applicant["access_token"])).status_code
        == 403
    )
