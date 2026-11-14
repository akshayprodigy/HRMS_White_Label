"""CSV / XLSX punch import (Roadmap v2 Phase 4, Task 6).

Parsing and validation are pure functions (no DB); `resolve_and_summarise`
adds the DB lookups (people, known devices, already-imported keys). Naive
timestamps are wall-clock at `utc_offset_minutes`; an explicit offset in an
ISO value wins. Rows are numbered like a spreadsheet: header = 1, first data
row = 2."""
import csv
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.models.biometric import BiometricDevice, BiometricPunch
from app.services import biometric as bio

log = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
MAX_SCAN = MAX_ROWS * 5          # rows scanned, blank ones included
MAX_UNCOMPRESSED = 100 * 1024 * 1024
MAX_COLS = 30
MAX_FUTURE = timedelta(hours=24)
MAX_AGE = timedelta(days=400)
CODE_MAX = bio.PIN_MAX
ERROR_CAP = 200
SAMPLE_N = 20
_CHUNK = 500

_NOTE = ("# Lines starting with # are ignored. timestamp: YYYY-MM-DD HH:MM[:SS] "
         "or DD/MM/YYYY HH:MM[:SS] (day first); an ISO value may carry an "
         "offset (+05:30 / Z).\n")
TEMPLATE_CODE = ("employee_code,timestamp,device_serial\n" + _NOTE +
                 "EMP001,2026-11-03 09:02:11,\n"
                 "EMP001,2026-11-03 18:31:40,\n")
TEMPLATE_PIN = ("pin,timestamp,device_serial\n" + _NOTE +
                "1001,2026-11-03 09:02:11,\n"
                "1001,2026-11-03 18:31:40,\n")


def source_for(identify_by: str) -> str:
    return bio.IMPORT_CODE if identify_by == "employee_code" else bio.IMPORT_PIN


def source_key_for(identify_by: str, serial: Optional[str]) -> str:
    """Dedupe namespace: code rows never collide with pin rows, and the same
    pin from two devices is two taps."""
    if identify_by == "employee_code":
        return bio.IMPORT_CODE
    return f"{bio.IMPORT_PIN}:{serial}" if serial else bio.IMPORT_PIN


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
        if i > MAX_SCAN + 1:
            raise ImportFileError("Too many rows (blank rows count too)")
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


def _skip_comments(rdr):
    """(row_number, cells), dropping pure comment lines (exactly one non-empty
    cell, starting with '#') in the block directly after the header. Any
    other row, '#12,2026-...' included, is data."""
    lead = True
    for n, r in enumerate(rdr, start=2):
        if lead:
            filled = [c for c in r if not _is_blank(c)]
            if len(filled) == 1 and str(filled[0]).lstrip().startswith("#"):
                continue
            if filled:
                lead = False
        yield n, r


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
        return _collect(first, _skip_comments(rdr))
    except csv.Error as exc:
        raise ImportFileError(f"Invalid CSV: {exc}") from None


def _read_xlsx(data: bytes) -> list[tuple[int, dict]]:
    if not data.startswith(b"PK\x03\x04"):
        raise ImportFileError("Not a valid .xlsx file")
    from openpyxl import load_workbook
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # central-directory sizes can be understated; MAX_SCAN and the
            # threadpool bound the damage
            if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
                raise ImportFileError("Workbook is too large when unpacked")
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except ImportFileError:
        raise
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
        dt = datetime.fromisoformat(iso)
    except ValueError:
        dt = None
    if dt is not None:
        if len(iso) <= 10:
            raise ValueError("timestamp has no time part")
        return dt
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
            raise ValueError("timestamp has no time part")
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


_DMY = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-]\d{4}")


def ambiguous_dmy(rec: dict) -> bool:
    """dd/mm/yyyy text where day and month are both <= 12 and differ."""
    v = rec.get("timestamp")
    if _is_blank(v):
        v = rec.get("date")
    if not isinstance(v, str):
        return False
    m = _DMY.match(v)
    return bool(m and int(m[1]) <= 12 and int(m[2]) <= 12
                and m[1].lstrip("0") != m[2].lstrip("0"))


