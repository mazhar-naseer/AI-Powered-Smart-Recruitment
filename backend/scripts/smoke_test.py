"""Run a non-destructive local end-to-end smoke test with labeled test accounts."""
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000/api/v1"
PASSWORD = "SmartHireTest123!"


def login(client: httpx.Client, email: str) -> str:
    response = client.post(f"{BASE_URL}/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    resume_path = Path(__file__).parents[2] / "Backend_Design_Document_5_Pages.pdf"
    with httpx.Client(timeout=40) as client:
        health = client.get("http://localhost:8000//health")
        health.raise_for_status()
        tokens = {
            role: login(client, f"{role}.test@example.com")
            for role in ("admin", "employer", "applicant")
        }
        for role, token in tokens.items():
            me = client.get(f"{BASE_URL}/auth/me", headers=headers(token))
            assert me.status_code == 200 and me.json()["data"]["role"] == role

        title = f"Backend Engineer Smoke Test {datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        created = client.post(
            f"{BASE_URL}/employer/jobs",
            headers=headers(tokens["employer"]),
            json={
                "title": title,
                "description": "Build production FastAPI services backed by PostgreSQL with secure APIs.",
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
                "location": "Remote",
                "employment_type": "Full-time",
                "experience_level": "Mid-level",
                "status": "open",
            },
        )
        created.raise_for_status()
        job_id = created.json()["data"]["id"]

        jobs = client.get(f"{BASE_URL}/jobs", headers=headers(tokens["applicant"]))
        assert jobs.status_code == 200
        assert any(job["id"] == job_id for job in jobs.json()["data"]["items"])

        with resume_path.open("rb") as resume:
            applied = client.post(
                f"{BASE_URL}/jobs/{job_id}/applications",
                headers=headers(tokens["applicant"]),
                files={"resume": ("test-resume.pdf", resume, "application/pdf")},
            )
        assert applied.status_code == 202, applied.text
        application_id = applied.json()["data"]["id"]

        status = "processing"
        for _ in range(20):
            applications = client.get(
                f"{BASE_URL}/applicant/applications", headers=headers(tokens["applicant"])
            )
            applications.raise_for_status()
            application = next(
                item for item in applications.json()["data"] if item["id"] == application_id
            )
            status = application["status"]
            if status != "processing":
                break
            time.sleep(0.25)
        assert status == "completed", application
        assert application["component_scores"]
        assert application["ai_summary"]

        ranked = client.get(
            f"{BASE_URL}/employer/jobs/{job_id}/applications",
            headers=headers(tokens["employer"]),
        )
        assert ranked.status_code == 200 and ranked.json()["data"][0]["id"] == application_id

        dashboard = client.get(
            f"{BASE_URL}/admin/dashboard", headers=headers(tokens["admin"])
        )
        assert dashboard.status_code == 200
        forbidden = client.get(
            f"{BASE_URL}/admin/dashboard", headers=headers(tokens["applicant"])
        )
        assert forbidden.status_code == 403
        print("health=passed")
        print("postgres_auth_and_roles=passed")
        print("job_create_and_listing=passed")
        print("pdf_upload_and_resume_processing=passed")
        print("employer_ranking=passed")
        print("admin_dashboard_and_rbac=passed")
        print(f"resume_match_status={status}")


if __name__ == "__main__":
    main()
