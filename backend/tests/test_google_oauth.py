from urllib.parse import parse_qs, urlparse

from app import oauth_api
from app.database import SessionLocal
from app.models import SocialIdentity, User
from sqlalchemy import select


def configure_google(monkeypatch):
    monkeypatch.setattr(oauth_api.settings, "google_oauth_enabled", True)
    monkeypatch.setattr(oauth_api.settings, "google_client_id", "google-client-test")
    monkeypatch.setattr(oauth_api.settings, "google_client_secret", "google-secret-test")
    monkeypatch.setattr(oauth_api.settings, "google_redirect_uri", "http://127.0.0.1:8000/api/v1/auth/oauth/google/callback")


def begin(client, intent="register", role="applicant"):
    response = client.get(
        "/api/v1/auth/oauth/google/start",
        params={"intent": intent, "role": role, "return_to": "http://localhost:5173"},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    query = parse_qs(urlparse(location).query)
    assert query["code_challenge_method"] == ["S256"]
    return query["state"][0]


def callback_code(client, state):
    response = client.get(
        "/api/v1/auth/oauth/google/callback",
        params={"state": state, "code": "google-authorization-code"},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["code"][0]


def test_google_registration_uses_pkce_one_time_handoff_and_selected_role(client, monkeypatch):
    configure_google(monkeypatch)
    monkeypatch.setattr(oauth_api, "fetch_google_identity", lambda code, verifier: {
        "sub": "google-subject-new", "email": "google.new@example.com",
        "email_verified": True, "name": "Google Applicant",
    })
    providers = client.get("/api/v1/auth/oauth/providers").json()["data"]
    assert providers["google"]["enabled"] is True
    state = begin(client, role="applicant")
    code = callback_code(client, state)
    exchange = client.post("/api/v1/auth/oauth/exchange", json={"code": code})
    assert exchange.status_code == 200, exchange.text
    assert exchange.json()["data"]["user"]["role"] == "applicant"
    assert exchange.json()["data"]["user"]["email_verified"] is True
    assert client.post("/api/v1/auth/oauth/exchange", json={"code": code}).status_code == 400
    assert client.get("/api/v1/auth/oauth/google/callback", params={"state": state, "code": "replay"}, follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "google.new@example.com"))
        identity = db.scalar(select(SocialIdentity).where(SocialIdentity.user_id == user.id))
        assert identity.provider_subject == "google-subject-new"


def test_google_login_does_not_silently_create_unregistered_account(client, monkeypatch):
    configure_google(monkeypatch)
    monkeypatch.setattr(oauth_api, "fetch_google_identity", lambda code, verifier: {
        "sub": "unknown-google-subject", "email": "not.registered@example.com",
        "email_verified": True, "name": "Unknown User",
    })
    state = begin(client, intent="login")
    response = client.get("/api/v1/auth/oauth/google/callback", params={"state": state, "code": "valid-code"}, follow_redirects=False)
    assert response.status_code == 303
    error = parse_qs(urlparse(response.headers["location"]).query)["error"][0]
    assert "register first" in error


def test_google_provider_is_hidden_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(oauth_api.settings, "google_oauth_enabled", False)
    providers = client.get("/api/v1/auth/oauth/providers").json()["data"]
    assert providers["google"]["enabled"] is False


def test_development_callback_accepts_current_local_vite_port():
    assert oauth_api.safe_return_to("http://127.0.0.1:5176") == "http://127.0.0.1:5176"
