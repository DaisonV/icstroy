"""Add tasks, notifications and application activity

Revision ID: 9a41f8d7c2b0
Revises: edfb09d6e51e
Create Date: 2026-07-14 04:10:00

"""
from alembic import op
import sqlalchemy as sa


revision = "9a41f8d7c2b0"
down_revision = "edfb09d6e51e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("application_activities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_application_activities_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_application_activities_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_application_activities_user_id"), ["user_id"], unique=False)

    op.create_table(
        "crm_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "DONE", "CANCELLED", name="taskstatus", native_enum=False), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("crm_tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_crm_tasks_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_crm_tasks_assignee_id"), ["assignee_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_crm_tasks_due_at"), ["due_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_crm_tasks_status"), ["status"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notifications_application_id"), ["application_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_notifications_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_notifications_is_read"), ["is_read"], unique=False)
        batch_op.create_index(batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_user_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_is_read"))
        batch_op.drop_index(batch_op.f("ix_notifications_created_at"))
        batch_op.drop_index(batch_op.f("ix_notifications_application_id"))
    op.drop_table("notifications")

    with op.batch_alter_table("crm_tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_crm_tasks_status"))
        batch_op.drop_index(batch_op.f("ix_crm_tasks_due_at"))
        batch_op.drop_index(batch_op.f("ix_crm_tasks_assignee_id"))
        batch_op.drop_index(batch_op.f("ix_crm_tasks_application_id"))
    op.drop_table("crm_tasks")

    with op.batch_alter_table("application_activities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_application_activities_user_id"))
        batch_op.drop_index(batch_op.f("ix_application_activities_created_at"))
        batch_op.drop_index(batch_op.f("ix_application_activities_application_id"))
    op.drop_table("application_activities")
