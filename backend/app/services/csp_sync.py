"""Daily CSP sync from the live "Calling Sheet" Google Sheet.

Fetches the sheet's public CSV export and reconciles the `csps` table with it:
- every ACTIVE CSP in the sheet is upserted (name, number, alternate number, category, assigned RM,
  branch/district/state) keyed on its CSP ID, so changed numbers / RM reassignments land in the DB;
- any CSP in the DB that is no longer active in the sheet is marked INACTIVE, so it drops off the
  app and web (both show active CSPs only).

Columns are resolved by HEADER NAME, never by fixed position, because whoever maintains the sheet
inserts/removes columns over time (a hardcoded index would silently read the wrong field).
"""

from __future__ import annotations

import csv
import io
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.csp import Csp, CspStatus
from ..models.user import Role, User

logger = logging.getLogger("rcrm.csp_sync")
settings = get_settings()


class CspSyncError(RuntimeError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _norm_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits or None


def _fetch_csv() -> str:
    import httpx

    url = (
        f"https://docs.google.com/spreadsheets/d/{settings.csp_sheet_id}"
        f"/export?format=csv&gid={settings.csp_sheet_gid}"
    )
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        if "text/csv" not in resp.headers.get("content-type", ""):
            raise CspSyncError("Calling Sheet did not return CSV (is it still link-shared?)")
        return resp.text


def _resolve_columns(field_row: list[str]) -> dict[str, int]:
    """Map the fields we need to their column index, by header name. 'State' appears twice
    (one is a mislabelled circle-head column), so the geographic state is taken as the first
    'state' header that comes after 'district'."""
    idx: dict[str, int] = {}
    wanted = {
        "csp_id": "csp id",
        "name": "csp name",
        "mobile": "csp mobile number",
        "alt_mobile": "alternative mobile number",
        "category": "csp category",
        "rm": "relationship manager",
        "status": "terminal status",
        "branch": "branch name",
        "district": "district",
        "lho": "circle (lho)",
    }
    normed = [_norm(h) for h in field_row]
    for key, label in wanted.items():
        for i, h in enumerate(normed):
            if h == label:
                idx[key] = i
                break
    # geographic state: first "state" column after district
    if "district" in idx:
        for i in range(idx["district"] + 1, len(normed)):
            if normed[i] == "state":
                idx["state"] = i
                break
    missing = [k for k in ("csp_id", "name", "mobile", "rm", "status") if k not in idx]
    if missing:
        raise CspSyncError(f"Calling Sheet is missing required columns: {missing}")
    return idx


def _rm_user_map(db: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for u in db.scalars(select(User).where(User.role == Role.RELATIONSHIP_MANAGER)).all():
        if u.name:
            out[u.name.strip().split()[0].lower()] = u.id
    return out


def sync_csps_from_sheet(db: Session) -> dict:
    """Reconcile the csps table with the live sheet. Returns a counts summary. Never partially
    commits: the whole reconcile is one transaction the caller commits."""
    text = _fetch_csv()
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        raise CspSyncError("Calling Sheet has no data rows")
    # row 0 = merged group labels, row 1 = field names, row 2+ = data (same as the one-off import).
    col = _resolve_columns(rows[1])
    rm_map = _rm_user_map(db)

    def cell(r: list[str], key: str) -> str:
        i = col.get(key)
        return (r[i].strip() if i is not None and i < len(r) else "")

    existing = {c.csp_id: c for c in db.scalars(select(Csp)).all()}
    seen_active: set[str] = set()
    created = updated = deactivated = 0
    unmatched_rms: set[str] = set()

    for r in rows[2:]:
        csp_id = cell(r, "csp_id")
        name = cell(r, "name")
        if not csp_id or not name:
            continue
        if not re.match(r"^active", _norm(cell(r, "status"))):
            continue  # only active CSPs are tracked
        seen_active.add(csp_id)
        rm_name = cell(r, "rm")
        rm_user_id = rm_map.get(rm_name.lower())
        if rm_name and rm_user_id is None:
            unmatched_rms.add(rm_name)
        fields = dict(
            name=name,
            mobile=_norm_phone(cell(r, "mobile")),
            alternate_mobile=_norm_phone(cell(r, "alt_mobile")),
            category=cell(r, "category") or None,
            rm_name=rm_name,
            rm_user_id=rm_user_id,
            branch_name=cell(r, "branch") or None,
            district=cell(r, "district") or None,
            state=cell(r, "state") or None,
            lho=cell(r, "lho") or None,
            status=CspStatus.ACTIVE,
        )
        c = existing.get(csp_id)
        if c is None:
            db.add(Csp(csp_id=csp_id, **fields))
            created += 1
        else:
            if any(getattr(c, k) != v for k, v in fields.items()):
                for k, v in fields.items():
                    setattr(c, k, v)
                updated += 1

    # CSPs no longer active in the sheet -> deactivate so they drop off the app/web.
    for csp_id, c in existing.items():
        if csp_id not in seen_active and c.status != CspStatus.INACTIVE:
            c.status = CspStatus.INACTIVE
            deactivated += 1

    db.flush()
    summary = {
        "created": created, "updated": updated, "deactivated": deactivated,
        "active_in_sheet": len(seen_active),
    }
    if unmatched_rms:
        summary["unmatched_rms"] = sorted(unmatched_rms)
    return summary


def run_sync() -> dict:
    """Entry point for the scheduler: own DB session, commit on success, never raise."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        summary = sync_csps_from_sheet(db)
        db.commit()
        logger.info("CSP sync: %s", summary)
        return summary
    except Exception:
        db.rollback()
        logger.exception("CSP sync failed")
        return {"error": "sync failed"}
    finally:
        db.close()
