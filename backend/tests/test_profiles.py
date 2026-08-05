from tests.conftest import auth, login, register


def test_applicant_can_update_comprehensive_profile(client):
    register(client, "applicant", "profile.applicant@example.com", "Alex Applicant")
    token = login(client, "profile.applicant@example.com")["access_token"]
    response = client.patch(
        "/api/v1/profiles/me",
        headers=auth(token),
        json={
            "headline": "Senior Backend Engineer",
            "phone": "+92 300 1234567",
            "bio": "Backend engineer focused on reliable hiring platforms.",
            "location": "Lahore, Pakistan",
            "skills": ["Python", "FastAPI", "Python", "  PostgreSQL  "],
            "languages": ["English", "Urdu"],
            "education": ["BS Computer Science"],
            "years_experience": 7,
            "availability": "Open to opportunities",
            "preferred_work_mode": "Hybrid",
            "portfolio_url": "https://portfolio.example.com",
            "linkedin_url": "https://linkedin.com/in/alex",
            "github_url": "https://github.com/alex",
        },
    )
    assert response.status_code == 200, response.text
    profile = response.json()["data"]
    assert profile["skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert profile["years_experience"] == 7
    assert profile["preferred_work_mode"] == "Hybrid"


def test_employer_can_update_company_profile(client):
    register(client, "employer", "profile.employer@example.com", "Erin Employer")
    token = login(client, "profile.employer@example.com")["access_token"]
    response = client.patch(
        "/api/v1/profiles/me",
        headers=auth(token),
        json={
            "company_name": "SmartHire Labs",
            "industry": "Recruitment Technology",
            "company_size": "51–200 employees",
            "founded_year": 2024,
            "company_website": "https://smarthire.example.com",
            "company_description": "Evidence-driven recruitment technology.",
            "skills": ["Engineering", "Recruitment"],
            "languages": ["English"],
        },
    )
    assert response.status_code == 200, response.text
    profile = response.json()["data"]
    assert profile["industry"] == "Recruitment Technology"
    assert profile["founded_year"] == 2024


def test_profile_photo_upload_is_private_and_validated(client):
    register(client, "applicant", "avatar.applicant@example.com", "Avery Avatar")
    token = login(client, "avatar.applicant@example.com")["access_token"]
    headers = auth(token)
    invalid = client.post(
        "/api/v1/profiles/me/avatar", headers=headers, files={"avatar": ("avatar.txt", b"not an image", "text/plain")}
    )
    assert invalid.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"profile-image-content"
    uploaded = client.post(
        "/api/v1/profiles/me/avatar", headers=headers, files={"avatar": ("avatar.png", png, "image/png")}
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["data"]["avatar_url"] == "/api/v1/profiles/me/avatar"
    assert client.get("/api/v1/profiles/me/avatar").status_code == 401
    viewed = client.get("/api/v1/profiles/me/avatar", headers=headers)
    assert viewed.status_code == 200
    assert viewed.headers["content-type"] == "image/png"
    assert viewed.content == png
