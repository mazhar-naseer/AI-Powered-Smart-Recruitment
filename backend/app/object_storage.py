import uuid
from pathlib import Path

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

class LocalPrivateStorage:
    """Private object storage boundary. Keys are opaque; callers never build filesystem paths."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4().hex}{suffix.lower()}"
        try:
            (self.root / key).write_bytes(content)
        except OSError:
            # A full or read-only volume is an infrastructure fault, not a bad
            # request. Re-raised so the caller still fails, but recorded here
            # because only this layer knows the target directory.
            logger.exception("Storage write failed for %s in %s", key, self.root)
            raise
        logger.debug("Stored object %s (%d bytes)", key, len(content))
        return key

    def path(self, key: str) -> Path:
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

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            logger.debug("Delete skipped, object already gone: %s", key)
        except OSError:
            logger.exception("Could not delete object %s", key)


settings = get_settings()
resume_storage = LocalPrivateStorage(settings.resume_storage_path)
avatar_storage = LocalPrivateStorage(settings.avatar_storage_path)
