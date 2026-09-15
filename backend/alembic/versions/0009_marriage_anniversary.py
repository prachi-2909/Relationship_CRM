"""marriage anniversary as a dated fact + engagement moment

Revision ID: 0009_marriage_anniversary
Revises: 0008_real_unit_types
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_marriage_anniversary"
down_revision: Union[str, None] = "0008_real_unit_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# both columns are plain VARCHAR (native_enum=False) - no enum type to alter,
# just widen the column so "marriage_anniversary" (20 chars) fits comfortably.
# SQLite doesn't enforce VARCHAR length; this is for Postgres portability.


def upgrade() -> None:
    with op.batch_alter_table("official_dates") as batch_op:
        batch_op.alter_column(
            "kind", existing_type=sa.String(length=16), type_=sa.String(length=24)
        )
    with op.batch_alter_table("engagement_moments") as batch_op:
        batch_op.alter_column(
            "type", existing_type=sa.String(length=20), type_=sa.String(length=24)
        )


def downgrade() -> None:
    with op.batch_alter_table("engagement_moments") as batch_op:
        batch_op.alter_column(
            "type", existing_type=sa.String(length=24), type_=sa.String(length=20)
        )
    with op.batch_alter_table("official_dates") as batch_op:
        batch_op.alter_column(
            "kind", existing_type=sa.String(length=24), type_=sa.String(length=16)
        )
