"""Seed a demo dataset for a fictional partner organisation.

    python -m app.scripts.seed_demo            # seeds only if the DB has no officials
    python -m app.scripts.seed_demo --force    # seed anyway (adds duplicates)

All names, units, emails and notes below are illustrative. Replace with your
own data via the import flow.
"""

import argparse
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.interaction import Direction, Interaction, InteractionType
from ..models.official import FieldVerification, Official
from ..models.official_date import DateKind, OfficialDate
from ..models.organization_unit import OrganizationUnit
from ..models.relationship import Importance, Relationship, RelationshipStatus
from ..models.task import Task, TaskStatus
from ..models.user import Role, User, UserStatus
from ..security.passwords import hash_password
from ..models.connection import ConnectionStatus, ConnectionType
from ..services import connections as connections_svc
from ..services import moments, scoring
from ..services.llm import extract_interaction
from .seed_unit_types import ensure_defaults

# --- illustrative org tree ------------------------------------------------

HEAD_OFFICE = {
    "name": "Head Office",
    "type": "HO",
    "location": "Delhi",
    "mail": "ho.desk@partner.example",
}
REGIONAL = [
    {"name": "Regional Office — West", "type": "RO", "location": "Mumbai"},
    {
        "name": "Regional Office — East",
        "type": "RO",
        "location": "Kolkata",
        "mail": "ro.east@partner.example",
    },
]
ZONAL = [
    {"name": "Zone 2", "type": "ZO", "parent": "Regional Office — West"},
    {
        "name": "Zone 5",
        "type": "ZO",
        "parent": "Regional Office — East",
        "mail": "zone5@partner.example",
    },
    {"name": "Zone 7", "type": "ZO", "parent": "Regional Office — West"},
]
BRANCHES = [
    {"name": "Andheri Branch (2201)", "type": "BRANCH", "parent": "Zone 7", "mail": "br.2201@partner.example"},
    {"name": "Salt Lake Branch (3110)", "type": "BRANCH", "parent": "Zone 5", "mail": "br.3110@partner.example"},
    {"name": "Howrah Branch (3145)", "type": "BRANCH", "parent": "Zone 5", "mail": "br.3145@partner.example"},
    {"name": "Bandra Branch (2260)", "type": "BRANCH", "parent": "Zone 7", "mail": "br.2260@partner.example"},
    {"name": "Barasat Branch (3208)", "type": "BRANCH", "parent": "Zone 2", "mail": "br.3208@partner.example"},
]

# official (functional role) -> unit name, designation, level, location
OFFICIALS = [
    ("Chief Manager (Partnerships), Head Office", "Head Office", "Chief Manager", "Chief Manager", "Delhi"),
    ("Deputy GM (Operations), Head Office", "Head Office", "Deputy General Manager", "DGM", "Delhi"),
    ("Chief Manager, Zone 5", "Zone 5", "Chief Manager", "Chief Manager", "Kolkata"),
    ("AGM, Regional Office — East", "Regional Office — East", "Assistant General Manager", "AGM", "Kolkata"),
    ("Manager (Partnerships), Zone 5", "Zone 5", "Manager", "Manager", "Kolkata"),
    ("Branch Manager, Andheri Branch", "Andheri Branch (2201)", "Branch Manager", "Scale II", "Mumbai"),
    ("Branch Manager, Barasat Branch", "Barasat Branch (3208)", "Branch Manager", "Scale II", "Barasat"),
]

# (official role, title, due in N days -- negative = overdue, status)
TASKS = [
    ("Chief Manager (Partnerships), Head Office", "Share the revised quarterly targets", -1, "open"),
    ("Chief Manager (Partnerships), Head Office", "Set up the weekly performance report", 4, "open"),
    ("Chief Manager, Zone 5", "Chase the vendor on the pending terminal dispatch", -3, "open"),
    ("Manager (Partnerships), Zone 5", "Confirm the Salt Lake login issue is closed", -5, "done"),
    ("AGM, Regional Office — East", "Draft the Zone 2/7 expansion note", 10, "open"),
    ("Deputy GM (Operations), Head Office", "Follow up on the monthly summary", 2, "open"),
]

