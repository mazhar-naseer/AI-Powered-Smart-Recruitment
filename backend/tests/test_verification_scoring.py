from app.scoring import detailed_score, hybrid_score
from app.resume_processing import sanitize_extracted_text


def test_unverified_user_cannot_login_and_code_verifies(client):
    created = client.post("/api/v1/auth/register", json={
        "full_name": "Candidate", "email": "candidate@example.com",
        "password": "Password123!", "role": "applicant",
    })
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["verification_required"] is True
    blocked = client.post("/api/v1/auth/login", json={"email": "candidate@example.com", "password": "Password123!"})
    assert blocked.status_code == 403
    verified = client.post("/api/v1/auth/verify-email", json={
        "email": "candidate@example.com", "code": data["dev_verification_code"],
    })
    assert verified.status_code == 200
    auth = verified.json()["data"]
    assert auth["user"]["email_verified"] is True
    assert auth["access_token"]
    assert auth["refresh_token"]
    replay = client.post("/api/v1/auth/verify-email", json={
        "email": "candidate@example.com", "code": data["dev_verification_code"],
    })
    assert replay.status_code == 400


def test_hybrid_score_is_explainable_and_rewards_evidence():
    score, matched, parts = detailed_score(
        "Senior Python FastAPI engineer with 6 years experience building PostgreSQL APIs",
        "Senior Backend Engineer", "Build Python APIs using FastAPI and PostgreSQL",
        ["Python", "FastAPI", "PostgreSQL"], "Senior",
    )
    assert score >= 60
    assert matched == ["Python", "FastAPI", "PostgreSQL"]
    assert set(parts) == {"semantic", "skills", "title", "experience"}


def test_pdf_text_sanitizer_removes_postgres_invalid_control_bytes():
    dirty = "Real-\x00time Python\nFastAPI\x01 engineer\tPostgreSQL"
    clean = sanitize_extracted_text(dirty)
    assert clean == "Real-time Python\nFastAPI engineer\tPostgreSQL"
    assert "\x00" not in clean


def test_hybrid_score_limits_ai_by_confidence_and_flags_disagreement():
    score, meta = hybrid_score(42, 92, 0.8, maximum_ai_weight=0.35, disagreement_threshold=25)
    assert score == 56.0
    assert meta["deterministic_weight"] == 72.0
    assert meta["ai_weight"] == 28.0
    assert meta["manual_review_required"] is True


def test_hybrid_score_uses_less_ai_weight_when_confidence_is_low():
    score, meta = hybrid_score(60, 90, 0.2, maximum_ai_weight=0.35)
    assert score == 62.1
    assert meta["ai_weight"] == 7.0
