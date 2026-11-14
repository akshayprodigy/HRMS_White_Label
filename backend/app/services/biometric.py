"""Biometric raw-tap storage and the apply engine (Roadmap v2 Phase 4, Task 3).

Every tap is stored first as an immutable BiometricPunch; `apply_punch` then
folds it into Attendance with the first-in / last-out rule per employee per
resolved work day. The fold is ORDER INDEPENDENT: the in / out of a day are a
pure function of the set of taps (min / max), however they arrive:

    in  = min(app punch-in, every tap of the day)
    out = max(app punch-out, every tap of the day), only when out - in >=
          dedupe_seconds (closer taps are duplicates of the punch-in)

Taps absorbed as DUPLICATE keep `attendance_id`, so a later, earlier-timestamped
tap can still reconstruct the day from them. Everything here flushes only; the
caller commits.
"""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import OperationalError

from app.core.datetime_utils import as_utc
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.biometric import (
    BiometricDevice, BiometricDeviceStatus, BiometricPunch,
    BiometricPunchState, BiometricUserMap,
)
from app.models.user import User
from app.services import punch
from app.services.roster import is_lock_conflict
from app.services.attendance_lock import LockRetry, assert_attendance_editable

log = logging.getLogger(__name__)

DEFAULT_DEDUPE_SECONDS = 120
RAW_MAX = 500
PIN_MAX = 32
# Freshly stored tap, not yet applied. apply_punch always replaces it; if a
# caller dies in between, apply_pending sweeps it up.
PENDING_APPLY = "received"

_S = BiometricPunchState


async def resolve_user_id(db, device_id: Optional[int], pin: str) -> Optional[int]:
    """Device-specific BiometricUserMap first, then the global (device NULL) one."""
    if device_id is not None:
        uid = (await db.execute(select(BiometricUserMap.user_id).where(
            BiometricUserMap.device_id == device_id,
            BiometricUserMap.pin == pin))).scalars().first()
        if uid is not None:
            return uid
    return (await db.execute(select(BiometricUserMap.user_id).where(
        BiometricUserMap.device_id.is_(None),
        BiometricUserMap.pin == pin))).scalars().first()


def _dedupe_key(source_key: str, pin: str, when: datetime) -> str:
    return hashlib.sha256(
        f"{source_key}|{pin}|{as_utc(when).isoformat()}".encode()
    ).hexdigest()


async def store_taps(
    db, *, source: str, device: Optional[BiometricDevice],
    taps: list[tuple[str, datetime, Optional[str], Optional[str], str]],
    import_batch: Optional[str] = None,
) -> tuple[int, list[BiometricPunch]]:
    """Insert raw taps (INSERT IGNORE on dedupe_key, so re-sent batches are
    no-ops). taps = (pin, utc_time, status, verify, raw). Returns (number newly
    inserted, the new rows). Initial state: PENDING_DEVICE when the device is
    not active, UNMAPPED when no user resolves, else PENDING_APPLY."""
    source_key = device.serial if device is not None else "import"
    device_active = (device is None
                     or device.status == BiometricDeviceStatus.ACTIVE)
    new_keys: list[str] = []
    resolved: dict[str, Optional[int]] = {}
    for pin, when, status, verify, raw in taps:
        pin = (pin or "")[:PIN_MAX]
        when = as_utc(when)
        key = _dedupe_key(source_key, pin, when)
        if pin not in resolved:
            resolved[pin] = await resolve_user_id(
                db, device.id if device is not None else None, pin)
        uid = resolved[pin]
        if not device_active:
            state = _S.PENDING_DEVICE
        elif uid is None:
            state = _S.UNMAPPED
        else:
            state = PENDING_APPLY
        res = await db.execute(mysql_insert(BiometricPunch).values(
            dedupe_key=key, source=source,
            device_id=device.id if device is not None else None,
            import_batch=import_batch, pin=pin, punch_time=when,
            device_status=(status[:8] if status else None),
            verify_type=(verify[:8] if verify else None),
            raw=(raw or "")[:RAW_MAX] or None, user_id=uid, state=state,
            created_at=datetime.now(timezone.utc),
        ).prefix_with("IGNORE"))
        if res.rowcount == 1:
            new_keys.append(key)
    if not new_keys:
        return 0, []
    rows: list[BiometricPunch] = []
    for i in range(0, len(new_keys), 500):
        rows.extend((await db.execute(select(BiometricPunch).where(
            BiometricPunch.dedupe_key.in_(new_keys[i:i + 500])
        ).execution_options(populate_existing=True))).scalars().all())
    rows.sort(key=lambda r: (as_utc(r.punch_time), r.id))
    return len(new_keys), rows


