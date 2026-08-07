import uuid
from pathlib import Path

from app.config import get_settings


class LocalPrivateStorage:
    """Private object storage boundary. Keys are opaque; callers never build filesystem paths."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4().hex}{suffix.lower()}"
        (self.root / key).write_bytes(content)
        return key

    def path(self, key: str) -> Path:
        raw = Path(key)
        candidate = (raw if raw.is_absolute() else self.root / raw.name).resolve()
        if candidate.parent != self.root or not candidate.is_file():
            raise FileNotFoundError(key)
        return candidate

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass


settings = get_settings()
resume_storage = LocalPrivateStorage(settings.resume_storage_path)
avatar_storage = LocalPrivateStorage(settings.avatar_storage_path)