# stakeholder graph: (from role, type, to role, note)
CONNECTIONS = [
    (
        "Manager (Partnerships), Zone 5",
        "reports_to",
        "Chief Manager, Zone 5",
        "Zone 5 partnerships line",
    ),
    (
        "Chief Manager, Zone 5",
        "reports_to",
        "AGM, Regional Office — East",
        None,
    ),
    (
        "Deputy GM (Operations), Head Office",
        "works_with",
        "Chief Manager (Partnerships), Head Office",
        "co-own the HO partnership desk",
    ),
    (
        "Chief Manager (Partnerships), Head Office",
        "introduced_by",
        "AGM, Regional Office — East",
        "brought in during the Zone 5 review",
    ),
    (
        "Manager (Partnerships), Zone 5",
        "works_with",
        "Branch Manager, Barasat Branch",
        None,
    ),
]

# (official role, type, direction, days ago, note)
INTERACTIONS = [
    (
        "Chief Manager (Partnerships), Head Office", "meeting", "outbound", 6,
        "Review call with the Head Office desk on last month's performance. They "
        "were satisfied with the West region numbers and asked us to share the "
        "revised quarterly targets by Monday. Agreed to circulate the weekly "
        "performance report every Friday.",
    ),
    (
        "Chief Manager, Zone 5", "call", "outbound", 3,
        "Discussed the pending terminal installation backlog for the Zone 5 "
        "branches. They flagged a delay on the Salt Lake site and requested we "
        "expedite the dispatch. Committed to follow up with the vendor and revert "
        "with a timeline.",
    ),
    (
        "Manager (Partnerships), Zone 5", "email", "inbound", 2,
        "Zone 5 wrote in about a portal login issue at the Salt Lake branch. "
        "Escalated to the branch; issue resolved the same day. They thanked the "
        "support team for the quick turnaround.",
    ),
    (
        "AGM, Regional Office — East", "meeting", "outbound", 20,
        "Quarterly connect with the AGM at Regional Office — East. Positive "
        "discussion on the Zone 2 and Zone 7 expansion. They appreciated the "
        "reconciliation clean-up and confirmed continued support for new "
        "onboarding in the region.",
    ),
    (
        "Branch Manager, Andheri Branch", "call", "outbound", 12,
        "Called the Andheri branch about a device problem at a linked point. The "
        "branch manager was helpful; asked us to keep the branch email in the "
        "loop on all future escalations. Issue resolved.",
    ),
    (
        "Deputy GM (Operations), Head Office", "email", "outbound", 40,
        "Sent the monthly summary to the Deputy GM's office at Head Office. No "
        "reply yet; follow up if nothing by the next review.",
    ),
]


