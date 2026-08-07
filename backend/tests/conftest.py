import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_smarthire.db"
os.environ["RESUME_STORAGE_PATH"] = "./test_storage"
os.environ["AVATAR_STORAGE_PATH"] = "./test_avatars"
os.environ["SECRET_KEY"] = "test-secret-key-long-enough-for-tests"
os.environ["ENVIRONMENT"] = "development"
# Settings reads ../.env, so anything left unpinned here leaks a developer's
# real credentials into the suite and sends live traffic to third parties.
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["BREVO_API_KEY"] = ""
os.environ["USE_CLOUDINARY"] = "false"
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    storage = Path("test_storage")
    if storage.exists():
        for item in storage.iterdir():
            item.unlink()
        storage.rmdir()
    avatars = Path("test_avatars")
    if avatars.exists():
        for item in avatars.iterdir():
            item.unlink()
        avatars.rmdir()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, role: str, email: str, name: str = "Test User") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "Password123!",
            "role": role,
            "company_name": "Test Corp" if role == "employer" else None,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    verify = client.post("/api/v1/auth/verify-email", json={"email": email, "code": data["dev_verification_code"]})
    assert verify.status_code == 200, verify.text
    return data


def login(client: TestClient, email: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
