"""Grant BD bid-task perms to BD MANAGER

Revision ID: 5f7d3a1c2b90
Revises: 9c2f1a6b4d0e
Create Date: 2026-03-12

Production fix: some environments have BD users assigned to `BD MANAGER` (or
legacy `BD`) instead of `Business Developer`. Ensure bid-task + bid-review
read/write permissions exist and are granted to those roles when present.

This is idempotent.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f7d3a1c2b90"
down_revision: Union[str, None] = "9c2f1a6b4d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PERMISSIONS: list[tuple[str, str]] = [
    ("bd bid task read", "Read BD bid tasks"),
    ("bd bid task write", "Create and assign BD bid tasks"),
    ("bd bid review read", "Read BD bid reviews"),
    ("bd bid review write", "Create/update BD bid reviews"),
]

_ROLE_NAMES = [
    "Business Developer",
    "BD",
    "BD MANAGER",
]


def _get_permission_id(conn: sa.Connection, *, name: str) -> int | None:
    return conn.execute(
        sa.text("SELECT id FROM permission WHERE name = :name"),
        {"name": name},
    ).scalar_one_or_none()


def _ensure_permission(
    conn: sa.Connection, *, name: str, description: str
) -> int:
    perm_id = _get_permission_id(conn, name=name)
    if perm_id is not None:
        return int(perm_id)

    conn.execute(
        sa.text(
            "INSERT INTO permission (name, description) VALUES (:name, :desc)"
        ),
        {"name": name, "desc": description},
    )
    perm_id = _get_permission_id(conn, name=name)
    if perm_id is None:
        raise RuntimeError(f"Failed to create permission: {name}")
    return int(perm_id)


def _get_role_ids(conn: sa.Connection) -> list[int]:
    # Don't create roles here; only grant if role exists.
    rows = conn.execute(
        sa.text(
            "SELECT id FROM role WHERE name IN (:r1, :r2, :r3)"
        ),
        {"r1": _ROLE_NAMES[0], "r2": _ROLE_NAMES[1], "r3": _ROLE_NAMES[2]},
    ).fetchall()
    return [int(r[0]) for r in rows]


def _ensure_role_permission(
    conn: sa.Connection, *, role_id: int, permission_id: int
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :role_id, :permission_id
            FROM DUAL
            WHERE NOT EXISTS (
              SELECT 1 FROM role_permissions
              WHERE role_id = :role_id AND permission_id = :permission_id
            )
            """
        ),
        {"role_id": role_id, "permission_id": permission_id},
    )


def upgrade() -> None:
    conn = op.get_bind()
    role_ids = _get_role_ids(conn)
    if not role_ids:
        return

    for perm_name, perm_desc in _PERMISSIONS:
        perm_id = _ensure_permission(
            conn,
            name=perm_name,
            description=perm_desc,
        )
        for role_id in role_ids:
            _ensure_role_permission(
                conn,
                role_id=role_id,
                permission_id=perm_id,
            )


def downgrade() -> None:
    conn = op.get_bind()
    role_ids = _get_role_ids(conn)
    if not role_ids:
        return

    for perm_name, _perm_desc in _PERMISSIONS:
        perm_id = _get_permission_id(conn, name=perm_name)
        if perm_id is None:
            continue

        for role_id in role_ids:
            conn.execute(
                sa.text(
                    "DELETE FROM role_permissions "
                    "WHERE role_id = :role_id "
                    "AND permission_id = :permission_id"
                ),
                {"role_id": role_id, "permission_id": int(perm_id)},
            )
