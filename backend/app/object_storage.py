"""Private object storage boundary.

Two backends sit behind one interface, selected by ``USE_CLOUDINARY``:

* ``LocalPrivateStorage`` — writes under ``resume_storage_path`` /
  ``avatar_storage_path``. Used for development and any host with a persistent
  disk.
* ``CloudinaryPrivateStorage`` — uploads to Cloudinary as *authenticated*
  resources. Required on hosts with an ephemeral filesystem, where local writes
  are lost on every redeploy, restart, and idle spin-down.

When Cloudinary is enabled it is the only store consulted: nothing is written to
local disk, and a key that is not a Cloudinary key is rejected rather than read
off the volume.

Keys are opaque; callers never build filesystem paths. Cloudinary keys carry a
``cloudinary:`` prefix so the two forms stay distinguishable.

Bytes are always streamed back through the API rather than handed out as a public
URL, preserving the rule that only the owning employer may download a resume.
Cloudinary resumes upload as authenticated raw resources, so the delivery URL is
unusable without a signature even if it leaks.

Failures are reported as ``FileNotFoundError`` when an object is absent and
``OSError`` when the store itself is unreachable, so both backends present the
same contract to the routes.
"""

import mimetypes
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import urlopen

from app.config import Settings, get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

CLOUDINARY_PREFIX = "cloudinary:"
RESUME_FOLDER = "smarthire/resumes"
AVATAR_FOLDER = "smarthire/avatars"


