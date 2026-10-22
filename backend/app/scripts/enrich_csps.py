"""Enrich existing CSPs with relationship-building details matched by CSP ID.

Input: app/scripts/data/csp_details.json - { "<CSP CODE>": {date_of_birth, gender, email,
address, pincode, home_phone}, ... }, extracted from the KO full-details export and already
filtered to CSP codes that exist as active CSPs in the CRM.

Only ever FILLS the relationship fields on a matching CSP (matched on csp_id); it never touches
name / number / RM / status (those are owned by the daily calling-sheet sync).

    python -m app.scripts.enrich_csps            # apply
    python -m app.scripts.enrich_csps --dry-run  # preview
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from ..db import SessionLocal
from ..models.csp import Csp

_DATA = Path(__file__).parent / "data" / "csp_details.json"


def _as_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def run(dry_run: bool) -> None:
    details = json.loads(_DATA.read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        matched = 0
        by_id = {c.csp_id.strip().upper(): c for c in db.scalars(select(Csp)).all()}
        for code, d in details.items():
            csp = by_id.get(code.strip().upper())
            if csp is None:
                continue
            csp.date_of_birth = _as_date(d.get("date_of_birth"))
            csp.gender = (d.get("gender") or None)
            csp.email = (d.get("email") or None)
            csp.address = (d.get("address") or None)
            csp.pincode = (d.get("pincode") or None)
            csp.home_phone = (d.get("home_phone") or None)
            matched += 1
        if dry_run:
            db.rollback()
            print(f"[dry-run] would enrich {matched} CSPs")
        else:
            db.commit()
            print(f"enriched {matched} CSPs with birthday + contact details")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args().dry_run)
