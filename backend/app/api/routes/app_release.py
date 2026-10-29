"""Android self-update: the DC app checks its own version against this on
launch, and downloads the APK here if newer. No auth on the download itself
(the file carries no sensitive data and a bearer token is awkward to attach
to a plain download-manager-style GET); the version-check does require auth,
just to keep the endpoint list consistent with the rest of the API.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models.user import Role, User
from ...schemas.app_release import AppVersionOut
from ...security.deps import get_current_user, require_roles
from ...services import audit
from ...services.app_release import apk_path, latest_info, publish

settings = get_settings()
router = APIRouter(prefix="/app", tags=["app-release"])


@router.get("/version", response_model=AppVersionOut)
def latest_version(_: User = Depends(get_current_user)):
    code, name = latest_info()
    return AppVersionOut(
        version_code=code,
        version_name=name,
        download_url=f"{settings.api_prefix}/app/download",
    )


_MAX_APK_BYTES = 100 * 1024 * 1024


@router.post("/release", response_model=AppVersionOut, status_code=status.HTTP_201_CREATED)
async def publish_release(
    apk: UploadFile = File(...),
    version_code: int = Form(..., ge=1),
    version_name: str = Form(..., min_length=1, max_length=40),
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.ADMIN)),
):
    """Admin only: publishes a new APK as the current release. Every phone that runs the app is then offered
    the update (it only ever goes UP: a version code not above the current one is refused)."""
    current_code, _ = latest_info()
    if version_code <= current_code:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Version code must be higher than the current {current_code}"
        )
    data = await apk.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Empty file")
    if len(data) > _MAX_APK_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "APK too large")
    if data[:4] != b"PK\x03\x04":      # an APK is a zip archive
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That is not an APK file")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "upload.apk"
        src.write_bytes(data)
        publish(src, version_code, version_name.strip())
    audit.record(
        db, action="app.release_published", entity_type="app_release", entity_id=version_code,
        actor_id=admin.id, after={"version_code": version_code, "version_name": version_name.strip(), "bytes": len(data)},
    )
    db.commit()
    return AppVersionOut(
        version_code=version_code,
        version_name=version_name.strip(),
        download_url=f"{settings.api_prefix}/app/download",
    )


@router.get("/download")
def download_apk():
    path = apk_path()
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No release published yet")
    return FileResponse(
        path, media_type="application/vnd.android.package-archive", filename="rcrm-dc.apk"
    )
