from app.database import SessionLocal
from app.models import AuditLog, Role, User
from app.security import hash_password
from tests.conftest import auth, login, register


def create_admin():
    with SessionLocal() as db:
        db.add(User(email="governance.admin@example.com", full_name="Governance Admin",
                    password_hash=hash_password("Password123!"), role=Role.ADMIN,
                    email_verified=True))
        db.commit()


def test_admin_governance_controls_are_audited(client):
    register(client, "employer", "owner@example.com", "Workspace Owner")
    register(client, "employer", "recruiter@example.com", "New Recruiter")
    create_admin()
    administrator = login(client, "governance.admin@example.com")
    headers = auth(administrator["access_token"])

    overview = client.get("/api/v1/admin/governance/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    organizations = overview.json()["data"]["organizations"]
    organization = next(item for item in organizations if any(member["user"]["email"] == "owner@example.com" for member in item["members"]))

    with SessionLocal() as db:
        recruiter = db.query(User).filter(User.email == "recruiter@example.com").one()
        recruiter_id = recruiter.id

    assigned = client.post(
        f"/api/v1/admin/governance/organizations/{organization['id']}/members",
        headers=headers, json={"user_id": recruiter_id, "role": "recruiter"},
    )
    assert assigned.status_code == 201, assigned.text

    subscription = client.patch(
        f"/api/v1/admin/governance/organizations/{organization['id']}/subscription",
        headers=headers, json={"plan_key": "growth", "status": "active", "confirmation": organization["name"]},
    )
    assert subscription.status_code == 200, subscription.text
    assert subscription.json()["data"]["plan_key"] == "growth"

    suspended = client.patch(
        f"/api/v1/admin/governance/organizations/{organization['id']}/status",
        headers=headers, json={"status": "suspended", "confirmation": organization["name"]},
    )
    assert suspended.status_code == 200, suspended.text

    audit = client.get("/api/v1/admin/governance/audit?action=governance", headers=headers)
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["data"]}
    assert {"governance.membership_assigned", "governance.subscription_changed", "governance.organization_suspended"} <= actions


def test_platform_role_change_requires_exact_confirmation_and_blocks_self(client):
    register(client, "applicant", "candidate@example.com", "Candidate User")
    create_admin()
    administrator = login(client, "governance.admin@example.com")
    headers = auth(administrator["access_token"])
    with SessionLocal() as db:
        candidate = db.query(User).filter(User.email == "candidate@example.com").one()
        candidate_id = candidate.id

    rejected = client.patch(f"/api/v1/admin/governance/users/{candidate_id}/role", headers=headers, json={"role": "employer", "confirmation": "wrong"})
    assert rejected.status_code == 422
    changed = client.patch(f"/api/v1/admin/governance/users/{candidate_id}/role", headers=headers, json={"role": "employer", "confirmation": "candidate@example.com"})
    assert changed.status_code == 200, changed.text
    own = client.patch(f"/api/v1/admin/governance/users/{administrator['user']['id']}/role", headers=headers, json={"role": "applicant", "confirmation": "governance.admin@example.com"})
    assert own.status_code == 409
