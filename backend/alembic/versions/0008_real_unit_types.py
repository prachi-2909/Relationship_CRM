"""rename org unit types to match the real hierarchy (RBO/LHO/AO/CC/Branch)

Revision ID: 0008_real_unit_types
Revises: 0007_ask_conversations
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_real_unit_types"
down_revision: Union[str, None] = "0007_ask_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (old_code, new_code, new_label) - rank/active carried over from the old row.
# HO/RO/ZO were placeholders from before the real hierarchy was known.
_RENAMES = [
    ("HO", "CC", "Corporate Centre"),
    ("RO", "LHO", "LHO"),
    ("ZO", "RBO", "RBO"),
]
# same code, just tidying the label
_RELABEL = [
    ("AO", "AO"),
    ("BRANCH", "Branch"),
]


def _rename(conn, old: str, new: str, label: str) -> None:
    # 1. add the new type (only if the old one still exists here - a fresh
    #    install seeded directly with the new codes has nothing to rename)
    conn.execute(
        sa.text(
            "INSERT INTO org_unit_types (code, label, rank, active, created_at, updated_at) "
            "SELECT :new, :label, rank, active, created_at, updated_at FROM org_unit_types "
            "WHERE code = :old AND NOT EXISTS "
            "(SELECT 1 FROM org_unit_types WHERE code = :new)"
        ),
        {"new": new, "label": label, "old": old},
    )
    # 2. repoint any units still filed under the old code
    conn.execute(
        sa.text("UPDATE organization_units SET type_code = :new WHERE type_code = :old"),
        {"new": new, "old": old},
    )
    # 3. the old code is now unreferenced - safe to remove
    conn.execute(sa.text("DELETE FROM org_unit_types WHERE code = :old"), {"old": old})


def upgrade() -> None:
    conn = op.get_bind()
    for old, new, label in _RENAMES:
        _rename(conn, old, new, label)
    for code, label in _RELABEL:
        conn.execute(
            sa.text("UPDATE org_unit_types SET label = :label WHERE code = :code"),
            {"label": label, "code": code},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for old, new, _label in _RENAMES:
        _rename(conn, new, old, dict(HO="Head Office", RO="Regional Office", ZO="Zonal Office")[old])
    for code, label in [("AO", "Area Office"), ("BRANCH", "Branch")]:
        conn.execute(
            sa.text("UPDATE org_unit_types SET label = :label WHERE code = :code"),
            {"label": label, "code": code},
        )
