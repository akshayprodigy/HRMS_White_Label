"""Shared teardown helper: delete every row that references given shift templates.

Walks the SQLAlchemy metadata so new tables with an FK to shift_template are
covered automatically. Rows created by other actors (e.g. an admin drafting in
the UI against a test template) would otherwise make the template delete fail
and abort the whole fixture teardown, leaking users/templates.
"""
from sqlalchemy import delete, select

from app.db.base_class import Base
import app.models  # noqa: F401  (registers all models in metadata)
from app.models.shift import ShiftTemplate


async def purge_shift_templates(db, tpl_ids) -> None:
    tpl_ids = list(tpl_ids)
    if not tpl_ids:
        return
    target = ShiftTemplate.__table__.name
    for table in reversed(Base.metadata.sorted_tables):
        for fk in table.foreign_keys:
            if fk.column.table.name == target and table.name != target:
                await db.execute(delete(table).where(fk.parent.in_(tpl_ids)))
    await db.execute(delete(ShiftTemplate).where(ShiftTemplate.id.in_(tpl_ids)))


async def purge_gap_notifications(db, tpl_ids) -> None:
    """Delete coverage_gap notifications (which may have gone to real roster
    admins) and the gaps for the given shift templates. Call BEFORE
    purge_shift_templates (the gap rows cascade away with the templates)."""
    from app.models.coverage_gap import CoverageGap
    from app.models.notification import Notification

    tpl_ids = list(tpl_ids)
    if not tpl_ids:
        return
    gids = [str(i) for i in (await db.execute(
        select(CoverageGap.id).where(
            CoverageGap.shift_template_id.in_(tpl_ids)))).scalars().all()]
    if gids:
        await db.execute(delete(Notification).where(
            Notification.resource_type == "coverage_gap",
            Notification.resource_id.in_(gids)))


PROTECTED_USER_IDS = (1, 133, 134, 135, 136, 137, 138)


async def purge_users_by_email_like(db, patterns, protected=PROTECTED_USER_IDS) -> int:
    """Delete test users whose email matches any SQL LIKE pattern (plus the
    approval items/steps of their leave requests, which carry no FK). All
    other dependents (leaves, ledger, attendance, employees, notifications,
    user_roles, ...) go via ON DELETE CASCADE. Returns users deleted."""
    from sqlalchemy import or_
    from app.models.approval import ApprovalItem, ApprovalStep
    from app.models.leave import LeaveRequest
    from app.models.user import User

    ids = list((await db.execute(select(User.id).where(
        or_(*[User.email.like(p) for p in patterns]),
        User.id.notin_(list(protected))))).scalars().all())
    if not ids:
        return 0
    leave_ids = [str(i) for i in (await db.execute(select(LeaveRequest.id).where(
        LeaveRequest.employee_id.in_(ids)))).scalars().all()]
    if leave_ids:
        item_ids = list((await db.execute(select(ApprovalItem.id).where(
            ApprovalItem.resource_type == "leave",
            ApprovalItem.resource_id.in_(leave_ids)))).scalars().all())
        if item_ids:
            await db.execute(delete(ApprovalStep).where(
                ApprovalStep.approval_item_id.in_(item_ids)))
            await db.execute(delete(ApprovalItem).where(
                ApprovalItem.id.in_(item_ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))
    await db.commit()
    return len(ids)
