"""Where the current Android release APK lives on disk, relative to the
database file's own directory (same convention as backup_dir/media_dir).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import get_settings

settings = get_settings()

_APK_NAME = "app-release.apk"
_INFO_NAME = "latest.json"


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


def latest_info() -> tuple[int, str]:
    """(version_code, version_name) the apps are told to update to: what the last publish recorded, else the
    ANDROID_LATEST_VERSION_* settings (the old way, kept as the fallback)."""
    try:
        data = json.loads((_root() / _INFO_NAME).read_text(encoding="utf-8"))
        return int(data["version_code"]), str(data["version_name"])
    except (OSError, ValueError, KeyError, TypeError):
        return settings.android_latest_version_code, settings.android_latest_version_name


def publish(source_apk: Path, version_code: int | None = None, version_name: str | None = None) -> Path:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    dest = apk_path()
    dest.write_bytes(source_apk.read_bytes())
    if version_code is not None and version_name:
        (root / _INFO_NAME).write_text(
            json.dumps({"version_code": version_code, "version_name": version_name}), encoding="utf-8"
        )
    return dest
