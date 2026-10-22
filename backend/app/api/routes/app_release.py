"""Android self-update: the DC app checks its own version against this on
launch, and downloads the APK here if newer. No auth on the download itself
(the file carries no sensitive data and a bearer token is awkward to attach
to a plain download-manager-style GET); the version-check does require auth,
just to keep the endpoint list consistent with the rest of the API.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from ...config import get_settings
from ...models.user import User
from ...schemas.app_release import AppVersionOut
from ...security.deps import get_current_user
from ...services.app_release import apk_path

settings = get_settings()
router = APIRouter(prefix="/app", tags=["app-release"])


@router.get("/version", response_model=AppVersionOut)
def latest_version(_: User = Depends(get_current_user)):
    return AppVersionOut(
        version_code=settings.android_latest_version_code,
        version_name=settings.android_latest_version_name,
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
