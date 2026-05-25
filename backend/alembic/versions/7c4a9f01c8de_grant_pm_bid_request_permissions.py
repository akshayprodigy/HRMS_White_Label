"""Grant PM bid-request permissions

Revision ID: 7c4a9f01c8de
Revises: 5f7d3a1c2b90
Create Date: 2026-03-12

Ensure the PM role can access the bid-request flows by granting:
- bd bid task read
- bd bid review read
- bd bid review write

This is idempotent and production-safe.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c4a9f01c8de"
down_revision: Union[str, None] = "5f7d3a1c2b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PERMISSIONS: list[tuple[str, str]] = [
    ("bd bid task read", "Read lead bid tasks and assignments"),
    ("bd bid review read", "Read PM bid reviews for a lead"),
    ("bd bid review write", "Create/update/submit PM bid reviews"),
]

_PM_ROLE_NAME = "PM"
_PM_ROLE_DESCRIPTION = "Project Management"

_EXTRA_ROLE_NAMES = [
    "Project Manager",
    "PROJECT MANAGER",
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
        sa.text("INSERT INTO role (name, description) VALUES (:name, :desc)"),
        {"name": name, "desc": description},
    )
    role_id = _get_role_id(conn, name=name)
    if role_id is None:
        raise RuntimeError(f"Failed to create role: {name}")
    return int(role_id)


def _get_target_role_ids(conn: sa.Connection) -> list[int]:
    role_ids: list[int] = []

    pm_id = _get_role_id(conn, name=_PM_ROLE_NAME)
    if pm_id is not None:
        role_ids.append(int(pm_id))

    for extra in _EXTRA_ROLE_NAMES:
        rid = _get_role_id(conn, name=extra)
        if rid is not None:
            role_ids.append(int(rid))

    # Unique, stable order
    return list(dict.fromkeys(role_ids))


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

    # Ensure primary PM role exists.
    _ensure_role(conn, name=_PM_ROLE_NAME, description=_PM_ROLE_DESCRIPTION)

    role_ids = _get_target_role_ids(conn)
    if not role_ids:
        return

    for perm_name, perm_desc in _PERMISSIONS:
        perm_id = _ensure_permission(
            conn, name=perm_name, description=perm_desc
        )
        for role_id in role_ids:
            _ensure_role_permission(
                conn, role_id=role_id, permission_id=perm_id
            )


def downgrade() -> None:
    conn = op.get_bind()
    role_ids = _get_target_role_ids(conn)
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
