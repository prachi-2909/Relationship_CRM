"""Publishes a newly built APK as the current release: copies the file into
place and bumps the version settings the DC app checks against.

    python -m app.scripts.publish_android_release path/to/app-debug.apk 2 "1.1"

Note: version_code/version_name are process-local settings (env-var backed,
like everything else in config.py) - for this to actually take effect on the
running server, set ANDROID_LATEST_VERSION_CODE / ANDROID_LATEST_VERSION_NAME
in the environment (or .env) to the same values and restart the backend.
This script's job is only to put the APK file in place; it prints the env
vars to set as a reminder rather than silently rewriting .env for you.
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

    dest = publish(src)
    print(f"Published {src} -> {dest}")
    print("Set these and restart the backend for the app to see the update:")
    print(f"  ANDROID_LATEST_VERSION_CODE={args.version_code}")
    print(f"  ANDROID_LATEST_VERSION_NAME={args.version_name}")


if __name__ == "__main__":
    main()
