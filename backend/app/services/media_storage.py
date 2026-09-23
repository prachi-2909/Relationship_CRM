"""Local disk storage for uploaded call media (DC voice notes today).
Every caller only ever deals in a secure_object_ref string, so swapping this
for real object storage later is purely a config/implementation change here.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ..config import get_settings

settings = get_settings()


def _root() -> Path:
    db_path = None
    if settings.database_url.startswith("sqlite"):
        _, _, path_part = settings.database_url.partition(":///")
        if path_part and path_part != ":memory:":
            db_path = Path(path_part)
    base = db_path.parent if db_path else Path(".")
    return base / settings.media_dir


def save_upload(subdir: str, filename: str, data: bytes) -> str:
    """Saves bytes under media_dir/subdir with a random name, returns the
    path to store as secure_object_ref."""
    root = _root() / subdir
    root.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix or ".bin"
    dest = root / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(data)
    return str(dest)
