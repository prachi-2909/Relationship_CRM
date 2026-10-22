"""Fixes branches that were imported directly under an AO, skipping the RBO
level (CC -> LHO -> AO -> RBO -> BRANCH is the correct hierarchy). This is
what makes a DC's "My Territory" view miss its RBO, and makes RBO-level
officials (e.g. a shared Field Investigator) invisible to that DC.

Input `rbo_mapping.json`: a dict of {tab_name: [{branch, ifsc, rbo,
branch_code?}, ...]} scraped from the "DC wise Branch & RBO Mapping" sheet
(one entry per tab). Rows with a blank "rbo" are skipped - never guessed at.

Matching, safest first:
- By IFSC code (branch.unit_metadata["ifsc"]) - exact, unambiguous.
- By branch_code (branch.unit_metadata["branch_code"]) - same.
- By case-insensitive branch name, only when that name is unique among
  branches currently parented directly under an AO.
A branch already correctly parented under an RBO is left untouched, even if
it also appears in the sheet - only AO-parented (misplaced) branches are
candidates for reparenting. A branch matched by two sheet rows that disagree
on the RBO name is flagged as a conflict, never guessed at.

The target RBO is found by exact case-insensitive name (RBO names are
globally unique in this DB - verified before writing this script). If no RBO
with that name exists yet, one is created under the branch's own current AO
parent (that AO was already correct; only the RBO level was missing).

    python -m app.scripts.fix_branch_rbo_parenting rbo_mapping.json --apply
"""

from __future__ import annotations

import argparse
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.organization_unit import OrganizationUnit, OrgUnitStatus
from ..services import audit


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _flatten(mapping: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for tab, tab_rows in mapping.items():
        for r in tab_rows:
            branch = (r.get("branch") or "").strip()
            rbo = (r.get("rbo") or "").strip()
            if not branch or not rbo:
                continue
            rows.append({
                "tab": tab,
                "branch": branch,
                "ifsc": (r.get("ifsc") or "").strip().upper(),
                "branch_code": (r.get("branch_code") or "").strip(),
                "rbo": rbo,
            })
    return rows


def reconcile(db: Session, mapping: dict[str, list[dict]]) -> dict:
    report = {
        "reparented": [], "rbo_created": [],
        "conflicting_rbo_for_branch": [], "name_ambiguous": [], "not_found": [],
        "skipped_blank_rbo_rows": 0, "already_under_rbo_untouched": 0,
    }

    all_rows = _flatten(mapping)
    total_sheet_rows = sum(len(v) for v in mapping.values())
    report["skipped_blank_rbo_rows"] = total_sheet_rows - len(all_rows)

    branches = db.scalars(select(OrganizationUnit).where(OrganizationUnit.type_code == "BRANCH")).all()
    units_by_id = {u.id: u for u in db.scalars(select(OrganizationUnit)).all()}

    ao_parented = [b for b in branches if b.parent_id and units_by_id.get(b.parent_id) and units_by_id[b.parent_id].type_code == "AO"]

    by_ifsc: dict[str, OrganizationUnit] = {}
    by_branch_code: dict[str, OrganizationUnit] = {}
    name_counts: dict[str, int] = {}
    by_name: dict[str, OrganizationUnit] = {}
    for b in ao_parented:
        meta = b.unit_metadata or {}
        ifsc = (meta.get("ifsc") or "").strip().upper()
        if ifsc:
            by_ifsc[ifsc] = b
        code = (meta.get("branch_code") or "").strip()
        if code:
            by_branch_code[code] = b
        k = _key(b.name)
        name_counts[k] = name_counts.get(k, 0) + 1
        by_name.setdefault(k, b)

    rbo_by_name = {
        _key(u.name): u for u in db.scalars(select(OrganizationUnit).where(OrganizationUnit.type_code == "RBO")).all()
    }

    # branch.id -> the single RBO name every matching sheet row agrees on (or a conflict marker)
    target_rbo_for_branch: dict[int, str] = {}
    conflict_branch_ids: set[int] = set()
    match_source: dict[int, str] = {}

    for row in all_rows:
        branch_unit = None
        source = None
        if row["ifsc"] and row["ifsc"] in by_ifsc:
            branch_unit = by_ifsc[row["ifsc"]]
            source = f"ifsc:{row['ifsc']}"
        elif row["branch_code"] and row["branch_code"] in by_branch_code:
            branch_unit = by_branch_code[row["branch_code"]]
            source = f"branch_code:{row['branch_code']}"
        else:
            k = _key(row["branch"])
            if k in by_name and name_counts[k] == 1:
                branch_unit = by_name[k]
                source = f"name:{row['branch']}"
            elif k in by_name and name_counts[k] > 1:
                report["name_ambiguous"].append(f"{row['tab']}: {row['branch']}")
                continue
            else:
                report["not_found"].append(f"{row['tab']}: {row['branch']} (ifsc={row['ifsc'] or '-'})")
                continue

        existing = target_rbo_for_branch.get(branch_unit.id)
        if existing is not None and _key(existing) != _key(row["rbo"]):
            conflict_branch_ids.add(branch_unit.id)
            continue
        target_rbo_for_branch[branch_unit.id] = row["rbo"]
        match_source[branch_unit.id] = source

    for branch_id in conflict_branch_ids:
        target_rbo_for_branch.pop(branch_id, None)
        b = units_by_id[branch_id]
        report["conflicting_rbo_for_branch"].append(f"{b.name} (id={b.id})")

    for branch_id, rbo_name in target_rbo_for_branch.items():
        branch = units_by_id[branch_id]
        rbo_unit = rbo_by_name.get(_key(rbo_name))
        if rbo_unit is None:
            rbo_unit = OrganizationUnit(
                name=rbo_name.strip(), type_code="RBO", parent_id=branch.parent_id,
                status=OrgUnitStatus.ACTIVE,
            )
            db.add(rbo_unit)
            db.flush()
            audit.record(
                db, action="org_unit.bulk_import_create", entity_type="org_unit", entity_id=rbo_unit.id,
                actor_id=None, after={"name": rbo_unit.name, "type_code": "RBO", "parent_id": branch.parent_id},
            )
            rbo_by_name[_key(rbo_name)] = rbo_unit
            report["rbo_created"].append(f"{rbo_unit.name} (id={rbo_unit.id}) under AO id={branch.parent_id}")

        before_parent = branch.parent_id
        branch.parent_id = rbo_unit.id
        audit.record(
            db, action="org_unit.bulk_import_reparent", entity_type="org_unit", entity_id=branch.id,
            actor_id=None, before={"parent_id": before_parent}, after={"parent_id": rbo_unit.id},
        )
        report["reparented"].append(
            f"{branch.name} (id={branch.id}) -> RBO '{rbo_unit.name}' (id={rbo_unit.id}) "
            f"[was AO id={before_parent}, matched by {match_source[branch_id]}]"
        )

    report["already_under_rbo_untouched"] = len(branches) - len(ao_parented)
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
