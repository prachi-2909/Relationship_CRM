"""organisation: unit types, org units, officials, field provenance

Revision ID: 0002_organisation
Revises: 0001_foundation
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_organisation"
down_revision: Union[str, None] = "0001_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_unit_status = sa.Enum(
    "active", "archived", name="org_unit_status", native_enum=False, length=16
)
_official_status = sa.Enum(
    "active", "archived", name="official_status", native_enum=False, length=16
)
_official_verif = sa.Enum(
    "unverified",
    "partially_verified",
    "verified",
    name="official_verification",
    native_enum=False,
    length=24,
)
_field_verif = sa.Enum(
    "unverified", "verified", name="field_verification", native_enum=False, length=16
)

_SEED_TYPES = [
    ("HO", "Head Office", 10),
    ("RO", "Regional Office", 20),
    ("ZO", "Zonal Office", 30),
    ("AO", "Area Office", 40),
    ("BRANCH", "Branch", 50),
]


def upgrade() -> None:
    org_unit_types = op.create_table(
        "org_unit_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_org_unit_types_code", "org_unit_types", ["code"], unique=True)

    op.bulk_insert(
        org_unit_types,
        [
            {"code": code, "label": label, "rank": rank, "active": True}
            for code, label, rank in _SEED_TYPES
        ],
    )

    op.create_table(
        "organization_units",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "type_code",
            sa.String(32),
            sa.ForeignKey("org_unit_types.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Integer,
            sa.ForeignKey("organization_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column("status", _unit_status, nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_organization_units_name", "organization_units", ["name"])
    op.create_index(
        "ix_organization_units_type_code", "organization_units", ["type_code"]
    )
    op.create_index(
        "ix_organization_units_parent_id", "organization_units", ["parent_id"]
    )

    op.create_table(
        "officials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("designation", sa.String(200), nullable=True),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column("level", sa.String(120), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column(
            "organization_unit_id",
            sa.Integer,
            sa.ForeignKey("organization_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", _official_status, nullable=False, server_default="active"
        ),
        sa.Column(
            "verification_status",
            _official_verif,
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_officials_name", "officials", ["name"])
    op.create_index("ix_officials_level", "officials", ["level"])
    op.create_index(
        "ix_officials_organization_unit_id", "officials", ["organization_unit_id"]
    )
    op.create_index(
        "ix_officials_verification_status", "officials", ["verification_status"]
    )

    op.create_table(
        "official_field_provenance",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Integer, nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column(
            "verification_status",
            _field_verif,
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "verified_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("official_id", "field", name="uq_official_field"),
    )
    op.create_index(
        "ix_official_field_provenance_official_id",
        "official_field_provenance",
        ["official_id"],
    )


def downgrade() -> None:
    op.drop_table("official_field_provenance")
    op.drop_table("officials")
    op.drop_table("organization_units")
    op.drop_index("ix_org_unit_types_code", table_name="org_unit_types")
    op.drop_table("org_unit_types")
