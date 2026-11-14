"""Pure ADMS / iClock push-protocol helpers (no DB, no FastAPI).

Fingerprint templates are never parsed or stored.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

_PIN_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_TIME_FMT = "%Y-%m-%d %H:%M:%S"

MAX_LINES = 5000  # per request; extra lines are ignored (device resends)


@dataclass(frozen=True)
class AttLog:
    pin: str
    local_time: datetime  # naive, device wall clock
    status: Optional[str]
    verify: Optional[str]
    raw: str


@dataclass(frozen=True)
class DeviceUser:
    pin: str
    name: Optional[str]


def _lines(body: str) -> list[str]:
    return body.splitlines()[:MAX_LINES]


def parse_attlog(body: str) -> tuple[list[AttLog], list[str]]:
    records: list[AttLog] = []
    errors: list[str] = []
    for n, line in enumerate(_lines(body), start=1):
        if not line.strip():
            continue
        parts = line.split("\t")
        pin = parts[0].strip()
        if not _PIN_RE.match(pin):
            errors.append(f"line {n}: invalid PIN")
            continue
        if len(parts) < 2:
            errors.append(f"line {n}: missing time")
            continue
        try:
            when = datetime.strptime(parts[1].strip(), _TIME_FMT)
        except ValueError:
            errors.append(f"line {n}: invalid time")
            continue
        status = parts[2].strip() or None if len(parts) > 2 else None
        verify = parts[3].strip() or None if len(parts) > 3 else None
        records.append(AttLog(pin=pin, local_time=when, status=status, verify=verify, raw=line))
    return records, errors


def parse_operlog_users(body: str) -> list[DeviceUser]:
    users: list[DeviceUser] = []
    for line in _lines(body):
        if not line.startswith("USER "):
            continue
        kv: dict[str, str] = {}
        for part in line[len("USER "):].split("\t"):
            if "=" in part:
                k, v = part.split("=", 1)
                kv[k.strip()] = v
        pin = kv.get("PIN", "").strip()
        if not _PIN_RE.match(pin):
            continue
        name = (kv.get("Name") or "").strip()[:120] or None
        users.append(DeviceUser(pin=pin, name=name))
    return users


def to_utc(local: datetime, utc_offset_minutes: int) -> datetime:
    return (local - timedelta(minutes=utc_offset_minutes)).replace(tzinfo=timezone.utc)


def handshake_response(sn: str, attlog_stamp: Optional[str], operlog_stamp: Optional[str],
                       utc_offset_minutes: int) -> str:
    tz = f"{utc_offset_minutes / 60:g}"
    return "\n".join([
        f"GET OPTION FROM: {sn}",
        f"ATTLOGStamp={attlog_stamp or 'None'}",
        f"OPERLOGStamp={operlog_stamp or 'None'}",
        "ATTPHOTOStamp=None",
        "ErrorDelay=30",
        "Delay=10",
        "TransTimes=00:00;14:05",
        "TransInterval=1",
        "TransFlag=TransData AttLog OpLog",
        f"TimeZone={tz}",
        "Realtime=1",
        "Encrypt=None",
    ]) + "\n"


def ok_count(n: int) -> str:
    return f"OK: {n}"
