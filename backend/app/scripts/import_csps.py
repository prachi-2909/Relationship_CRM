"""Import active CSPs (from the calling sheet) and assign each to its Relationship Manager.

Input: app/scripts/data/active_csps.json - a JSON array of
{csp_id, name, mobile, alt_mobile, category, rm, status, branch, district, state, lho}
records, one per ACTIVE CSP (inactive CSPs are already excluded during extraction).

Each CSP's sheet "Relationship Manager" value is a first name (Vandana / Shiwani / Amuda);
it is matched to that RM's user account by first name so an RM can later see their own CSPs.

    python -m app.scripts.import_csps            # upsert (idempotent)
    python -m app.scripts.import_csps --dry-run  # preview only
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sqlalchemy import select

from ..db import SessionLocal
from ..models.csp import Csp, CspStatus
from ..models.user import Role, User

_DATA = Path(__file__).parent / "data" / "active_csps.json"


def _norm_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits or None


def _rm_user_map(db) -> dict[str, int]:
    """first-name (lowercase) -> RM user id, for linking each CSP to its RM account."""
    rms = db.scalars(select(User).where(User.role == Role.RELATIONSHIP_MANAGER)).all()
    out: dict[str, int] = {}
    for u in rms:
        first = (u.name or "").strip().split()[0].lower() if u.name else ""
        if first:
            out[first] = u.id
    return out


def run(dry_run: bool) -> None:
    rows = json.loads(_DATA.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        rm_map = _rm_user_map(db)
        created = updated = linked = 0
        unmatched_rms: set[str] = set()
        for r in rows:
            csp_id = (r.get("csp_id") or "").strip()
            name = (r.get("name") or "").strip()
            if not csp_id or not name:
                continue
            rm_name = (r.get("rm") or "").strip()
            rm_user_id = rm_map.get(rm_name.lower())
            if rm_user_id is None and rm_name:
                unmatched_rms.add(rm_name)
            else:
                linked += 1
            existing = db.scalar(select(Csp).where(Csp.csp_id == csp_id))
            fields = dict(
                name=name,
                mobile=_norm_phone(r.get("mobile")),
                alternate_mobile=_norm_phone(r.get("alt_mobile")),
                category=(r.get("category") or "").strip() or None,
                rm_name=rm_name,
                rm_user_id=rm_user_id,
                branch_name=(r.get("branch") or "").strip() or None,
                district=(r.get("district") or "").strip() or None,
                state=(r.get("state") or "").strip() or None,
                lho=(r.get("lho") or "").strip() or None,
                status=CspStatus.ACTIVE,
            )
            if existing is None:
                db.add(Csp(csp_id=csp_id, **fields))
                created += 1
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
        if dry_run:
            db.rollback()
            print(f"[dry-run] would create {created}, update {updated} CSPs; {linked} linked to an RM user")
        else:
            db.commit()
            print(f"created {created}, updated {updated} CSPs; {linked} linked to an RM user")
        if unmatched_rms:
            print(f"WARNING: no RM user matched for: {sorted(unmatched_rms)}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.dry_run)
