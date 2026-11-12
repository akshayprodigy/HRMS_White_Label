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
