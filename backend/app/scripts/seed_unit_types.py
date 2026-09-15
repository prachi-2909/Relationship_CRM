"""Ensure the default organisation-unit types exist.

    python -m app.scripts.seed_unit_types

Idempotent. The migration seeds these on a fresh database; this script is for
re-adding any that were removed, or for test setup.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.org_unit_type import OrgUnitType

DEFAULT_UNIT_TYPES: list[tuple[str, str, int]] = [
    ("CC", "Corporate Centre", 10),
    ("LHO", "LHO", 20),
    ("RBO", "RBO", 30),
    ("AO", "AO", 40),
    ("BRANCH", "Branch", 50),
]


def ensure_defaults(db: Session) -> int:
    existing = set(db.scalars(select(OrgUnitType.code)))
    added = 0
    for code, label, rank in DEFAULT_UNIT_TYPES:
        if code not in existing:
            db.add(OrgUnitType(code=code, label=label, rank=rank, active=True))
            added += 1
    if added:
        db.flush()
    return added


def main() -> None:
    db = SessionLocal()
    try:
        added = ensure_defaults(db)
        db.commit()
        print(f"OK - added {added} unit type(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
