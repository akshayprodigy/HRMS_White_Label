from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.db.models.iam import Permission, Role, RolePermission, User, UserRole

_DEFAULT_ADMIN_PERMISSIONS: tuple[str, ...] = (
    "admin.users.read",
    "admin.users.write",
    "admin.roles.read",
    "admin.roles.write",
    "admin.permissions.read",
    "admin.permissions.write",
    "admin.audit_logs.read",
    "core.organizations.read",
    "core.organizations.write",
    "core.sites.read",
    "core.sites.write",
    "core.projects.read",
    "core.projects.write",
    "core.cost_centers.read",
    "core.cost_centers.write",
    "hr.employees.read",
    "hr.employees.write",
    "hr.employee_documents.read",
    "hr.employee_documents.write",
    "hr.employee_assets.read",
    "hr.employee_assets.write",
    "hr.leave_types.read",
    "hr.leave_types.write",
    "hr.leave_policies.read",
    "hr.leave_policies.write",
    "hr.leave_balances.read",
    "hr.leave_requests.read",
    "hr.leave_requests.apply",
    "hr.leave_requests.approve",
    "hr.leave_requests.reject",
    "hr.leave_requests.cancel",
    "hr.holiday_calendars.read",
    "hr.holiday_calendars.write",
    "admin.jobs.leave_credit",

    # HR • Attendance
    "hr.attendance.read",
    "hr.attendance.write",

    # Inventory
    "inventory.uoms.read",
    "inventory.uoms.write",
    "inventory.items.read",
    "inventory.items.write",
    "inventory.warehouses.read",
    "inventory.warehouses.write",
    "inventory.grns.read",
    "inventory.grns.write",
    "inventory.issues.read",
    "inventory.issues.write",
    "inventory.reports.project_consumption.read",

    # Projects • DPR
    "projects.dprs.read",
    "projects.dprs.write",
    "projects.dprs.metrics.read",

    # Projects • Finance / Profitability
    "projects.finance.read",
    "projects.finance.write",
    "projects.profitability.read",
)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _get_or_create_permissions(db, codes: Sequence[str]) -> list[Permission]:
    stmt = select(Permission).where(Permission.code.in_(list(codes)))
    existing = {p.code: p for p in db.execute(stmt).scalars().all()}
    out: list[Permission] = []
    for code in codes:
        perm = existing.get(code)
        if perm is None:
            perm = Permission(code=code, description=None)
            db.add(perm)
        out.append(perm)
    db.commit()
    return out


def _get_or_create_role(db, name: str) -> Role:
    role = db.execute(
        select(Role).where(Role.name == name)
    ).scalar_one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def _get_or_create_user(db, email: str, password: str) -> User:
    user = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _ensure_role_permissions(
    db,
    role: Role,
    permissions: Sequence[Permission],
) -> None:
    perm_ids = {p.id for p in permissions}
    existing = set(
        db.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role.id
            )
        ).scalars().all()
    )
    missing = perm_ids - existing
    for perm_id in missing:
        db.add(RolePermission(role_id=role.id, permission_id=perm_id))
    db.commit()


def _ensure_user_role(db, user: User, role: Role) -> None:
    existing = db.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()


def main() -> int:
    email = _require_env("BOOTSTRAP_ADMIN_EMAIL")
    password = _require_env("BOOTSTRAP_ADMIN_PASSWORD")
    role_name = os.getenv("BOOTSTRAP_ADMIN_ROLE", "admin")

    with SessionLocal() as db:
        permissions = _get_or_create_permissions(
            db,
            _DEFAULT_ADMIN_PERMISSIONS,
        )
        role = _get_or_create_role(db, role_name)
        _ensure_role_permissions(db, role, permissions)
        user = _get_or_create_user(db, email, password)
        _ensure_user_role(db, user, role)

    print(f"Bootstrapped admin user: {email} (role={role_name})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
