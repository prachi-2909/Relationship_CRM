"""Assigns each DC (matched by name to an existing User with role=dc) the
RBO/AO/Branch units listed for them.

    python -m app.scripts.assign_dc_territory dc_territory_map.json          # dry run
    python -m app.scripts.assign_dc_territory dc_territory_map.json --apply  # commit

`dc_territory_map.json`:
{"<DC full name>": {"type": "RBO"|"AO"|"BRANCH", "names": ["Godda", ...]}, ...}

A DC name with no matching User (role=dc) is reported, never guessed at -
create that DC's login account first (Users page), then re-run this script;
it's idempotent, so re-running only adds what's missing.
"""

from __future__ import annotations

import argparse
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.dc_territory import DCTerritory
from ..models.organization_unit import OrganizationUnit
from ..models.user import Role, User
from ..services import audit


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def reconcile(db: Session, mapping: dict) -> dict:
    report = {"assigned": [], "already_assigned": [], "unit_not_found": [], "dc_not_found": []}

    dc_users = {_key(u.name): u for u in db.scalars(select(User).where(User.role == Role.DC)).all()}

    for dc_name, spec in mapping.items():
        dc = dc_users.get(_key(dc_name))
        if dc is None:
            report["dc_not_found"].append(dc_name)
            continue
        type_code = spec["type"]
        for unit_name in spec["names"]:
            unit = db.scalar(
                select(OrganizationUnit)
                .where(OrganizationUnit.type_code == type_code)
                .where(OrganizationUnit.name.ilike(unit_name))
            )
            if unit is None:
                report["unit_not_found"].append(f"{dc_name}: {type_code} '{unit_name}'")
                continue
            existing = db.scalar(
                select(DCTerritory)
                .where(DCTerritory.dc_user_id == dc.id)
                .where(DCTerritory.organization_unit_id == unit.id)
            )
            if existing is not None:
                report["already_assigned"].append(f"{dc_name} -> {unit.name}")
                continue
            row = DCTerritory(dc_user_id=dc.id, organization_unit_id=unit.id)
            db.add(row)
            db.flush()
            audit.record(
                db, action="dc_territory.bulk_assign", entity_type="dc_territory", entity_id=row.id,
                actor_id=None, after={"dc_user_id": dc.id, "organization_unit_id": unit.id},
            )
            report["assigned"].append(f"{dc_name} -> {unit.name}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        mapping = json.load(f)

    db = SessionLocal()
    try:
        report = reconcile(db, mapping)
        if args.apply:
            db.commit()
            print("APPLIED.")
        else:
            db.rollback()
            print("DRY RUN (no changes committed - pass --apply to commit).")
        print(json.dumps(report, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
