"""tasks, follow-ups, and officials import; officials.email

Revision ID: 0004_tasks_and_imports
Revises: 0003_relationships_interactions
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tasks_and_imports"
down_revision: Union[str, None] = "0003_relationships_interactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_task_status = sa.Enum(
    "open", "done", "cancelled", name="task_status", native_enum=False, length=16
)
_import_status = sa.Enum(
    "pending", "committed", "cancelled", name="data_import_status",
    native_enum=False, length=16,
)
_row_action = sa.Enum(
    "create", "merge", "skip", name="import_row_action", native_enum=False, length=8
)


def upgrade() -> None:
    with op.batch_alter_table("officials") as batch:
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
    op.create_index("ix_officials_email", "officials", ["email"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "relationship_id",
            sa.Integer,
            sa.ForeignKey("relationships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _task_status, nullable=False, server_default="open"),
        sa.Column(
            "source_interaction_id",
            sa.Integer,
            sa.ForeignKey("interactions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_to",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_relationship_id", "tasks", ["relationship_id"])
    op.create_index("ix_tasks_official_id", "tasks", ["official_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_due_at", "tasks", ["due_at"])
    op.create_index("ix_tasks_assigned_to", "tasks", ["assigned_to"])

    op.create_table(
        "data_imports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("status", _import_status, nullable=False, server_default="pending"),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_data_imports_status", "data_imports", ["status"])

    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "import_id",
            sa.Integer,
            sa.ForeignKey("data_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("raw", sa.JSON, nullable=False),
        sa.Column("normalized", sa.JSON, nullable=False),
        sa.Column(
            "resolved_official_id",
            sa.Integer,
            sa.ForeignKey("officials.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", _row_action, nullable=False),
        sa.Column("confidence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.String(300), nullable=True),
    )
    op.create_index("ix_import_rows_import_id", "import_rows", ["import_id"])


def downgrade() -> None:
    op.drop_table("import_rows")
    op.drop_table("data_imports")
    op.drop_table("tasks")
    op.drop_index("ix_officials_email", table_name="officials")
    with op.batch_alter_table("officials") as batch:
        batch.drop_column("email")
