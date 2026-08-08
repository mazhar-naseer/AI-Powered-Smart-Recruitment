"""Storage backend selection and the environment-seeded first administrator.

The suite pins ``USE_CLOUDINARY=false`` (see ``conftest``), so these build their
own ``Settings`` rather than relying on the ambient one.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.first_admin import AdminSeedError, ensure_first_admin
from app.object_storage import (
    CLOUDINARY_PREFIX,
    CloudinaryPrivateStorage,
    LocalPrivateStorage,
    build_storage,
)

CREDENTIALS = {
    "cloudinary_cloud_name": "test-cloud",
    "cloudinary_api_key": "123456789",
    "cloudinary_api_secret": "test-secret-value",
}


def cloudinary_settings(**overrides) -> Settings:
    return Settings(use_cloudinary=True, **CREDENTIALS, **overrides)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_cloudinary_without_credentials_is_rejected_at_startup():
    """A missing credential must stop the boot, not degrade to local disk."""
    with pytest.raises(ValidationError) as exc:
        Settings(use_cloudinary=True, cloudinary_cloud_name=None,
                 cloudinary_api_key=None, cloudinary_api_secret=None)
    message = str(exc.value)
    assert "CLOUDINARY_CLOUD_NAME" in message
    assert "CLOUDINARY_API_KEY" in message
    assert "CLOUDINARY_API_SECRET" in message


def test_partial_cloudinary_credentials_are_rejected():
    with pytest.raises(ValidationError) as exc:
        Settings(use_cloudinary=True, cloudinary_cloud_name="test-cloud",
                 cloudinary_api_key="123", cloudinary_api_secret=None)
    assert "CLOUDINARY_API_SECRET" in str(exc.value)


def test_credentials_are_not_required_when_the_flag_is_off():
    assert Settings(use_cloudinary=False).use_cloudinary is False


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #


def test_cloudinary_mode_selects_the_remote_backend_and_touches_no_disk(tmp_path):
    """The point of the flag: with it on, local directories are never created."""
    root = tmp_path / "never-created"
    storage = build_storage(cloudinary_settings(), "smarthire/resumes", "raw", root)
    assert isinstance(storage, CloudinaryPrivateStorage)
    assert not root.exists()


def test_local_mode_selects_the_local_backend(tmp_path):
    root = tmp_path / "resumes"
    storage = build_storage(Settings(use_cloudinary=False), "smarthire/resumes", "raw", root)
    assert isinstance(storage, LocalPrivateStorage)
    assert root.exists()


# --------------------------------------------------------------------------- #
# Cloudinary backend
# --------------------------------------------------------------------------- #


def test_resume_upload_goes_to_cloudinary_and_returns_a_prefixed_key(monkeypatch, tmp_path):
    import cloudinary.uploader

    root = tmp_path / "resumes"
    storage = CloudinaryPrivateStorage("smarthire/resumes", "raw", cloudinary_settings())
    captured = {}

    def fake_upload(file, **options):
        captured.update(options)
        return {"public_id": options["public_id"]}

    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    key = storage.put(b"%PDF-1.4 resume", ".pdf")

    assert key.startswith(CLOUDINARY_PREFIX)
    assert key.endswith(".pdf")
    assert captured["resource_type"] == "raw"
    # Authenticated, so the delivery URL is unusable without a signature.
    assert captured["type"] == "authenticated"
    assert captured["public_id"].startswith("smarthire/resumes/")
    assert not root.exists()


def test_avatar_key_carries_the_suffix_that_cloudinary_drops(monkeypatch):
    import cloudinary.uploader

    storage = CloudinaryPrivateStorage("smarthire/avatars", "image", cloudinary_settings())
    captured = {}

    def fake_upload(file, **options):
        captured.update(options)
        return {"public_id": options["public_id"]}

    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    key = storage.put(b"\x89PNG\r\n\x1a\n", ".PNG")

    # Cloudinary stores an image without the extension, so the key carries it
    # for MIME detection while the public_id sent upstream does not.
    assert not captured["public_id"].endswith(".png")
    assert key.endswith(".png")
    assert captured["resource_type"] == "image"
    assert "\\" not in key


def test_upload_failure_is_reported_as_oserror(monkeypatch):
    """Routes map OSError to 503; a raw Cloudinary error would become a 500."""
    import cloudinary.uploader

    storage = CloudinaryPrivateStorage("smarthire/resumes", "raw", cloudinary_settings())

    def fail(file, **options):
        raise RuntimeError("cloudinary is unreachable")

    monkeypatch.setattr(cloudinary.uploader, "upload", fail)
    with pytest.raises(OSError):
        storage.put(b"%PDF-1.4", ".pdf")


@pytest.mark.parametrize("resource_type", ["raw", "image"])
def test_local_keys_are_rejected_in_strict_cloudinary_mode(resource_type, tmp_path):
    """A pre-switch local key must 404 rather than read off the volume."""
    storage = CloudinaryPrivateStorage("smarthire/resumes", resource_type, cloudinary_settings())
    stray = tmp_path / "leftover.pdf"
    stray.write_bytes(b"%PDF-1.4 local")

    with pytest.raises(FileNotFoundError):
        storage.read(f"{uuid.uuid4().hex}.pdf")
    with pytest.raises(FileNotFoundError):
        storage.read(str(stray))
    # The file is left alone, not deleted, when a local key reaches this backend.
    storage.delete(str(stray))
    assert stray.exists()


def test_read_uses_the_signed_download_api_not_the_cdn(monkeypatch):
    """Delivery URLs 401 on authenticated raw assets; the download API does not."""
    storage = CloudinaryPrivateStorage("smarthire/resumes", "raw", cloudinary_settings())
    key = f"{CLOUDINARY_PREFIX}smarthire/resumes/{uuid.uuid4().hex}.pdf"

    url = storage._download_url(key)
    assert url.startswith("https://api.cloudinary.com/")
    assert "/raw/download?" in url
    assert "signature=" in url and "api_key=" in url
    # res.cloudinary.com is the delivery host that rejected these in production.
    assert "res.cloudinary.com" not in url


def test_avatar_download_url_passes_the_format_separately():
    """Cloudinary strips an image's extension, so it must be sent as `format`."""
    storage = CloudinaryPrivateStorage("smarthire/avatars", "image", cloudinary_settings())
    url = storage._download_url(f"{CLOUDINARY_PREFIX}smarthire/avatars/abc.png")
    assert "/image/download?" in url
    assert "format=png" in url


