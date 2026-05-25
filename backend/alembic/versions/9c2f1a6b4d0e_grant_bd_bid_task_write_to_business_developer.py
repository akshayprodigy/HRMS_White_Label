"""Grant BD bid-task write to Business Developer

Revision ID: 9c2f1a6b4d0e
Revises: f1c0d2e4a6b8
Create Date: 2026-03-12

This is a data migration to ensure production has consistent RBAC defaults.

- Ensures the bid-task and bid-review read/write permissions exist.
- Ensures role `Business Developer` exists and has those permissions.
- Also grants the same permissions to legacy role `BD` if present.

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c2f1a6b4d0e"
down_revision: Union[str, None] = "f1c0d2e4a6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PERMISSIONS: list[tuple[str, str]] = [
    ("bd bid task read", "Read BD bid tasks"),
    ("bd bid task write", "Create and assign BD bid tasks"),
    ("bd bid review read", "Read BD bid reviews"),
    ("bd bid review write", "Create/update BD bid reviews"),
]

_BD_ROLE_NAME = "Business Developer"
_BD_ROLE_DESC = "Sales and lead management"


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


def _get_role_id(conn: sa.Connection, *, name: str) -> int | None:
    return conn.execute(
        sa.text("SELECT id FROM role WHERE name = :name"),
        {"name": name},
    ).scalar_one_or_none()


def _ensure_role(conn: sa.Connection, *, name: str, description: str) -> int:
    role_id = _get_role_id(conn, name=name)
    if role_id is not None:
        return int(role_id)

    conn.execute(
        sa.text(
            "INSERT INTO role (name, description) VALUES (:name, :desc)"
        ),
        {"name": name, "desc": description},
    )
    role_id = _get_role_id(conn, name=name)
    if role_id is None:
        raise RuntimeError(f"Failed to create role: {name}")
    return int(role_id)


def _get_role_ids(conn: sa.Connection, *, bd_role_id: int) -> list[int]:
    rows = conn.execute(
        sa.text(
            "SELECT id FROM role WHERE name IN (:r1, :r2)"
        ),
        {"r1": _BD_ROLE_NAME, "r2": "BD"},
    ).fetchall()
    ids = [int(r[0]) for r in rows]
    if bd_role_id not in ids:
        ids.append(bd_role_id)
    return ids


def _ensure_role_permission(
    conn: sa.Connection, *, role_id: int, permission_id: int
) -> None:
    # MariaDB supports DUAL; use NOT EXISTS to stay idempotent.
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
    bd_role_id = _ensure_role(
        conn,
        name=_BD_ROLE_NAME,
        description=_BD_ROLE_DESC,
    )

    role_ids = _get_role_ids(conn, bd_role_id=bd_role_id)

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
    # Safe to keep roles/permissions; remove only the role assignments.
    conn = op.get_bind()
    bd_role_id = _get_role_id(conn, name=_BD_ROLE_NAME)
    if bd_role_id is None:
        return

    role_ids = _get_role_ids(conn, bd_role_id=int(bd_role_id))

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
