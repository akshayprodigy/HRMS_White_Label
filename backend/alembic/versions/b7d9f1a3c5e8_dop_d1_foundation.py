"""dop d1: manager kinds/assignments, posts, post holders, acting covers

Delegation of Powers D1 foundation. Seeds three manager kinds, backfills one
'reporting' assignment per user with a manager other than themselves, and
adds the 'dop manage' permission (granted to Super Admin).

NOTE: MariaDB DDL is not transactional. If the upgrade fails midway, drop any
of acting_assignment, manager_assignment, post_holder, post, manager_kind that
were created, and delete the 'dop manage' permission (and its role_permissions
rows) if inserted, before retrying. alembic_version stays at a6b8d0f2c4e7.

Revision ID: b7d9f1a3c5e8
Revises: a6b8d0f2c4e7
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d9f1a3c5e8"
down_revision = "a6b8d0f2c4e7"
branch_labels = None
depends_on = None


def _created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                     server_default=sa.func.now())


def upgrade():
    op.create_table(
        "manager_kind",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="1"),
        sa.Column("is_system", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.UniqueConstraint("code", name="uq_manager_kind_code"),
    )

    op.create_table(
        "post",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("parent_post_id", sa.Integer(), nullable=True),
        sa.Column("heads_department_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="1"),
        _created_at(),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"],
                                name="fk_post_department",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_post_id"], ["post.id"],
                                name="fk_post_parent", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["heads_department_id"], ["department.id"],
                                name="fk_post_heads_department",
                                ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_post_code"),
        sa.UniqueConstraint("heads_department_id",
                            name="uq_post_heads_department_id"),
    )

    op.create_table(
        "post_holder",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["post_id"], ["post.id"],
                                name="fk_post_holder_post",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"],
                                name="fk_post_holder_user",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"],
                                name="fk_post_holder_created_by",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_post_holder_post", "post_holder",
                    ["post_id", "starts_on"])
    op.create_index("ix_post_holder_user_id", "post_holder", ["user_id"])

    op.create_table(
        "manager_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manager_kind_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_user_id", sa.Integer(), nullable=True),
        sa.Column("scope_department_id", sa.Integer(), nullable=True),
        sa.Column("scope_location", sa.String(100), nullable=True),
        sa.Column("manager_user_id", sa.Integer(), nullable=True),
        sa.Column("manager_post_id", sa.Integer(), nullable=True),
        sa.Column("subdomains", sa.JSON(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        _created_at(),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["manager_kind_id"], ["manager_kind.id"],
                                name="fk_mgr_asg_kind", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scope_user_id"], ["user.id"],
                                name="fk_mgr_asg_scope_user",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scope_department_id"], ["department.id"],
                                name="fk_mgr_asg_scope_dept",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manager_user_id"], ["user.id"],
                                name="fk_mgr_asg_manager_user",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manager_post_id"], ["post.id"],
                                name="fk_mgr_asg_manager_post",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"],
                                name="fk_mgr_asg_created_by",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_mgr_asg_kind_scope", "manager_assignment",
                    ["manager_kind_id", "scope_type"])
    op.create_index("ix_mgr_asg_user", "manager_assignment",
                    ["scope_user_id"])
    op.create_index("ix_manager_assignment_manager_user_id",
                    "manager_assignment", ["manager_user_id"])
    op.create_index("ix_manager_assignment_manager_post_id",
                    "manager_assignment", ["manager_post_id"])

    op.create_table(
        "acting_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("covers_user_id", sa.Integer(), nullable=True),
        sa.Column("covers_post_id", sa.Integer(), nullable=True),
        sa.Column("acting_user_id", sa.Integer(), nullable=False),
        sa.Column("subdomains", sa.JSON(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("original_can_act", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.Column("only_when_on_leave", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        _created_at(),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["covers_user_id"], ["user.id"],
                                name="fk_acting_covers_user",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["covers_post_id"], ["post.id"],
                                name="fk_acting_covers_post",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acting_user_id"], ["user.id"],
                                name="fk_acting_acting_user",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"],
                                name="fk_acting_created_by",
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["user.id"],
                                name="fk_acting_revoked_by",
                                ondelete="SET NULL"),
    )
    op.create_index("ix_acting_assignment_covers_user_id",
                    "acting_assignment", ["covers_user_id"])
    op.create_index("ix_acting_assignment_covers_post_id",
                    "acting_assignment", ["covers_post_id"])
    op.create_index("ix_acting_assignment_acting_user_id",
                    "acting_assignment", ["acting_user_id"])

    op.execute("INSERT INTO manager_kind (code, name, sort_order, is_active, "
               "is_system) VALUES ('reporting','Reporting manager',0,1,1),"
               "('functional','Functional manager',1,1,0),"
               "('project','Project manager',2,1,0)")
    op.execute(
        "INSERT INTO manager_assignment (manager_kind_id, scope_type, "
        "scope_user_id, manager_user_id, subdomains, starts_on, note, "
        "created_at) SELECT k.id, 'user', u.id, u.manager_id, '[]', "
        "'2000-01-01', 'Copied from reporting manager', UTC_TIMESTAMP() "
        "FROM user u JOIN manager_kind k ON k.code = 'reporting' "
        "WHERE u.manager_id IS NOT NULL AND u.manager_id <> u.id")
    op.execute("INSERT INTO permission (name, description) SELECT "
               "'dop manage', 'Manage managers, posts and acting covers' "
               "FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM permission "
               "WHERE name = 'dop manage')")
    op.execute("INSERT IGNORE INTO role_permissions (role_id, permission_id) "
               "SELECT r.id, p.id FROM role r, permission p WHERE "
               "r.name = 'Super Admin' AND p.name = 'dop manage'")


def downgrade():
    op.execute("DELETE FROM role_permissions WHERE permission_id IN "
               "(SELECT id FROM permission WHERE name = 'dop manage')")
    op.execute("DELETE FROM permission WHERE name = 'dop manage'")
    op.drop_table("acting_assignment")
    op.drop_table("manager_assignment")
    op.drop_table("post_holder")
    op.drop_table("post")
    op.drop_table("manager_kind")
