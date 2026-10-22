"""Where the current Android release APK lives on disk, relative to the
database file's own directory (same convention as backup_dir/media_dir).
"""

from __future__ import annotations

from pathlib import Path

from ..config import get_settings

settings = get_settings()

_APK_NAME = "app-release.apk"


def _root() -> Path:
    db_path = None
    if settings.database_url.startswith("sqlite"):
        _, _, path_part = settings.database_url.partition(":///")
        if path_part and path_part != ":memory:":
            db_path = Path(path_part)
    base = db_path.parent if db_path else Path(".")
    return base / settings.android_release_dir


def apk_path() -> Path:
    return _root() / _APK_NAME


def publish(source_apk: Path) -> Path:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    dest = apk_path()
    dest.write_bytes(source_apk.read_bytes())
    return dest
