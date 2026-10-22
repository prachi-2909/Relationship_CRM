from pydantic import BaseModel


class AppVersionOut(BaseModel):
    version_code: int
    version_name: str
    download_url: str