class LocalPrivateStorage:
    """Stores objects on the local filesystem under a fixed root."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4().hex}{suffix.lower()}"
        try:
            # Re-created per write: the root can disappear under a running
            # process on an ephemeral volume, and a one-time mkdir at startup
            # would not survive that.
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / key).write_bytes(content)
        except OSError:
            # A full or read-only volume is an infrastructure fault, not a bad
            # request. Re-raised so the caller still fails, but recorded here
            # because only this layer knows the target directory.
            logger.exception("Storage write failed for %s in %s", key, self.root)
            raise
        logger.debug("Stored object %s (%d bytes)", key, len(content))
        return key

    def _path(self, key: str) -> Path:
        raw = Path(key)
        candidate = (raw if raw.is_absolute() else self.root / raw.name).resolve()
        if candidate.parent != self.root:
            # Escaping the root means a traversal attempt or a corrupted key.
            # Worth an explicit record, unlike a merely absent file.
            logger.warning("Rejected storage key outside root: %r", key)
            raise FileNotFoundError(key)
        if not candidate.is_file():
            logger.warning("Storage key not found on disk: %s", candidate.name)
            raise FileNotFoundError(key)
        return candidate

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    @contextmanager
    def open(self, key: str) -> Iterator[Path]:
        """Yield a real path to the object. Local files are yielded in place."""
        yield self._path(key)

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            logger.debug("Delete skipped, object already gone: %s", key)
        except OSError:
            logger.exception("Could not delete object %s", key)


class CloudinaryPrivateStorage:
    """Stores objects on Cloudinary as authenticated resources.

    ``resource_type`` differs per folder: resumes upload as ``raw`` so the bytes
    come back verbatim, avatars as ``image``. Cloudinary drops the extension from
    an image's public_id, so the suffix is carried on the key for MIME detection
    and stripped again before every API call.
    """

    def __init__(self, folder: str, resource_type: str, settings: Settings):
        self.folder = folder
        self.resource_type = resource_type
        self.settings = settings

    def _configure(self):
        # cloudinary's __init__ does not pull in its submodules, so `import
        # cloudinary` alone leaves cloudinary.uploader and cloudinary.utils
        # unbound. Every call site here reaches for one of the two.
        import cloudinary
        import cloudinary.uploader  # noqa: F401
        import cloudinary.utils  # noqa: F401

        cloudinary.config(
            cloud_name=self.settings.cloudinary_cloud_name,
            api_key=self.settings.cloudinary_api_key,
            api_secret=self.settings.cloudinary_api_secret,
            secure=True,
        )
        return cloudinary

    def _public_id(self, key: str) -> str:
        """Strip the prefix, and the suffix that Cloudinary does not store."""
        if not key.startswith(CLOUDINARY_PREFIX):
            # Strict mode: a local key here means the row predates the switch and
            # its bytes live on a volume this backend must not touch.
            logger.warning("Rejected non-Cloudinary storage key: %r", key)
            raise FileNotFoundError(key)
        public_id = key[len(CLOUDINARY_PREFIX) :]
        if self.resource_type == "image":
            public_id = public_id.removesuffix(Path(public_id).suffix)
        return public_id

    def put(self, content: bytes, suffix: str) -> str:
        cloudinary = self._configure()
        suffix = suffix.lower()
        # raw keeps the extension in the public_id; image does not, so it is
        # appended to the returned key instead.
        stem = f"{self.folder}/{uuid.uuid4().hex}"
        public_id = stem if self.resource_type == "image" else f"{stem}{suffix}"
        try:
            result = cloudinary.uploader.upload(
                BytesIO(content),
                public_id=public_id,
                resource_type=self.resource_type,
                type="authenticated",
                overwrite=False,
            )
        except Exception as exc:
            # Surfaced as OSError so the routes map an unreachable store to the
            # same 503 they already return for an unwritable volume.
            logger.exception("Cloudinary upload failed for %s", public_id)
            raise OSError(f"Cloudinary upload failed: {exc}") from exc
        key = f"{CLOUDINARY_PREFIX}{result['public_id']}"
        if self.resource_type == "image":
            key = f"{key}{suffix}"
        logger.debug("Stored object %s (%d bytes)", key, len(content))
        return key

    def _download_url(self, key: str) -> str:
        """Sign a URL for the original bytes via the API, not the CDN.

        Delivery URLs for authenticated assets are subject to per-account
        delivery rules, which reject raw PDFs with a 401 on most plans. The
        download endpoint is signed with the API secret and is not.
        """
        public_id = self._public_id(key)
        cloudinary = self._configure()
        # raw carries its extension in the public_id; image had it stripped, so
        # the format has to be handed over separately.
        fmt = Path(key).suffix.lstrip(".") if self.resource_type == "image" else None
        return cloudinary.utils.private_download_url(
            public_id, fmt, resource_type=self.resource_type, type="authenticated"
        )

    def read(self, key: str) -> bytes:
        public_id = self._public_id(key)
        url = self._download_url(key)
        try:
            with urlopen(url, timeout=30) as response:  # noqa: S310 - signed Cloudinary URL
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                logger.warning("Cloudinary object does not exist: %s", public_id)
                raise FileNotFoundError(key) from exc
            # Anything else is the store refusing or failing, not a missing
            # object. Reporting it as absent sends a 404 for a resume that is
            # sitting in the account, which is what made the 401 hard to read.
            logger.error(
                "Cloudinary refused to serve %s: HTTP %d %s", public_id, exc.code, exc.reason
            )
            raise OSError(f"Cloudinary download failed with HTTP {exc.code}") from exc
        except Exception as exc:
            logger.exception("Cloudinary object could not be retrieved: %s", public_id)
            raise OSError(f"Cloudinary download failed: {exc}") from exc

    @contextmanager
    def open(self, key: str) -> Iterator[Path]:
        """Download to a temporary path, removed on exit.

        The resume parser needs a real file, and a remote object has no path.
        """
        content = self.read(key)
        suffix = Path(self._public_id(key)).suffix or ".pdf"
        with TemporaryDirectory() as directory:
            path = Path(directory) / f"resume{suffix}"
            path.write_bytes(content)
            yield path

    def delete(self, key: str) -> None:
        try:
            public_id = self._public_id(key)
        except FileNotFoundError:
            logger.debug("Delete skipped, not a Cloudinary key: %s", key)
            return
        try:
            cloudinary = self._configure()
            cloudinary.uploader.destroy(
                public_id, resource_type=self.resource_type, type="authenticated"
            )
        except Exception:
            logger.exception("Could not delete object %s", key)


def build_storage(settings: Settings, folder: str, resource_type: str, root: Path):
    """Pick the backend. Local roots are only created when local is selected."""
    if settings.use_cloudinary:
        return CloudinaryPrivateStorage(folder, resource_type, settings)
    return LocalPrivateStorage(root)


settings = get_settings()
resume_storage = build_storage(
    settings, RESUME_FOLDER, "raw", settings.resume_storage_path
)
avatar_storage = build_storage(
    settings, AVATAR_FOLDER, "image", settings.avatar_storage_path
)

if settings.use_cloudinary:
    logger.info(
        "Object storage: Cloudinary cloud %s (local disk unused)",
        settings.cloudinary_cloud_name,
    )
else:
    logger.info("Object storage: local disk at %s", settings.resume_storage_path)


def avatar_media_type(key: str) -> str:
    suffix = Path(key).suffix.lower()
    return mimetypes.types_map.get(suffix, "image/jpeg")
