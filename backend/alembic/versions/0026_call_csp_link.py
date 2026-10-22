"""link a call session to a CSP (Kiosk Operator)

A call to a Kiosk Operator could never be identified before: identity resolution
matched the number against Officials only, so a known CSP's call fell through to
"unregistered". This adds call_sessions.csp_id so a CSP call is tied to its
operator and shown by name.

Revision ID: 0026_call_csp_link
Revises: 0025_csp_birthday_wish
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_call_csp_link"
down_revision: Union[str, None] = "0025_csp_birthday_wish"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("call_sessions") as batch:
        batch.add_column(sa.Column("csp_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_call_sessions_csp_id", "csps", ["csp_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_call_sessions_csp_id", ["csp_id"])


def downgrade() -> None:
    with op.batch_alter_table("call_sessions") as batch:
        batch.drop_index("ix_call_sessions_csp_id")
        batch.drop_constraint("fk_call_sessions_csp_id", type_="foreignkey")
        batch.drop_column("csp_id")