@pytest.mark.parametrize(("status", "missing"), [(404, True), (401, False), (500, False)])
def test_download_http_errors_map_to_the_right_exception(monkeypatch, status, missing):
    """A 401 must not be reported as a missing file — that was the prod symptom."""
    from urllib.error import HTTPError

    import app.object_storage as module

    storage = CloudinaryPrivateStorage("smarthire/resumes", "raw", cloudinary_settings())

    def fail(url, timeout=None):
        raise HTTPError(url, status, "boom", {}, None)

    monkeypatch.setattr(module, "urlopen", fail)
    with pytest.raises(OSError) as exc:  # noqa: PT011 - narrowed by the assert below
        storage.read(f"{CLOUDINARY_PREFIX}smarthire/resumes/{uuid.uuid4().hex}.pdf")
    # FileNotFoundError subclasses OSError, so the branch has to be asserted
    # explicitly or a 401 regressing to a 404 would still pass.
    assert isinstance(exc.value, FileNotFoundError) is missing


def test_open_yields_a_real_path_for_the_parser(monkeypatch):
    """The parser needs a file; a remote object is downloaded to a temp path."""
    storage = CloudinaryPrivateStorage("smarthire/resumes", "raw", cloudinary_settings())
    monkeypatch.setattr(storage, "read", lambda key: b"%PDF-1.4 downloaded")

    key = f"{CLOUDINARY_PREFIX}smarthire/resumes/{uuid.uuid4().hex}.pdf"
    with storage.open(key) as path:
        assert path.is_file()
        assert path.read_bytes() == b"%PDF-1.4 downloaded"
        leaked = path
    # The temporary directory is removed on exit.
    assert not leaked.exists()


