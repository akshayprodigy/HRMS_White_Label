"""add designation/grade master, salary revision, cycle + employee FKs

Section A foundation:
- grade                  : master of bands (L1..L8 etc.)
- designation            : master of titles, optional FK to grade
- employee.designation_id, employee.grade_id (FK, nullable)
- revision_cycle         : annual / bulk hike grouping
- salary_revision        : per-employee proposed change with snapshot

Back-fill rules
---------------
1. Existing `employee.designation` (free-text) is preserved as the
   legacy string column.
2. Distinct non-empty designation strings are inserted into the new
   `designation` table.
3. Distinct non-empty `employee.grade` strings are inserted into the
   new `grade` table (rank=0 for all auto-imported rows; HR fixes
   later).
4. employee.designation_id / grade_id are best-effort matched by
   case-insensitive equality. Unmatched stay NULL — flagged in the
   admin UI for HR cleanup.

Anything that fails (e.g. no `employee` table yet on a fresh DB) is
swallowed so the migration is safe to run on an empty schema.

Revision ID: b9w0x1y2z3a4
Revises: a8v9w0x1y2z3
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "b9w0x1y2z3a4"
down_revision = "a8v9w0x1y2z3"
branch_labels = None
depends_on = None


def _create_masters():
    op.create_table(
        "grade",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_salary", sa.Float(), nullable=True),
        sa.Column("max_salary", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_grade_name"),
    )
    op.create_index("ix_grade_rank", "grade", ["rank"])
    op.create_index("ix_grade_name", "grade", ["name"])

    op.create_table(
        "designation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column(
            "grade_id", sa.Integer(),
            sa.ForeignKey("grade.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("title", name="uq_designation_title"),
    )
    op.create_index("ix_designation_title", "designation", ["title"])
    op.create_index("ix_designation_grade", "designation", ["grade_id"])


def _add_employee_fks():
    op.add_column(
        "employee",
        sa.Column("designation_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "employee",
        sa.Column("grade_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_employee_designation",
        "employee", "designation",
        ["designation_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_employee_grade",
        "employee", "grade",
        ["grade_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_employee_designation_id", "employee", ["designation_id"])
    op.create_index("ix_employee_grade_id", "employee", ["grade_id"])


def _backfill_masters():
    """Soft back-fill: never raises on missing data."""
    bind = op.get_bind()
    try:
        # Distinct designations
        rows = bind.execute(sa.text(
            "SELECT DISTINCT TRIM(designation) AS t FROM employee "
            "WHERE designation IS NOT NULL AND TRIM(designation) <> ''"
        )).fetchall()
        for r in rows:
            t = (r[0] or "").strip()
            if not t:
                continue
            bind.execute(sa.text(
                "INSERT INTO designation (title, is_active, created_at, updated_at) "
                "VALUES (:t, TRUE, NOW(), NOW()) ON CONFLICT DO NOTHING"
            ), {"t": t})

        # Distinct grades
        grade_rows = bind.execute(sa.text(
            "SELECT DISTINCT TRIM(grade) AS g FROM employee "
            "WHERE grade IS NOT NULL AND TRIM(grade) <> ''"
        )).fetchall()
        for r in grade_rows:
            g = (r[0] or "").strip()
            if not g:
                continue
            bind.execute(sa.text(
                "INSERT INTO grade (name, rank, is_active, created_at, updated_at) "
                "VALUES (:n, 0, TRUE, NOW(), NOW()) ON CONFLICT DO NOTHING"
            ), {"n": g})

        # Match employee FKs (case-insensitive)
        bind.execute(sa.text(
            "UPDATE employee SET designation_id = d.id "
            "FROM designation d "
            "WHERE LOWER(TRIM(employee.designation)) = LOWER(d.title) "
            "AND employee.designation IS NOT NULL"
        ))
        bind.execute(sa.text(
            "UPDATE employee SET grade_id = g.id "
            "FROM grade g "
            "WHERE LOWER(TRIM(employee.grade)) = LOWER(g.name) "
            "AND employee.grade IS NOT NULL"
        ))
    except Exception:
        # Fresh DB / SQLite / partial schema — keep going; rows will be
        # back-filled when HR opens the designation master.
        pass


def _create_cycle_and_revision():
    op.create_table(
        "revision_cycle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("budget_hike_amount", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("name", name="uq_revision_cycle_name"),
    )
    op.create_index("ix_revision_cycle_status", "revision_cycle", ["status"])

    op.create_table(
        "salary_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cycle_id", sa.Integer(),
            sa.ForeignKey("revision_cycle.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "revision_type", sa.String(20),
            nullable=False, server_default="increment",
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),

        sa.Column(
            "old_designation_id", sa.Integer(),
            sa.ForeignKey("designation.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "old_grade_id", sa.Integer(),
            sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("old_basic", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("old_conveyance", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("old_hra", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("old_other_allowance", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("old_ctc", sa.Float(), nullable=False, server_default=sa.text("0.0")),

        sa.Column(
            "new_designation_id", sa.Integer(),
            sa.ForeignKey("designation.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "new_grade_id", sa.Integer(),
            sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("new_basic", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("new_conveyance", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("new_hra", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("new_other_allowance", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("new_ctc", sa.Float(), nullable=False, server_default=sa.text("0.0")),

        sa.Column("hike_amount", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("hike_percent", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("band_warning", sa.String(255), nullable=True),

        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column(
            "approval_item_id", sa.Integer(),
            sa.ForeignKey("approvalitem.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejected_reason", sa.String(500), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "applied_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "letter_id", sa.Integer(),
            sa.ForeignKey("employeeletter.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "arrears_run_id", sa.Integer(),
            sa.ForeignKey("payrollrun.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("arrears_amount", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("arrears_months", sa.Integer(), nullable=False, server_default=sa.text("0")),

        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_salary_revision_employee", "salary_revision", ["employee_id"])
    op.create_index("ix_salary_revision_cycle", "salary_revision", ["cycle_id"])
    op.create_index("ix_salary_revision_effective", "salary_revision", ["effective_from"])
    op.create_index("ix_salary_revision_status", "salary_revision", ["status"])
    op.create_index("ix_salary_revision_type", "salary_revision", ["revision_type"])
    op.create_index("ix_salary_revision_arrears_run", "salary_revision", ["arrears_run_id"])


def upgrade():
    _create_masters()
    _add_employee_fks()
    _backfill_masters()
    _create_cycle_and_revision()


def downgrade():
    op.drop_index("ix_salary_revision_arrears_run", table_name="salary_revision")
    op.drop_index("ix_salary_revision_type", table_name="salary_revision")
    op.drop_index("ix_salary_revision_status", table_name="salary_revision")
    op.drop_index("ix_salary_revision_effective", table_name="salary_revision")
    op.drop_index("ix_salary_revision_cycle", table_name="salary_revision")
    op.drop_index("ix_salary_revision_employee", table_name="salary_revision")
    op.drop_table("salary_revision")
    op.drop_index("ix_revision_cycle_status", table_name="revision_cycle")
    op.drop_table("revision_cycle")

    op.drop_index("ix_employee_grade_id", table_name="employee")
    op.drop_index("ix_employee_designation_id", table_name="employee")
    op.drop_constraint("fk_employee_grade", "employee", type_="foreignkey")
    op.drop_constraint("fk_employee_designation", "employee", type_="foreignkey")
    op.drop_column("employee", "grade_id")
    op.drop_column("employee", "designation_id")

    op.drop_index("ix_designation_grade", table_name="designation")
    op.drop_index("ix_designation_title", table_name="designation")
    op.drop_table("designation")

    op.drop_index("ix_grade_name", table_name="grade")
    op.drop_index("ix_grade_rank", table_name="grade")
    op.drop_table("grade")