def _get_or_create_admin(db: Session) -> User:
    admin = db.scalar(select(User).where(User.role == Role.ADMIN))
    if admin:
        return admin
    admin = User(
        name="Demo Admin",
        email="admin@example.com",
        password_hash=hash_password("demo-admin-123"),
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db.add(admin)
    db.flush()
    print("  created admin admin@example.com / demo-admin-123")
    return admin


def seed(db: Session) -> None:
    ensure_defaults(db)
    admin = _get_or_create_admin(db)

    units: dict[str, OrganizationUnit] = {}

    head_office = OrganizationUnit(
        name=HEAD_OFFICE["name"],
        type_code=HEAD_OFFICE["type"],
        location=HEAD_OFFICE["location"],
        unit_metadata={"mail": HEAD_OFFICE["mail"]},
    )
    db.add(head_office)
    db.flush()
    units[HEAD_OFFICE["name"]] = head_office

    for ro in REGIONAL:
        u = OrganizationUnit(
            name=ro["name"], type_code=ro["type"], location=ro["location"],
            parent_id=head_office.id,
            unit_metadata={"mail": ro["mail"]} if ro.get("mail") else None,
        )
        db.add(u)
        db.flush()
        units[ro["name"]] = u

    for zo in ZONAL:
        u = OrganizationUnit(
            name=zo["name"], type_code=zo["type"],
            parent_id=units[zo["parent"]].id,
            unit_metadata={"mail": zo["mail"]} if zo.get("mail") else None,
        )
        db.add(u)
        db.flush()
        units[zo["name"]] = u

    for br in BRANCHES:
        u = OrganizationUnit(
            name=br["name"], type_code=br["type"],
            parent_id=units[br["parent"]].id,
            unit_metadata={"mail": br["mail"]},
        )
        db.add(u)
        db.flush()
        units[br["name"]] = u

    officials: dict[str, Official] = {}
    for role_name, unit_name, designation, level, location in OFFICIALS:
        o = Official(
            name=role_name,
            designation=designation,
            level=level,
            location=location,
            organization_unit_id=units[unit_name].id,
        )
        db.add(o)
        db.flush()
        officials[role_name] = o

    relationships: dict[str, Relationship] = {}
    for role_name, official in officials.items():
        rel = Relationship(
            official_id=official.id,
            owner_id=admin.id,
            status=RelationshipStatus.ACTIVE,
        )
        db.add(rel)
        db.flush()
        relationships[role_name] = rel

    now = datetime.now(timezone.utc)
    for role_name, itype, direction, days_ago, note in INTERACTIONS:
        rel = relationships[role_name]
        result = extract_interaction(note, interaction_type=itype)
        payload = {
            "topics": result.topics,
            "commitments": result.commitments,
            "requests": result.requests,
            "people": result.people,
        }
        db.add(
            Interaction(
                relationship_id=rel.id,
                official_id=rel.official_id,
                type=InteractionType(itype),
                direction=Direction(direction),
                occurred_at=now - timedelta(days=days_ago),
                channel="phone" if itype == "call" else None,
                raw_notes=note,
                ai_summary=result.summary,
                ai_structured=payload,
                ai_model=result.model,
                structured=payload,
                sentiment=result.sentiment,
                created_by=admin.id,
            )
        )

    today = datetime.now(timezone.utc).date()
    seed_dates = [
        # birthday on a relationship with no recent contact -> draftable
        (
            "Deputy GM (Operations), Head Office",
            DateKind.BIRTHDAY,
            (today + timedelta(days=4)).replace(year=1975),
        ),
        # promotion on a recently-contacted relationship -> fatigue-suppressed
        (
            "AGM, Regional Office — East",
            DateKind.PROMOTED,
            today - timedelta(days=8),
        ),
        # ~10-year work anniversary, no interactions yet -> draftable
        (
            "Branch Manager, Barasat Branch",
            DateKind.JOINED,
            (today + timedelta(days=3)).replace(year=today.year - 10),
        ),
    ]
    for role_name, kind, value in seed_dates:
        official = officials[role_name]
        db.add(
            OfficialDate(
                official_id=official.id,
                kind=kind,
                value=value,
                source="manual entry (demo)",
                confidence=90,
                verification_status=FieldVerification.VERIFIED,
                verified_by=admin.id,
                verified_at=datetime.now(timezone.utc),
            )
        )
    db.flush()

    for role_name, title, due_days, task_status in TASKS:
        rel = relationships[role_name]
        db.add(
            Task(
                relationship_id=rel.id,
                official_id=rel.official_id,
                title=title,
                due_at=now + timedelta(days=due_days),
                status=TaskStatus(task_status),
                completed_at=now - timedelta(days=1)
                if task_status == "done"
                else None,
                assigned_to=admin.id,
                created_by=admin.id,
            )
        )
    db.flush()

    for from_role, ctype, to_role, note in CONNECTIONS:
        connections_svc.upsert(
            db,
            from_id=officials[from_role].id,
            to_id=officials[to_role].id,
            type_=ConnectionType(ctype),
            source="Manual entry (demo)",
            status=ConnectionStatus.CONFIRMED,
            actor_id=admin.id,
            note=note,
            confidence=100,
        )
    db.flush()

    from ..services.importance import recompute as recompute_importance

    for rel in relationships.values():
        recompute_importance(db, rel)
        scoring.recompute_and_store(db, rel, reason="seed")

    n_moments = moments.detect_all(db)

    print(
        f"  seeded {len(units)} units, {len(officials)} officials, "
        f"{len(relationships)} relationships, {len(INTERACTIONS)} interactions, "
        f"{len(TASKS)} tasks, {len(seed_dates)} dates, {len(CONNECTIONS)} connections, "
        f"{n_moments} moments"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="seed even if data exists")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.force and db.scalar(select(Official.id).limit(1)):
            print("Officials already present; nothing to do (use --force to add anyway).")
            return
        seed(db)
        db.commit()
        print("OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