def _finish(bp: BiometricPunch, state: str, attendance_id: Optional[int] = None,
            error: Optional[str] = None) -> None:
    bp.state = state
    bp.attendance_id = attendance_id
    bp.error = error[:255] if error else None
    bp.applied_at = datetime.now(timezone.utc)


async def _day_tap_times(db, attendance_id: int, exclude_id: int) -> list[datetime]:
    """Times of the other taps already folded into this attendance row
    (locking read: must see what a concurrent apply just committed)."""
    rows = (await db.execute(select(BiometricPunch.punch_time).where(
        BiometricPunch.attendance_id == attendance_id,
        BiometricPunch.id != exclude_id,
        BiometricPunch.state.in_([_S.APPLIED, _S.DUPLICATE]),
    ).with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    return [as_utc(t) for t in rows]


async def _merge(db, bp, user, row: Attendance, t: datetime,
                 dedupe_seconds: int, quiet: bool) -> str:
    """Fold tap `t` into an existing, locked, not-HR-edited row. Returns the
    resulting state (APPLIED when in/out changed, else DUPLICATE)."""
    cur_in = as_utc(row.captured_at)
    cur_out = as_utc(row.punch_out_time) if row.punch_out_time else None
    pts = [cur_in, t] + await _day_tap_times(db, row.id, bp.id)
    if cur_out is not None:
        pts.append(cur_out)
    new_in, top = min(pts), max(pts)
    changed = False

    in_moved = new_in < cur_in
    if in_moved:
        wd, sid, cross, flag = await punch._attribute_punch(db, user.id, new_in)
        if wd != row.work_date:
            # Unreachable (the row was selected by this tap's work_date). Never
            # move the in-time without re-attributing it.
            log.error("biometric tap %s attributes to %s, row %s is %s: "
                      "in-time not moved", bp.id, wd, row.id, row.work_date)
            in_moved = False
            new_in = cur_in
        else:
            row.captured_at = new_in
            row.shift_template_id = sid
            row.is_cross_midnight = cross
            row.attribution_flag = flag
            db.add(AuditLog(
                user_id=user.id, action="BIOMETRIC_PUNCH_IN_MOVED",
                resource_type="attendance", resource_id=str(row.id),
                details={"previous": cur_in.isoformat(),
                         "new": new_in.isoformat(), "biometric_punch_id": bp.id}))
            changed = True

    out_changed = False
    if (top - new_in).total_seconds() >= dedupe_seconds and (
            cur_out is None or top > cur_out):
        if cur_out is None:
            await punch.finalize_punch_out(db, user, row, top, quiet=quiet)
        else:
            await punch.extend_punch_out(db, user, row, top)
        out_changed = changed = True
    if in_moved and not out_changed and row.punch_out_time is not None:
        # The in-time moved on a closed row: keep the out-window flag
        # consistent and re-run the (idempotent) comp-off helper so the
        # result does not depend on arrival order.
        out_at = as_utc(row.punch_out_time)
        await punch.apply_out_window_flag(db, user, row, out_at)
        await punch._comp_off_after_punch_out(db, user, row, out_at, None)
    return _S.APPLIED if changed else _S.DUPLICATE


async def _apply_locked(db, bp, user, work_date, t, dedupe_seconds, quiet,
                        device_serial: Optional[str]) -> None:
    row = await punch._fresh_one(db, select(Attendance).where(
        Attendance.user_id == user.id, Attendance.work_date == work_date
    ).order_by(Attendance.captured_at).limit(1), True)
    if row is None:
        row, created = await punch.record_punch_in(
            db, user, mode="biometric", captured_at=t, fresh=True,
            remarks=f"device {device_serial}" if device_serial else "import",
            geo_bypass=True, quiet=quiet)
        if created:
            _finish(bp, _S.APPLIED, row.id)
            return
        # a concurrent tap created it first: merge into it
    if row.edited_by_id is not None:
        _finish(bp, _S.EDITED, row.id)
        return
    state = await _merge(db, bp, user, row, t, dedupe_seconds, quiet)
    _finish(bp, state, row.id)


async def apply_punch(db, bp: BiometricPunch, *, dedupe_seconds: int = DEFAULT_DEDUPE_SECONDS,
                      quiet: bool = False) -> None:
    """Fold one raw tap into Attendance and set bp.state / attendance_id /
    applied_at / error. quiet=True suppresses employee/HR notifications
    (back-fill); live taps pass quiet=False and behave like app punches."""
    device = None
    if bp.device_id is not None:
        device = await db.get(BiometricDevice, bp.device_id)
        if device is None or device.status != BiometricDeviceStatus.ACTIVE:
            bp.state, bp.error = _S.PENDING_DEVICE, None
            return
    uid = bp.user_id or await resolve_user_id(db, bp.device_id, bp.pin)
    if uid is None:
        bp.user_id, bp.state, bp.error = None, _S.UNMAPPED, None
        return
    bp.user_id = uid

    # Serialise per user: attendance has no unique (user, work_date), so two
    # concurrent first taps must not both create a row. The lock also makes
    # the later reads see what the other session committed.
    user = await punch._fresh_one(db, select(User).where(User.id == uid), True)
    if user is None or not user.is_active:
        _finish(bp, _S.IGNORED, error="inactive user")
        return

    t = as_utc(bp.punch_time)
    work_date = (await punch._attribute_punch(db, user.id, t))[0]
    try:
        await assert_attendance_editable(db, work_date, fresh=True)
    except HTTPException as exc:
        if isinstance(exc, LockRetry) or exc.status_code != 409:
            raise  # transient (retried by the caller) / not a payroll lock
        _finish(bp, _S.LOCKED, error=str(exc.detail))
        return

    serial = device.serial if device is not None else None
    # Savepoint: a failure half-way leaves neither a stray row nor flags. A
    # lock conflict (MariaDB 1020 / deadlock) surfaces as HTTPException 409;
    # see apply_punch_committed for the retry on a fresh transaction.
    async with db.begin_nested():
        await _apply_locked(db, bp, user, work_date, t,
                            dedupe_seconds, quiet, serial)


def _is_conflict(exc: Exception) -> bool:
    """Transient lock conflict worth a retry on a fresh transaction."""
    if isinstance(exc, HTTPException):
        return isinstance(exc, LockRetry)
    if not isinstance(exc, OperationalError):
        return False
    # 1305: the server already aborted the transaction (1020/1213), so the
    # savepoint rollback that follows it fails; same transient cause.
    orig = getattr(exc, "orig", None)
    return is_lock_conflict(exc) or bool(
        orig is not None and orig.args and orig.args[0] == 1305)


async def _apply_tap_tx(
    session_factory, bp_id: int, *, dedupe_seconds: int, quiet: bool,
    attempts: int, reresolve: bool = False,
    only_states: Optional[set] = None,
) -> str:
    """Apply one stored tap in its own transaction and commit; returns the
    final state. Retries lock conflicts on a brand-new session/snapshot and
    re-raises the conflict when retries run out (state left unchanged)."""
    last: Optional[Exception] = None
    for attempt in range(attempts):
        async with session_factory() as db:
            try:
                bp = await db.get(BiometricPunch, bp_id)
                if bp is None:
                    raise ValueError(f"biometric_punch {bp_id} not found")
                if only_states is not None and bp.state not in only_states:
                    return bp.state  # handled meanwhile by someone else
                if reresolve:
                    bp.user_id = await resolve_user_id(db, bp.device_id, bp.pin)
                await apply_punch(
                    db, bp, dedupe_seconds=dedupe_seconds, quiet=quiet)
                state = bp.state
                await db.commit()
                return state
            except (HTTPException, OperationalError) as exc:
                if not _is_conflict(exc):
                    raise
                log.warning("biometric tap %s: lock conflict, attempt %s/%s: "
                            "%r", bp_id, attempt + 1, attempts, exc)
                last = exc
                await db.rollback()
        await asyncio.sleep(0.05 * (attempt + 1))
    assert last is not None
    raise last


async def apply_punch_committed(
    session_factory, bp_id: int, *,
    dedupe_seconds: int = DEFAULT_DEDUPE_SECONDS, quiet: bool = False,
    attempts: int = 4,
) -> str:
    """Apply one stored tap (live device tap) in its OWN transaction and
    commit; returns the final state. Two concurrent first taps for the same
    employee/day serialise on the user-row lock; the loser either merges or,
    when MariaDB rejects its stale REPEATABLE READ snapshot (1020/deadlock),
    is retried on a fresh session."""
    return await _apply_tap_tx(
        session_factory, bp_id, dedupe_seconds=dedupe_seconds, quiet=quiet,
        attempts=attempts)


DEFAULT_PENDING_STATES = frozenset(
    {_S.UNMAPPED, _S.PENDING_DEVICE, PENDING_APPLY})


async def apply_pending(
    session_factory, *, user_id: Optional[int] = None,
    device_id: Optional[int] = None, pin: Optional[str] = None,
    limit: int = 2000, dedupe_seconds: int = DEFAULT_DEDUPE_SECONDS,
    states=DEFAULT_PENDING_STATES, attempts: int = 4,
) -> dict[str, int]:
    """Back-fill (device approved / mapping added / reprocess). Takes a
    SESSION FACTORY (e.g. SessionLocal) and commits itself: every tap is
    re-resolved and applied, quiet, in its own short transaction in
    punch_time order, so no locks are held across taps (no cross-user
    deadlocks) and a dead transaction can't poison the rest.

    `states` selects which rows to process (Task 5 reprocess passes
    {error, locked}). Returns counts per resulting state. A tap whose lock
    conflicts outlast the retries keeps its state and is counted under
    "conflict"; a non-lock exception stamps that tap ERROR and the batch
    continues. Never stamps ERROR for a transient conflict."""
    states = set(states)
    async with session_factory() as db:
        stmt = select(BiometricPunch.id).where(
            BiometricPunch.state.in_(states))
        if device_id is not None:
            stmt = stmt.where(BiometricPunch.device_id == device_id)
        if pin is not None:
            stmt = stmt.where(BiometricPunch.pin == pin)
        if user_id is not None:
            maps = (await db.execute(select(BiometricUserMap).where(
                BiometricUserMap.user_id == user_id))).scalars().all()
            conds = [BiometricPunch.user_id == user_id]
            for m in maps:
                c = BiometricPunch.pin == m.pin
                if m.device_id is not None:
                    c = and_(c, BiometricPunch.device_id == m.device_id)
                conds.append(c)
            stmt = stmt.where(or_(*conds))
        stmt = stmt.order_by(
            BiometricPunch.punch_time, BiometricPunch.id).limit(limit)
        ids = list((await db.execute(stmt)).scalars().all())

    counts: dict[str, int] = {}
    for bp_id in ids:
        try:
            state = await _apply_tap_tx(
                session_factory, bp_id, dedupe_seconds=dedupe_seconds,
                quiet=True, attempts=attempts, reresolve=True,
                only_states=states)
        except Exception as exc:
            if _is_conflict(exc):
                state = "conflict"
            else:
                state = _S.ERROR
                try:
                    async with session_factory() as db:
                        bp = await db.get(BiometricPunch, bp_id)
                        if bp is not None:
                            bp.state = _S.ERROR
                            bp.attendance_id = None
                            bp.error = (
                                f"{type(exc).__name__}: "
                                f"{getattr(exc, 'detail', None) or exc}"
                            )[:255]
                            await db.commit()
                except Exception as stamp_exc:  # never abort the batch
                    log.warning("biometric tap %s: could not stamp ERROR "
                                "(%r) after %r", bp_id, stamp_exc, exc)
                    state = ("conflict" if _is_conflict(stamp_exc)
                             else "unstamped")
        counts[state] = counts.get(state, 0) + 1
    return counts
