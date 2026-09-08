"""Bulk import of officials from CSV / Excel."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models.data_import import DataImport, ImportStatus, RowAction
from ...models.official import Official
from ...models.user import Role, User
from ...schemas.data_import import (
    ImportCreate,
    ImportPreview,
    ImportRowOut,
    ImportSummary,
    WorkedSample,
)
from ...security.deps import get_current_user, require_roles
from ...services import ingestion

router = APIRouter(prefix="/imports", tags=["imports"])

_EDITORS = require_roles(Role.ADMIN, Role.RELATIONSHIP_MANAGER)
_MAX_ROWS = 5000


def _load(db: Session, import_id: int) -> DataImport:
    di = db.get(DataImport, import_id)
    if di is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return di


def _stage(db: Session, filename: str, rows: list[dict], actor: User) -> DataImport:
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No rows found")
    if len(rows) > _MAX_ROWS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Too many rows")
    di = ingestion.stage_import(db, filename=filename, rows=rows, actor_id=actor.id)
    db.commit()
    db.refresh(di)
    return di


@router.post("", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
def create_import_from_csv(
    payload: ImportCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    rows = ingestion.parse_csv(payload.csv_text)
    return ImportSummary.model_validate(_stage(db, payload.filename, rows, actor))


@router.post("/upload", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
async def create_import_from_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(_EDITORS),
):
    data = await file.read()
    name = (file.filename or "upload").lower()
    if name.endswith(".csv"):
        rows = ingestion.parse_csv(data.decode("utf-8-sig"))
    elif name.endswith((".xlsx", ".xlsm")):
        rows = ingestion.parse_xlsx(data)
    else:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .csv or .xlsx file"
        )
    return ImportSummary.model_validate(_stage(db, file.filename or "upload", rows, actor))


@router.get("", response_model=list[ImportSummary])
def list_imports(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    rows = db.scalars(select(DataImport).order_by(DataImport.id.desc())).all()
    return [ImportSummary.model_validate(r) for r in rows]


@router.get("/{import_id}/preview", response_model=ImportPreview)
def preview_import(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    di = _load(db, import_id)
    samples: list[WorkedSample] = []
    for action in (RowAction.CREATE, RowAction.MERGE):
        row = next((r for r in di.rows if r.action is action), None)
        if row is None:
            continue
        norm = row.normalized
        if action is RowAction.CREATE:
            name = norm.get("name") or "?"
            writes = {k: v for k, v in norm.items() if v}
        else:
            official = db.get(Official, row.resolved_official_id)
            name = official.name if official else norm.get("name") or "?"
            writes = {
                k: norm[k]
                for k in ("email", "designation", "department", "level", "location", "unit")
                if norm.get(k) and (official is None or not getattr(official, k, None))
            }
        samples.append(
            WorkedSample(
                action=action, row_number=row.row_number, official_name=name, writes=writes
            )
        )

    base = ImportSummary.model_validate(di).model_dump()
    return ImportPreview(
        **base,
        rows=[ImportRowOut.model_validate(r) for r in di.rows],
        samples=samples,
    )


@router.post("/{import_id}/commit", response_model=ImportSummary)
def commit_import(
    import_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN)),
):
    di = _load(db, import_id)
    if di.status is not ImportStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Import already resolved")
    ingestion.commit_import(db, di, actor_id=actor.id)
    db.commit()
    db.refresh(di)
    return ImportSummary.model_validate(di)


@router.post("/{import_id}/cancel", response_model=ImportSummary)
def cancel_import(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_EDITORS),
):
    di = _load(db, import_id)
    if di.status is not ImportStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Import already resolved")
    di.status = ImportStatus.CANCELLED
    db.commit()
    db.refresh(di)
    return ImportSummary.model_validate(di)
