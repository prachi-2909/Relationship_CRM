"""One-time reconciliation: replace the ad-hoc CC -> RBO -> Branch demo
hierarchy with the real CC -> LHO -> AO -> Branch structure sourced from the
"Calling Sheet" (Circle/LHO, AO, Branch Code/Name, District, State columns).

    python -m app.scripts.import_calling_sheet extract.json --dry-run   # preview only
    python -m app.scripts.import_calling_sheet extract.json --apply     # commit

`extract.json` is a JSON array of {lho, ao, code, name, dist, st} records
(one per calling-sheet row; duplicates across CSPs at the same branch are
expected and deduplicated by branch code here).

Reconciliation rules, chosen to never lose real data:
- A branch whose (case-insensitive) name is unique in BOTH the existing DB
  and the new sheet is re-parented onto its correct new AO in place - same
  row, same id, so every Official/Relationship/Interaction already attached
  to it is untouched.
- Every other sheet branch is created fresh under its AO.
- An existing branch/RBO with no counterpart in the sheet is archived only
  if it has no active officials and no active children left; otherwise it
  is left exactly as it was and reported, never force-archived.
Idempotent: safe to re-run - matching by name means already-migrated units
are found and left alone rather than duplicated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.official import Official, OfficialStatus
from ..models.organization_unit import OrganizationUnit, OrgUnitStatus
from ..services import audit

_SYSTEM_ACTOR_ID = None  # bulk data-migration script, not an interactive admin action


def _normalize_ao(raw: str) -> str:
    s = re.sub(r"-", " ", raw)
    s = re.sub(r"\s+", " ", s).strip()
    if s.upper().startswith("AO"):
        rest = s[2:].strip()
        return "AO " + rest.title() if rest else "AO"
    return s.title()


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _load_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return [r for r in rows if r.get("code") or r.get("name")]


def _get_or_create(db: Session, *, name: str, type_code: str, parent_id: int | None,
                    cache: dict, location: str | None = None) -> tuple[OrganizationUnit, bool]:
    cache_key = (type_code, parent_id, _key(name))
    if cache_key in cache:
        return cache[cache_key], False
    existing = db.scalar(
        select(OrganizationUnit)
        .where(OrganizationUnit.type_code == type_code)
        .where(OrganizationUnit.parent_id == parent_id)
        .where(OrganizationUnit.name.ilike(name))
    )
    if existing is not None:
        cache[cache_key] = existing
        return existing, False
    unit = OrganizationUnit(
        name=name, type_code=type_code, parent_id=parent_id,
        location=location, status=OrgUnitStatus.ACTIVE,
    )
    db.add(unit)
    db.flush()
    audit.record(
        db, action="org_unit.bulk_import_create", entity_type="org_unit", entity_id=unit.id,
        actor_id=_SYSTEM_ACTOR_ID, after={"name": name, "type_code": type_code, "parent_id": parent_id},
    )
    cache[cache_key] = unit
    return unit, True


def reconcile(db: Session, rows: list[dict]) -> dict:
    report = {
        "lho_created": 0, "ao_created": 0,
        "branches_reparented": 0, "branches_created": 0,
        "old_units_archived": 0, "old_units_kept_active_with_officials": [],
        "skipped_ambiguous_new_branches": 0,
    }
    cache: dict = {}

    cc = db.scalar(select(OrganizationUnit).where(OrganizationUnit.type_code == "CC"))
    if cc is None:
        raise SystemExit("No Corporate Centre unit found - create one first via the app.")

    # --- old branch inventory, for safe unique-name matching ---------------
    old_branches = db.scalars(
        select(OrganizationUnit).where(OrganizationUnit.type_code == "BRANCH")
    ).all()
    old_name_counts = Counter(_key(u.name) for u in old_branches)
    old_by_key: dict[str, OrganizationUnit] = {}
    for u in old_branches:
        old_by_key.setdefault(_key(u.name), u)

    # --- distinct branches from the sheet, keyed by branch code -----------
    by_code: dict[str, dict] = {}
    for r in rows:
        code = r.get("code") or f"noname:{_key(r['name'])}"
        prev = by_code.get(code)
        if prev is None or (not prev.get("name") and r.get("name")):
            by_code[code] = r
    new_name_counts = Counter(_key(r["name"]) for r in by_code.values() if r.get("name"))

    matched_old_ids: set[int] = set()

    for rec in by_code.values():
        lho_name = rec["lho"]
        ao_raw = rec["ao"]
        name = rec["name"].strip() if rec["name"] else None
        if not lho_name or not ao_raw or not name:
            report["skipped_ambiguous_new_branches"] += 1
            continue

        lho, lho_created = _get_or_create(db, name=lho_name, type_code="LHO", parent_id=cc.id, cache=cache)
        if lho_created:
            report["lho_created"] += 1

        ao_name = _normalize_ao(ao_raw)
        ao, ao_created = _get_or_create(db, name=ao_name, type_code="AO", parent_id=lho.id, cache=cache)
        if ao_created:
            report["ao_created"] += 1

        branch_name = name.title()
        key = _key(name)
        location = ", ".join(p for p in (rec.get("dist"), rec.get("st")) if p) or None

        safe_match = old_name_counts.get(key) == 1 and new_name_counts.get(key) == 1
        if safe_match:
            old_unit = old_by_key[key]
            if old_unit.parent_id != ao.id:
                before = {"parent_id": old_unit.parent_id}
                old_unit.parent_id = ao.id
                if location:
                    old_unit.location = location
                audit.record(
                    db, action="org_unit.bulk_import_reparent", entity_type="org_unit",
                    entity_id=old_unit.id, actor_id=_SYSTEM_ACTOR_ID,
                    before=before, after={"parent_id": ao.id},
                )
                report["branches_reparented"] += 1
            matched_old_ids.add(old_unit.id)
        else:
            existing_new = db.scalar(
                select(OrganizationUnit)
                .where(OrganizationUnit.type_code == "BRANCH")
                .where(OrganizationUnit.parent_id == ao.id)
                .where(OrganizationUnit.name.ilike(branch_name))
            )
            if existing_new is None:
                unit = OrganizationUnit(
                    name=branch_name, type_code="BRANCH", parent_id=ao.id,
                    location=location, status=OrgUnitStatus.ACTIVE,
                )
                db.add(unit)
                db.flush()
                audit.record(
                    db, action="org_unit.bulk_import_create", entity_type="org_unit",
                    entity_id=unit.id, actor_id=_SYSTEM_ACTOR_ID,
                    after={"name": branch_name, "type_code": "BRANCH", "parent_id": ao.id},
                )
                report["branches_created"] += 1

    # --- archive old units the sheet no longer references ------------------
    def _has_active_officials(unit_id: int) -> bool:
        return db.scalar(
            select(Official.id)
            .where(Official.organization_unit_id == unit_id)
            .where(Official.status == OfficialStatus.ACTIVE)
        ) is not None

    def _has_active_children(unit_id: int) -> bool:
        return db.scalar(
            select(OrganizationUnit.id)
            .where(OrganizationUnit.parent_id == unit_id)
            .where(OrganizationUnit.status == OrgUnitStatus.ACTIVE)
        ) is not None

    unmatched_branches = [u for u in old_branches if u.id not in matched_old_ids and u.status == OrgUnitStatus.ACTIVE]
    for u in unmatched_branches:
        if _has_active_officials(u.id):
            report["old_units_kept_active_with_officials"].append({"id": u.id, "name": u.name, "type": "BRANCH"})
            continue
        before = {"status": u.status.value}
        u.status = OrgUnitStatus.ARCHIVED
        audit.record(
            db, action="org_unit.bulk_import_archive", entity_type="org_unit", entity_id=u.id,
            actor_id=_SYSTEM_ACTOR_ID, before=before, after={"status": "archived"},
        )
        report["old_units_archived"] += 1

    old_rbos = db.scalars(
        select(OrganizationUnit).where(OrganizationUnit.type_code == "RBO").where(OrganizationUnit.status == OrgUnitStatus.ACTIVE)
    ).all()
    for u in old_rbos:
        if _has_active_officials(u.id) or _has_active_children(u.id):
            report["old_units_kept_active_with_officials"].append({"id": u.id, "name": u.name, "type": "RBO"})
            continue
        before = {"status": u.status.value}
        u.status = OrgUnitStatus.ARCHIVED
        audit.record(
            db, action="org_unit.bulk_import_archive", entity_type="org_unit", entity_id=u.id,
            actor_id=_SYSTEM_ACTOR_ID, before=before, after={"status": "archived"},
        )
        report["old_units_archived"] += 1

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path")
    parser.add_argument("--apply", action="store_true", help="commit changes (default is a dry run that rolls back)")
    args = parser.parse_args()

    rows = _load_rows(args.json_path)
    db = SessionLocal()
    try:
        report = reconcile(db, rows)
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
