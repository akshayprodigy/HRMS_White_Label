# pyright: reportMissingImports=false

"""Utility script: create a role and assign it to users.

Run inside the backend container or with PYTHONPATH set to the backend folder.
"""

import argparse
import asyncio
import importlib
import os
import sys
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload


USER_MODELS_MODULE = "app.models.user"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a role (if missing) and assign it to users by "
            "email/user_id."
        )
    )
    parser.add_argument(
        "--role",
        required=True,
        help='Role name (e.g. "Operations Head")',
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Optional role description",
    )
    parser.add_argument(
        "--email",
        action="append",
        default=[],
        help=(
            "User email to assign the role to. Can be provided multiple times."
        ),
    )
    parser.add_argument(
        "--user-id",
        action="append",
        default=[],
        help=(
            "User ID to assign the role to. Can be provided multiple times."
        ),
    )
    parser.add_argument(
        "--target-role",
        action="append",
        default=[],
        help=(
            "Assign the role to all users who currently have this role. "
            "Can be provided multiple times."
        ),
    )
    return parser.parse_args()


def _normalize_emails(emails: Sequence[str]) -> list[str]:
    out: list[str] = []
    for e in emails:
        e = (e or "").strip().lower()
        if e:
            out.append(e)
    return list(dict.fromkeys(out))


def _normalize_ints(values: Sequence[str]) -> list[int]:
    out: list[int] = []
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        out.append(int(v))
    return list(dict.fromkeys(out))


def _normalize_role_names(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = (v or "").strip()
        if v:
            out.append(v)
    return list(dict.fromkeys(out))


async def _get_or_create_role(
    *,
    session: AsyncSession,
    role_name: str,
    description: str | None,
):
    role_model = importlib.import_module(USER_MODELS_MODULE).Role

    role = (
        await session.execute(
            select(role_model).where(role_model.name == role_name)
        )
    ).scalars().first()

    created = False
    if not role:
        role = role_model(name=role_name, description=description)
        session.add(role)
        await session.flush()
        created = True
    elif description and (role.description or "") != description:
        role.description = description
        session.add(role)

    return role, created


async def _load_target_users(
    *,
    session: AsyncSession,
    emails: list[str],
    user_ids: list[int],
    target_roles: list[str],
):
    user_model = importlib.import_module(USER_MODELS_MODULE).User
    role_model = importlib.import_module(USER_MODELS_MODULE).Role

    targets: list[Any] = []

    if user_ids:
        res = await session.execute(
            select(user_model)
            .where(user_model.id.in_(user_ids))
            .options(selectinload(user_model.roles))
        )
        targets.extend(res.scalars().unique().all())

    if emails:
        res = await session.execute(
            select(user_model)
            .where(user_model.email.in_(emails))
            .options(selectinload(user_model.roles))
        )
        targets.extend(res.scalars().unique().all())

    if target_roles:
        res = await session.execute(
            select(user_model)
            .join(user_model.roles)
            .where(role_model.name.in_(target_roles))
            .options(selectinload(user_model.roles))
        )
        targets.extend(res.scalars().unique().all())

    targets_by_id = {int(u.id): u for u in targets}
    return list(targets_by_id.values())


def _compute_missing_targets(
    *,
    emails: list[str],
    user_ids: list[int],
    users,
) -> tuple[list[str], list[int]]:
    seen_emails = {str(u.email or "").strip().lower() for u in users}
    seen_ids = {int(u.id) for u in users}
    missing_emails = sorted(set(emails) - seen_emails)
    missing_ids = sorted(set(user_ids) - seen_ids)
    return missing_emails, missing_ids


def _assign_role_to_users(*, users, role):
    assigned = 0
    already = 0
    for user in users:
        existing = {r.name for r in (user.roles or [])}
        if role.name in existing:
            already += 1
            continue
        user.roles.append(role)
        assigned += 1
    return assigned, already


async def _run() -> int:
    # Allow running this script directly.
    # without requiring a pre-set PYTHONPATH.
    sys.path.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    )

    settings = importlib.import_module("app.core.config").settings

    args = _parse_args()

    role_name = (args.role or "").strip()
    if not role_name:
        raise SystemExit("--role is required")

    emails = _normalize_emails(args.email)
    user_ids = _normalize_ints(args.user_id)
    target_roles = _normalize_role_names(args.target_role)

    if not emails and not user_ids and not target_roles:
        raise SystemExit(
            "Provide at least one of: --email, --user-id, --target-role"
        )

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    async_session_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with async_session_local() as session:
            role, created = await _get_or_create_role(
                session=session,
                role_name=role_name,
                description=args.description,
            )
            if created:
                print(f"Created role: {role.name} (id={role.id})")
            else:
                print(f"Role exists: {role.name} (id={role.id})")

            targets = await _load_target_users(
                session=session,
                emails=emails,
                user_ids=user_ids,
                target_roles=target_roles,
            )

            missing_emails, missing_ids = _compute_missing_targets(
                emails=emails,
                user_ids=user_ids,
                users=targets,
            )

            if missing_emails:
                print(f"WARNING: Missing users for emails: {missing_emails}")
            if missing_ids:
                print(f"WARNING: Missing users for user_ids: {missing_ids}")

            assigned, already = _assign_role_to_users(
                users=targets, role=role
            )
            for user in targets:
                session.add(user)

            await session.commit()

            print(
                "Done. "
                f"Assigned={assigned}, "
                f"already_had_role={already}, "
                f"total_targets={len(targets)}"
            )
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
