"""Publishes a newly built APK as the current release: copies the file into
place and bumps the version settings the DC app checks against.

    python -m app.scripts.publish_android_release path/to/app-debug.apk 2 "1.1"

The version is recorded next to the APK (releases/latest.json), which the running server reads on every
check, so no env edit or restart is needed. (An admin can also publish over the API: POST /app/release.)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..services.app_release import publish


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk_path")
    parser.add_argument("version_code", type=int)
    parser.add_argument("version_name")
    args = parser.parse_args()

    src = Path(args.apk_path)
    if not src.exists():
        raise SystemExit(f"No such file: {src}")

    dest = publish(src, args.version_code, args.version_name)
    print(f"Published {src} -> {dest} as version {args.version_name} (code {args.version_code})")


if __name__ == "__main__":
    main()
