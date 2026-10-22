"""Rebuilds each real DC's territory strictly from the Calling Sheet's own
"District Coordinator" column (the ground truth), replacing whatever branch
set they previously had - this corrects cases like Motihari/Gopalganj, which
an earlier RBO-name-based reconciliation had wrongly attributed.

Input `rows.json`: a JSON array of {dc, branchName} extracted from the Calling
Sheet (one row per branch-CSP). Branches are matched to existing
OrganizationUnit(type=BRANCH) rows by case-insensitive name; ambiguous
(duplicate-name) or not-found branches are reported, never guessed at.

    python -m app.scripts.rebuild_dc_territory_from_calling_sheet rows.json --apply
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


def reconcile(db: Session, rows: list[dict], dc_names: set[str]) -> dict:
    report = {
        "dc_not_found": [], "branch_not_found": [], "branch_ambiguous": [],
        "territory_removed": [], "territory_added": [], "unchanged": 0,
    }

    branches = db.scalars(select(OrganizationUnit).where(OrganizationUnit.type_code == "BRANCH")).all()
    name_counts: dict[str, int] = {}
    by_key: dict[str, OrganizationUnit] = {}
    for b in branches:
        k = _key(b.name)
        name_counts[k] = name_counts.get(k, 0) + 1
        by_key.setdefault(k, b)

    dc_users = {_key(u.name): u for u in db.scalars(select(User).where(User.role == Role.DC)).all()}

    target_branch_ids: dict[int, set[int]] = {}
    for r in rows:
        dc_name = (r.get("dc") or "").strip()
        if dc_name not in dc_names:
            continue
        branch_name = (r.get("branchName") or "").strip()
        if not branch_name:
            continue
        k = _key(branch_name)
        if k not in by_key:
            report["branch_not_found"].append(f"{dc_name}: {branch_name}")
            continue
        if name_counts[k] > 1:
            report["branch_ambiguous"].append(f"{dc_name}: {branch_name}")
            continue
        dc = dc_users.get(_key(dc_name))
        if dc is None:
            report["dc_not_found"].append(dc_name)
            continue
        target_branch_ids.setdefault(dc.id, set()).add(by_key[k].id)

    for dc_id, wanted in target_branch_ids.items():
        existing_rows = db.scalars(select(DCTerritory).where(DCTerritory.dc_user_id == dc_id)).all()
        existing_unit_ids = {row.organization_unit_id for row in existing_rows}

        for row in existing_rows:
            if row.organization_unit_id not in wanted:
                audit.record(
                    db, action="dc_territory.bulk_remove", entity_type="dc_territory", entity_id=row.id,
                    actor_id=None, before={"dc_user_id": dc_id, "organization_unit_id": row.organization_unit_id},
                )
                report["territory_removed"].append(f"dc_id={dc_id} unit_id={row.organization_unit_id}")
                db.delete(row)

        for unit_id in wanted:
            if unit_id in existing_unit_ids:
                report["unchanged"] += 1
                continue
            new_row = DCTerritory(dc_user_id=dc_id, organization_unit_id=unit_id)
            db.add(new_row)
            db.flush()
            audit.record(
                db, action="dc_territory.bulk_assign", entity_type="dc_territory", entity_id=new_row.id,
                actor_id=None, after={"dc_user_id": dc_id, "organization_unit_id": unit_id},
            )
            report["territory_added"].append(f"dc_id={dc_id} unit_id={unit_id}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--dc-names", nargs="+", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        rows = json.load(f)

    db = SessionLocal()
    try:
        report = reconcile(db, rows, set(args.dc_names))
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
