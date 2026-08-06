from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password
from tests.conftest import auth, login, register


JOB = {
    "title": "Commercial Platform Engineer",
    "description": "Build secure multi-tenant services for a commercial recruiting platform.",
    "required_skills": ["Python", "PostgreSQL"],
    "status": "open",
}


def test_workspace_subscription_settings_plan_export_and_quota(client):
    register(client, "employer", "commercial.owner@example.com", "Commercial Owner")
    owner = login(client, "commercial.owner@example.com")
    headers = auth(owner["access_token"])

    initial = client.get("/api/v1/workspace/saas", headers=headers)
    assert initial.status_code == 200, initial.text
    data = initial.json()["data"]
    assert data["subscription"]["plan_key"] == "starter"
    assert data["usage"]["active_jobs"] == {"used": 0, "limit": 3}
    assert set(data["plans"]) == {"starter", "growth", "scale"}

    updated = client.patch("/api/v1/workspace/settings", headers=headers, json={
        "name": "Commercial Hiring Labs",
        "timezone": "Asia/Karachi",
        "company_domain": "hiringlabs.example",
        "careers_url": "https://hiringlabs.example/careers",
        "primary_color": "#1455aa",
        "data_retention_days": 730,
        "candidate_email_notifications": True,
        "onboarding_completed": True,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["settings"]["data_retention_days"] == 730

    for index in range(3):
        payload = {**JOB, "title": f"Commercial Engineer {index}"}
        assert client.post("/api/v1/employer/jobs", headers=headers, json=payload).status_code == 201
    limited = client.post("/api/v1/employer/jobs", headers=headers, json={**JOB, "title": "Limit Exceeded"})
    assert limited.status_code == 402
    assert limited.json()["detail"]["code"] == "PLAN_LIMIT_REACHED"

    changed = client.post("/api/v1/workspace/billing/change-plan", headers=headers, json={"plan_key": "growth"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["status"] == "active"
    assert client.post("/api/v1/employer/jobs", headers=headers, json={**JOB, "title": "Growth Capacity"}).status_code == 201

    exported = client.get("/api/v1/workspace/data-export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["data"]["organization"]["name"] == "Commercial Hiring Labs"
    assert len(exported.json()["data"]["jobs"]) == 4


def test_commercial_controls_are_owner_scoped_and_admin_visible(client):
    register(client, "employer", "saas.owner@example.com", "SaaS Owner")
    register(client, "employer", "saas.viewer@example.com", "SaaS Viewer")
    owner = login(client, "saas.owner@example.com")
    viewer = login(client, "saas.viewer@example.com")
    owner_headers, viewer_headers = auth(owner["access_token"]), auth(viewer["access_token"])
    invited = client.post("/api/v1/workspace/team/invitations", headers=owner_headers, json={"email": "saas.viewer@example.com", "role": "viewer"})
    token = invited.json()["data"]["invitation_token"]
    assert client.post(f"/api/v1/workspace/team/invitations/{token}/accept", headers=viewer_headers).status_code == 200
    forbidden = client.patch("/api/v1/workspace/settings", headers=viewer_headers, json={
        "name": "Not Allowed", "timezone": "UTC", "primary_color": "#173fbf",
        "data_retention_days": 365, "candidate_email_notifications": True,
        "onboarding_completed": False,
    })
    assert forbidden.status_code == 403

    with SessionLocal() as db:
        db.add(User(email="commercial.admin@example.com", full_name="Commercial Admin", password_hash=hash_password("Password123!"), role=Role.ADMIN, email_verified=True))
        db.commit()
    administrator = login(client, "commercial.admin@example.com")
    overview = client.get("/api/v1/admin/saas/overview", headers=auth(administrator["access_token"]))
    assert overview.status_code == 200, overview.text
    assert overview.json()["data"]["organizations"] == 2
    assert overview.json()["data"]["active_subscriptions"] == 2


def test_billing_webhook_is_closed_when_not_configured(client):
    response = client.post("/api/v1/billing/webhooks/stripe", json={"id": "evt_test", "type": "subscription.updated"})
    assert response.status_code == 503
