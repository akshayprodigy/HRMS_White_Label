"""ADMS / iClock device endpoints (Roadmap v2 Phase 4, Task 4).

Mounted at the app root (/iclock), no auth: devices identify by serial only
(unknown serials stay PENDING until HR approves). Plain-text responses.
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.api import deps
from app.api.v1.endpoints.roster_common import retry_on_lock
from app.db.session import SessionLocal
from app.models.biometric import BiometricDevice, BiometricDeviceStatus
from app.services import adms_protocol as adms
from app.services import biometric as bio

log = logging.getLogger(__name__)
router = APIRouter()

MAX_BODY = 1024 * 1024
_SN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _text(body: str, status: int = 200) -> PlainTextResponse:
    return PlainTextResponse(body, status_code=status)


async def _read_body(request: Request) -> Optional[str]:
    """Body as text, or None when it exceeds MAX_BODY (checked before decode)."""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return None
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > MAX_BODY:
            return None
    # Firmware may send GBK / latin-1 names: replace rather than fail.
    return bytes(buf).decode("utf-8", errors="replace")


async def _gate(request: Request, db):
    """Common per-request checks. Returns (device, None) or (None, response)."""
    sn = request.query_params.get("SN", "")
    if not _SN_RE.match(sn):
        return None, _text("ERROR", 400)
    ip = bio.client_ip(request.client.host if request.client else None,
                       request.headers.get("x-forwarded-for"))
    try:
        dev = await bio.get_or_register_device(db, sn, ip)
    except bio.IpNotAllowed:
        log.warning("iclock: SN %s from %s rejected by ip allow-list", sn, ip)
        return None, _text("ERROR", 403)
    if dev is None:  # too many pending devices: ignore, device retries later
        return None, _text("OK")
    return dev, None


@router.get("/cdata")
async def cdata_get(request: Request, db: deps.DBDep):
    dev, resp = await _gate(request, db)
    if resp is not None:
        return resp
    if dev.status == BiometricDeviceStatus.DISABLED:
        return _text("OK")
    return _text(adms.handshake_response(
        dev.serial, dev.attlog_stamp, dev.operlog_stamp, dev.utc_offset_minutes))


@router.post("/cdata")
async def cdata_post(request: Request, db: deps.DBDep):
    dev, resp = await _gate(request, db)
    if resp is not None:
        return resp
    if dev.status == BiometricDeviceStatus.DISABLED:
        return _text("OK")
    body = await _read_body(request)
    if body is None:
        return _text("ERROR", 413)
    table = (request.query_params.get("table") or "").upper()
    stamp = (request.query_params.get("Stamp") or "")[:32] or None
    dev_id, offset = dev.id, dev.utc_offset_minutes

    if table == "ATTLOG":
        # A fully malformed body parses to 0 records: the reply is `OK: 0`
        # (so the device doesn't resend forever) and the Stamp is still kept.
        records, _errors = adms.parse_attlog(body)
        taps = [(r.pin, adms.to_utc(r.local_time, offset), r.status, r.verify,
                 r.raw) for r in records]
        new_ids: list[int] = []
        if dev.status == BiometricDeviceStatus.PENDING:
            from sqlalchemy import func, select
            from app.models.biometric import BiometricPunch, BiometricPunchState
            held = (await db.execute(
                select(func.count()).select_from(BiometricPunch).where(
                    BiometricPunch.device_id == dev_id,
                    BiometricPunch.state == BiometricPunchState.PENDING_DEVICE)
            )).scalar() or 0
            if held >= bio.MAX_PENDING_TAPS_PER_DEVICE:
                log.warning("iclock: pending device %s holds %s taps; "
                            "dropping a batch of %s", dev.serial, held,
                            len(taps))
                return _text(adms.ok_count(len(records)))

        async def _store():
            # Exclusive lock: serialises with approve (which locks the row
            # FOR UPDATE), so a tap is never stored PENDING_DEVICE after the
            # approve back-fill already ran. FOR UPDATE (not FOR SHARE) avoids
            # an S->X upgrade deadlock when the stamp is updated below.
            from sqlalchemy import select as _select
            d = (await db.execute(
                _select(BiometricDevice).where(BiometricDevice.id == dev_id)
                .with_for_update()
                .execution_options(populate_existing=True))).scalars().first()
            if d is None or d.status == BiometricDeviceStatus.DISABLED:
                new_ids[:] = []
                return
            _n, rows = await bio.store_taps(
                db, source="device", device=d, taps=taps)
            new_ids[:] = [r.id for r in rows
                          if r.state == bio.PENDING_APPLY]
            if stamp:
                d.attlog_stamp = stamp

        await retry_on_lock(db, _store, commit=True)
        # Live taps apply one by one in their own transactions; a failure
        # leaves the tap "received" for the next apply_pending sweep.
        for bp_id in new_ids:
            try:
                await bio.apply_punch_committed(SessionLocal, bp_id)
            except Exception:
                log.warning("iclock: apply of tap %s failed; left for sweep",
                            bp_id, exc_info=True)
        return _text(adms.ok_count(len(records)))

    if table == "OPERLOG":
        users = adms.parse_operlog_users(body)
        lines = len(body.splitlines()[:adms.MAX_LINES])

        async def _users():
            await bio.upsert_device_users(db, dev_id, users)
            if stamp:
                d = await db.get(BiometricDevice, dev_id)
                d.operlog_stamp = stamp

        await retry_on_lock(db, _users, commit=True)
        return _text(adms.ok_count(lines))

    return _text(adms.ok_count(0))


@router.get("/getrequest")
async def getrequest(request: Request, db: deps.DBDep):
    dev, resp = await _gate(request, db)
    if resp is not None:
        return resp
    return _text("OK")


@router.post("/devicecmd")
async def devicecmd(request: Request, db: deps.DBDep):
    dev, resp = await _gate(request, db)
    if resp is not None:
        return resp
    return _text("OK")
