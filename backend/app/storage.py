"""File storage abstraction.

Two backends are supported:

* ``local`` — writes to ``resume_storage_path`` / ``avatar_storage_path``. Used for
  development and for any host that provides a persistent disk.
* ``cloudinary`` — uploads to Cloudinary. Required on hosts with an ephemeral
  filesystem, where local writes are lost on every redeploy, restart, or idle
  spin-down.

Storage keys are opaque strings. Cloudinary keys carry a ``cloudinary:`` prefix so
records created under either backend keep working after a switch.

Resume bytes are always streamed back through the API rather than handed out as a
public URL, preserving the rule that only the owning employer may download a
resume. Cloudinary resumes are uploaded as authenticated raw resources, so the
delivery URL is unusable without a signature even if it leaks.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from urllib.request import urlopen

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

CLOUDINARY_PREFIX = "cloudinary:"
RESUME_FOLDER = "smarthire/resumes"
AVATAR_FOLDER = "smarthire/avatars"


class StorageError(RuntimeError):
    """Raised when a file cannot be stored or retrieved."""


def _cloudinary_enabled(settings: Settings) -> bool:
    return bool(
        settings.use_cloudinary
        and settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    )


def _configure(settings: Settings):
    # cloudinary's __init__ does not pull in its submodules, so `import
    # cloudinary` alone leaves cloudinary.uploader and cloudinary.utils
    # unbound. Every call site here reaches for one of the two.
    import cloudinary
    import cloudinary.uploader  # noqa: F401
    import cloudinary.utils  # noqa: F401

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    return cloudinary


def is_remote(storage_key: str) -> bool:
    return storage_key.startswith(CLOUDINARY_PREFIX)


def _public_id(storage_key: str) -> str:
    return storage_key[len(CLOUDINARY_PREFIX) :]


def _signed_url(settings: Settings, public_id: str, resource_type: str) -> str:
    cloudinary = _configure(settings)
    url, _options = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type=resource_type,
        type="authenticated",
        sign_url=True,
        secure=True,
    )
    return url


# --------------------------------------------------------------------------- #
# Resumes
# --------------------------------------------------------------------------- #


def save_resume(content: bytes, suffix: str, settings: Settings | None = None) -> str:
    """Persist resume bytes and return an opaque storage key."""
    settings = settings or get_settings()
    if _cloudinary_enabled(settings):
        cloudinary = _configure(settings)
        public_id = f"{RESUME_FOLDER}/{uuid.uuid4()}{suffix}"
        try:
            result = cloudinary.uploader.upload(
                BytesIO(content),
                public_id=public_id,
                resource_type="raw",
                type="authenticated",
                overwrite=False,
            )
        except Exception as exc:  # pragma: no cover - network failure path
            raise StorageError(f"Resume upload failed: {exc}") from exc
        return f"{CLOUDINARY_PREFIX}{result['public_id']}"

    storage = settings.resume_storage_path.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    destination = storage / f"{uuid.uuid4()}{suffix}"
    destination.write_bytes(content)
    return str(destination)


def read_resume(storage_key: str, settings: Settings | None = None) -> bytes:
    """Return resume bytes, or raise :class:`StorageError` if unavailable."""
    settings = settings or get_settings()
    if is_remote(storage_key):
        url = _signed_url(settings, _public_id(storage_key), "raw")
        try:
            with urlopen(url, timeout=30) as response:  # noqa: S310 - signed Cloudinary URL
                return response.read()
        except Exception as exc:
            raise StorageError(f"Resume could not be retrieved: {exc}") from exc

    path = Path(storage_key)
    if not path.is_file():
        raise StorageError("Resume file not found")
    return path.read_bytes()


@contextmanager
def resume_on_disk(storage_key: str, settings: Settings | None = None) -> Iterator[Path]:
    """Yield a local path to the resume, downloading it first when remote.

    Local files are yielded in place; remote files are written to a temporary
    directory that is removed on exit.
    """
    settings = settings or get_settings()
    if not is_remote(storage_key):
        path = Path(storage_key)
        if not path.is_file():
            raise StorageError("Resume file not found")
        yield path
        return

    content = read_resume(storage_key, settings)
    suffix = Path(_public_id(storage_key)).suffix or ".pdf"
    with TemporaryDirectory() as directory:
        path = Path(directory) / f"resume{suffix}"
        path.write_bytes(content)
        yield path


def delete_resume(storage_key: str, settings: Settings | None = None) -> None:
    """Best-effort delete. Never raises — callers are usually in an error path."""
    settings = settings or get_settings()
    try:
        if is_remote(storage_key):
            cloudinary = _configure(settings)
            cloudinary.uploader.destroy(
                _public_id(storage_key), resource_type="raw", type="authenticated"
            )
        else:
            Path(storage_key).unlink(missing_ok=True)
    except Exception:
        logger.warning("Could not delete resume %s", storage_key, exc_info=True)


# --------------------------------------------------------------------------- #
# Avatars
# --------------------------------------------------------------------------- #


def save_avatar(
    content: bytes, user_id: str, suffix: str, settings: Settings | None = None
) -> str:
    settings = settings or get_settings()
    if _cloudinary_enabled(settings):
        cloudinary = _configure(settings)
        public_id = f"{AVATAR_FOLDER}/{user_id}-{uuid.uuid4().hex}"
        try:
            result = cloudinary.uploader.upload(
                BytesIO(content),
                public_id=public_id,
                resource_type="image",
                type="authenticated",
                overwrite=False,
            )
        except Exception as exc:  # pragma: no cover - network failure path
            raise StorageError(f"Profile photo upload failed: {exc}") from exc
        return f"{CLOUDINARY_PREFIX}{result['public_id']}{suffix}"

    storage = settings.avatar_storage_path.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    destination = storage / f"{user_id}-{uuid.uuid4().hex}{suffix}"
    destination.write_bytes(content)
    return str(destination)


def read_avatar(storage_key: str, settings: Settings | None = None) -> bytes:
    settings = settings or get_settings()
    if is_remote(storage_key):
        public_id = _public_id(storage_key)
        # The suffix is carried for MIME detection only; Cloudinary stores the
        # image under the public_id without it.
        public_id = str(Path(public_id).with_suffix(""))
        url = _signed_url(settings, public_id.replace("\\", "/"), "image")
        try:
            with urlopen(url, timeout=30) as response:  # noqa: S310 - signed Cloudinary URL
                return response.read()
        except Exception as exc:
            raise StorageError(f"Profile photo could not be retrieved: {exc}") from exc

    path = Path(storage_key)
    if not path.is_file():
        raise StorageError("Profile photo not found")
    if path.resolve().parent != settings.avatar_storage_path.resolve():
        raise StorageError("Profile photo not found")
    return path.read_bytes()


def delete_avatar(storage_key: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    try:
        if is_remote(storage_key):
            cloudinary = _configure(settings)
            public_id = str(Path(_public_id(storage_key)).with_suffix("")).replace("\\", "/")
            cloudinary.uploader.destroy(
                public_id, resource_type="image", type="authenticated"
            )
        else:
            path = Path(storage_key)
            if path.resolve().parent == settings.avatar_storage_path.resolve():
                path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Could not delete avatar %s", storage_key, exc_info=True)


def avatar_media_type(storage_key: str) -> str:
    suffix = Path(storage_key).suffix.lower()
    return mimetypes.types_map.get(suffix, "image/jpeg")