@dataclass
class Row:
    row: int
    ident: str
    when: datetime
    device_serial: Optional[str] = None
    user_id: Optional[int] = None  # filled by resolve
    ambiguous: bool = False


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
        out.rows.append(Row(n, ident, when, serial, None, ambiguous_dmy(rec)))
    return out


# ---------------- DB-backed resolution ----------------

def _row_error(parsed: Parsed, row: Row, msg: str) -> None:
    parsed.invalid += 1
    if len(parsed.errors) < ERROR_CAP:
        parsed.errors.append({"row": row.row, "message": msg})


async def _resolve(db, parsed: Parsed, identify_by: str) -> set[str]:
    """Fills Row.user_id; flags unknown device serials and ambiguous codes as
    invalid. Returns the set of idents that resolve to nobody. Uses the same
    resolvers as store_taps / back-fill (codes: Employee only; pins: map)."""
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
            _row_error(parsed, r,
                       f"unknown device_serial '{r.device_serial[:40]}'")
        else:
            keep.append(r)
    parsed.rows = keep

    if identify_by == "employee_code":
        ok, amb = await bio.resolve_codes(db, {r.ident for r in parsed.rows})
        keep = []
        for r in parsed.rows:
            if r.ident in amb:
                _row_error(parsed, r, f"employee_code '{r.ident}' matches "
                                      "more than one employee")
                continue
            r.user_id = ok.get(r.ident)
            keep.append(r)
        parsed.rows = keep
    else:
        by_dev: dict = {}
        for r in parsed.rows:
            by_dev.setdefault(
                dev_by_serial.get(r.device_serial) if r.device_serial else None,
                set()).add(r.ident)
        maps = {did: await bio.resolve_pins(db, did, pins)
                for did, pins in by_dev.items()}
        for r in parsed.rows:
            did = dev_by_serial.get(r.device_serial) if r.device_serial else None
            r.user_id = maps[did].get(r.ident)
    parsed.errors.sort(key=lambda e: e["row"])
    return {r.ident for r in parsed.rows if r.user_id is None}


def dedupe_key(r: Row, identify_by: str) -> str:
    return bio._dedupe_key(source_key_for(identify_by, r.device_serial),
                           r.ident[:bio.PIN_MAX], r.when)


async def _existing_keys(db, keys: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(keys), _CHUNK):
        found.update((await db.execute(select(BiometricPunch.dedupe_key).where(
            BiometricPunch.dedupe_key.in_(keys[i:i + _CHUNK])))).scalars().all())
    return found


async def analyse(db, filename: str, data: bytes, identify_by: str,
                  offset_minutes: int) -> dict:
    """Parse + validate + resolve; writes nothing. Returns the summary plus
    the working objects under "_parsed" (used by commit). Parsing is CPU
    bound, so it runs in the threadpool."""
    raw = await run_in_threadpool(read_rows, filename, data)
    parsed = await run_in_threadpool(
        validate_rows, raw, identify_by, offset_minutes,
        datetime.now(timezone.utc))
    unknown = await _resolve(db, parsed, identify_by)
    seen: set[str] = set()
    dups = 0
    keys = []
    for r in parsed.rows:
        k = dedupe_key(r, identify_by)
        keys.append(k)
        if k in seen:
            dups += 1
        seen.add(k)
    existing = await _existing_keys(db, sorted(seen))
    already = sum(1 for k in keys if k in existing)
    times = [r.when for r in parsed.rows]
    amb_rows = [r.row for r in parsed.rows if r.ambiguous]
    return {
        "rows": parsed.total, "valid": len(parsed.rows),
        "invalid": parsed.invalid, "unknown_people": len(unknown),
        "duplicates_in_file": dups, "already_imported": already,
        "date_range": ({"from": min(times).isoformat(),
                        "to": max(times).isoformat()} if times else None),
        "errors": parsed.errors,
        "warnings": ([{
            "code": "ambiguous_day_month", "count": len(amb_rows),
            "rows": amb_rows[:10],
            "message": "Ambiguous day/month (both parts <= 12); read as "
                       "DD/MM"}] if amb_rows else []),
        "sample": [{"row": r.row, "identifier": r.ident,
                    "timestamp": r.when.isoformat(),
                    "device_serial": r.device_serial,
                    "known_person": r.user_id is not None}
                   for r in parsed.rows[:SAMPLE_N]],
        "_parsed": parsed,
    }