# --------------------------------------------------------------------------- #
# Local backend
# --------------------------------------------------------------------------- #


def test_local_round_trip_and_traversal_guard(tmp_path):
    storage = LocalPrivateStorage(tmp_path / "resumes")
    key = storage.put(b"%PDF-1.4 local", ".PDF")

    assert "/" not in key and "\\" not in key
    assert key.endswith(".pdf")
    assert storage.read(key) == b"%PDF-1.4 local"
    with storage.open(key) as path:
        assert path.is_file()

    outside = tmp_path / "secret.pdf"
    outside.write_bytes(b"not yours")
    with pytest.raises(FileNotFoundError):
        storage.read(str(outside))

    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.read(key)


def test_local_put_recreates_a_root_removed_underneath_it(tmp_path):
    """An ephemeral volume can lose the directory while the process runs."""
    root = tmp_path / "resumes"
    storage = LocalPrivateStorage(root)
    root.rmdir()
    assert storage.read(storage.put(b"content", ".pdf")) == b"content"


# --------------------------------------------------------------------------- #
# First administrator
# --------------------------------------------------------------------------- #

SEED = {"admin_email": "root@example.com", "admin_password": "Str0ng!Passw0rd",
        "admin_full_name": "Platform Root"}


def test_first_admin_is_seeded_then_never_reseeded(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Role, User

    settings = Settings(**SEED)
    created = ensure_first_admin(settings)
    assert created is not None
    assert created.role == Role.ADMIN
    assert created.email_verified is True

    # Second call is a no-op: an administrator already exists.
    assert ensure_first_admin(settings) is None
    with SessionLocal() as db:
        admins = db.scalars(select(User).where(User.role == Role.ADMIN)).all()
    assert len(admins) == 1


def test_seeded_admin_can_log_in_and_create_another_admin(client):
    ensure_first_admin(Settings(**SEED))

    login = client.post("/api/v1/auth/login",
                        json={"email": SEED["admin_email"], "password": SEED["admin_password"]})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    created = client.post(
        "/api/v1/admin/users/admin",
        headers=headers,
        json={"full_name": "Second Admin", "email": "second@example.com",
              "password": "An0ther!Str0ng"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["role"] == "admin"


def test_seeding_is_skipped_when_unset_and_rejected_when_half_configured():
    assert ensure_first_admin(Settings()) is None
    with pytest.raises(AdminSeedError):
        ensure_first_admin(Settings(admin_email="root@example.com"))
    with pytest.raises(AdminSeedError):
        ensure_first_admin(Settings(admin_password="Str0ng!Passw0rd"))


def test_weak_seed_password_fails_the_boot():
    """The seeded account may not be weaker than an API-created one."""
    with pytest.raises(AdminSeedError):
        ensure_first_admin(Settings(admin_email="root@example.com", admin_password="short"))


def test_seeding_never_promotes_an_existing_account(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Role, User
    from app.security import hash_password

    with SessionLocal() as db:
        db.add(User(email="existing@example.com", full_name="Existing Person",
                    password_hash=hash_password("Password123!"), role=Role.APPLICANT,
                    email_verified=True))
        db.commit()

    assert ensure_first_admin(
        Settings(admin_email="existing@example.com", admin_password="Str0ng!Passw0rd")
    ) is None
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "existing@example.com"))
    # An env var must not be able to take over an account that already exists.
    assert user.role == Role.APPLICANT
