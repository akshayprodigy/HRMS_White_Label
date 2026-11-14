"""CSV / XLSX punch import (Roadmap v2 Phase 4, Task 6).

Parsing and validation are pure functions (no DB); `resolve_and_summarise`
adds the DB lookups (people, known devices, already-imported keys). Naive
timestamps are wall-clock at `utc_offset_minutes`; an explicit offset in an
ISO value wins. Rows are numbered like a spreadsheet: header = 1, first data
row = 2."""
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select

from app.models.biometric import BiometricDevice, BiometricPunch
from app.models.employee import Employee
from app.models.user import User
from app.services import biometric as bio

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
MAX_COLS = 30
MAX_FUTURE = timedelta(hours=24)
MAX_AGE = timedelta(days=400)
CODE_MAX = bio.PIN_MAX
ERROR_CAP = 200
SAMPLE_N = 20
_CHUNK = 500

TEMPLATE_CODE = ("employee_code,timestamp,device_serial\n"
                 "EMP001,2026-11-03 09:02:11,\n"
                 "EMP001,2026-11-03 18:31:40,\n")
TEMPLATE_PIN = ("pin,timestamp,device_serial\n"
                "1001,2026-11-03 09:02:11,\n"
                "1001,2026-11-03 18:31:40,\n")


class ImportFileError(Exception):
    """File-level problem; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


_ALIASES = {"time_stamp": "timestamp", "datetime": "timestamp",
            "date_time": "timestamp"}


def norm_header(h: Any) -> str:
    k = re.sub(r"[\s_\-]+", "_", str(h or "").strip().lower()).strip("_")
    return _ALIASES.get(k, k)


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def read_rows(filename: str, data: bytes) -> list[tuple[int, dict]]:
    """-> [(row_number, {normalised header: raw cell})], blank rows skipped.
    Raises ImportFileError for a bad file type / encoding / size / row cap."""
    if len(data) > MAX_BYTES:
        raise ImportFileError("File is larger than 5 MB", 413)
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _read_csv(data)
    if name.endswith(".xlsx"):
        return _read_xlsx(data)
    raise ImportFileError("Only .csv and .xlsx files are supported")


def _collect(header: list, rows) -> list[tuple[int, dict]]:
    keys = [norm_header(h) for h in header]
    if not any(keys):
        raise ImportFileError("The file has no header row")
    out: list[tuple[int, dict]] = []
    for i, cells in rows:  # i = spreadsheet row number
        if all(_is_blank(c) for c in cells):
            continue
        if len(out) >= MAX_ROWS:
            raise ImportFileError(f"More than {MAX_ROWS} data rows")
        d: dict = {}
        for k, c in zip(keys, cells):
            if k and k not in d:
                d[k] = c
        out.append((i, d))
    return out


def _read_csv(data: bytes) -> list[tuple[int, dict]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("CSV file must be UTF-8") from None
    if "\x00" in text:
        raise ImportFileError("Not a valid CSV file")
    try:
        rdr = csv.reader(io.StringIO(text, newline=""))
        first = next(rdr, None)
        if first is None:
            raise ImportFileError("The file is empty")
        return _collect(first, ((n, r) for n, r in enumerate(rdr, start=2)))
    except csv.Error as exc:
        raise ImportFileError(f"Invalid CSV: {exc}") from None


def _read_xlsx(data: bytes) -> list[tuple[int, dict]]:
    if not data.startswith(b"PK\x03\x04"):
        raise ImportFileError("Not a valid .xlsx file")
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise ImportFileError("Not a valid .xlsx file") from None
    except Exception:
        raise ImportFileError("Not a valid .xlsx file") from None
    try:
        ws = wb.worksheets[0] if wb.worksheets else None
        if ws is None:
            raise ImportFileError("The workbook has no sheets")
        it = ws.iter_rows(min_col=1, max_col=MAX_COLS, values_only=True)
        first = next(it, None)
        if first is None:
            raise ImportFileError("The file is empty")
        return _collect(list(first), ((n, r) for n, r in enumerate(it, start=2)))
    finally:
        wb.close()


# ---------------- cell parsing ----------------

def norm_code(v: Any) -> str:
    """Employee code: trimmed + uppercased; an int-valued float (Excel) is
    rendered without '.0'; strings are kept verbatim (leading zeros)."""
    return _ident(v).upper()


def _ident(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


_DATE_FMTS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
_TIME_FMTS = ("%H:%M:%S", "%H:%M")


def _try(s: str, fmts) -> Optional[datetime]:
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _parse_text_ts(s: str) -> datetime:
    """ISO 8601 (offset wins) or the accepted local formats."""
    s = s.strip()
    iso = s[:-1] + "+00:00" if s[-1:] in ("Z", "z") else s
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    for df in _DATE_FMTS:
        for tf in _TIME_FMTS:
            dt = _try(s, (f"{df} {tf}",))
            if dt:
                return dt
    raise ValueError(f"unrecognised timestamp '{s[:40]}'")


def _to_time(v: Any) -> time:
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not 0 <= v < 1:
            raise ValueError(f"invalid time '{v}'")
        secs = round(v * 86400)
        return time(secs // 3600 % 24, secs % 3600 // 60, secs % 60)
    s = str(v).strip()
    dt = _try(s, _TIME_FMTS)
    if dt is None:
        raise ValueError(f"unrecognised time '{s[:20]}'")
    return dt.time()


def _to_date(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    dt = _try(s, _DATE_FMTS)
    if dt is None:
        raise ValueError(f"unrecognised date '{s[:20]}'")
    return dt.date()


def parse_timestamp(rec: dict, offset_minutes: int) -> datetime:
    """-> aware UTC datetime. Raises ValueError (message is row-error text)."""
    ts = rec.get("timestamp")
    if not _is_blank(ts):
        if isinstance(ts, datetime):
            dt = ts
        elif isinstance(ts, date):
            dt = datetime(ts.year, ts.month, ts.day)
        elif isinstance(ts, (int, float)) and not isinstance(ts, bool):
            raise ValueError("timestamp must be a date/time, not a number")
        else:
            dt = _parse_text_ts(str(ts))
    else:
        d, t = rec.get("date"), rec.get("time")
        if _is_blank(d) or _is_blank(t):
            raise ValueError("missing timestamp (or date + time)")
        dt = datetime.combine(_to_date(d), _to_time(t))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))
    return dt.astimezone(timezone.utc)


@dataclass
class Row:
    row: int
    ident: str
    when: datetime
    device_serial: Optional[str] = None
    user_id: Optional[int] = None  # filled by resolve


@dataclass
class Parsed:
    total: int = 0
    rows: list[Row] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    invalid: int = 0


def validate_rows(raw: list[tuple[int, dict]], identify_by: str,
                  offset_minutes: int, now: datetime) -> Parsed:
    """Pure validation. Raises ImportFileError when a required column is
    missing."""
    if identify_by not in ("employee_code", "pin"):
        raise ImportFileError("identify_by must be employee_code or pin")
    if not -840 <= offset_minutes <= 840:
        raise ImportFileError("utc_offset_minutes out of range")
    cols = set().union(*(set(d) for _, d in raw)) if raw else set()
    if raw:
        if identify_by not in cols:
            raise ImportFileError(f"Missing required column '{identify_by}'")
        if "timestamp" not in cols and not {"date", "time"} <= cols:
            raise ImportFileError(
                "Missing time column: need 'timestamp' or 'date' + 'time'")
    out = Parsed(total=len(raw))
    lo, hi = now - MAX_AGE, now + MAX_FUTURE

    def bad(n, msg):
        out.invalid += 1
        if len(out.errors) < ERROR_CAP:
            out.errors.append({"row": n, "message": msg})

    for n, rec in raw:
        ident = (norm_code if identify_by == "employee_code" else _ident)(
            rec.get(identify_by))
        if not ident:
            bad(n, f"missing {identify_by}")
            continue
        if len(ident) > CODE_MAX:
            bad(n, f"{identify_by} longer than {CODE_MAX} characters")
            continue
        try:
            when = parse_timestamp(rec, offset_minutes)
        except (ValueError, OverflowError) as exc:
            bad(n, str(exc))
            continue
        if when > hi:
            bad(n, "timestamp is more than 24 hours in the future")
            continue
        if when < lo:
            bad(n, "timestamp is older than 400 days")
            continue
        serial = _ident(rec.get("device_serial")) or None
        out.rows.append(Row(n, ident, when, serial))
    return out


# ---------------- DB-backed resolution ----------------

async def _resolve(db, parsed: Parsed, identify_by: str) -> set[str]:
    """Fills Row.user_id; flags unknown device serials as invalid. Returns
    the set of idents that resolve to nobody."""
    serials = sorted({r.device_serial for r in parsed.rows if r.device_serial})
    dev_by_serial: dict[str, int] = {}
    for i in range(0, len(serials), _CHUNK):
        for did, ser in (await db.execute(
                select(BiometricDevice.id, BiometricDevice.serial).where(
                    BiometricDevice.serial.in_(serials[i:i + _CHUNK])))).all():
            dev_by_serial[ser] = did
    keep: list[Row] = []
    for r in parsed.rows:
        if r.device_serial and r.device_serial not in dev_by_serial:
            parsed.invalid += 1
            if len(parsed.errors) < ERROR_CAP:
                parsed.errors.append({
                    "row": r.row,
                    "message": f"unknown device_serial '{r.device_serial[:40]}'"})
        else:
            keep.append(r)
    parsed.rows = keep
    parsed.errors.sort(key=lambda e: e["row"])

    cache: dict = {}
    if identify_by == "employee_code":
        codes = sorted({r.ident for r in parsed.rows})
        for i in range(0, len(codes), _CHUNK):
            q = (select(Employee.employee_id, Employee.user_id)
                 .join(User, User.id == Employee.user_id)
                 .where(User.is_active.is_(True),
                        func.upper(Employee.employee_id).in_(codes[i:i + _CHUNK])))
            for code, uid in (await db.execute(q)).all():
                cache.setdefault(code.strip().upper(), uid)
        for r in parsed.rows:
            r.user_id = cache.get(r.ident)
    else:
        for r in parsed.rows:
            k = (dev_by_serial.get(r.device_serial) if r.device_serial else None,
                 r.ident)
            if k not in cache:
                cache[k] = await bio.resolve_user_id(db, k[0], r.ident)
            r.user_id = cache[k]
    return {r.ident for r in parsed.rows if r.user_id is None}


def dedupe_key(r: Row) -> str:
    return bio._dedupe_key("import", r.ident[:bio.PIN_MAX], r.when)


async def _existing_keys(db, keys: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(keys), _CHUNK):
        found.update((await db.execute(select(BiometricPunch.dedupe_key).where(
            BiometricPunch.dedupe_key.in_(keys[i:i + _CHUNK])))).scalars().all())
    return found


async def analyse(db, filename: str, data: bytes, identify_by: str,
                  offset_minutes: int) -> dict:
    """Parse + validate + resolve; writes nothing. Returns the summary plus
    the working objects under "_parsed" (used by commit)."""
    raw = read_rows(filename, data)
    parsed = validate_rows(raw, identify_by, offset_minutes,
                           datetime.now(timezone.utc))
    unknown = await _resolve(db, parsed, identify_by)
    seen: set[str] = set()
    dups = 0
    for r in parsed.rows:
        k = dedupe_key(r)
        if k in seen:
            dups += 1
        seen.add(k)
    existing = await _existing_keys(db, sorted(seen))
    already = sum(1 for r in parsed.rows
                  if dedupe_key(r) in existing)
    times = [r.when for r in parsed.rows]
    return {
        "rows": parsed.total, "valid": len(parsed.rows),
        "invalid": parsed.invalid, "unknown_people": len(unknown),
        "duplicates_in_file": dups, "already_imported": already,
        "date_range": ({"from": min(times).isoformat(),
                        "to": max(times).isoformat()} if times else None),
        "errors": parsed.errors,
        "sample": [{"row": r.row, "identifier": r.ident,
                    "timestamp": r.when.isoformat(),
                    "device_serial": r.device_serial,
                    "known_person": r.user_id is not None}
                   for r in parsed.rows[:SAMPLE_N]],
        "_parsed": parsed,
    }
