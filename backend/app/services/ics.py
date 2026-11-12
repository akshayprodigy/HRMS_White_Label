"""Pure RFC 5545 iCalendar rendering for the personal roster feed.

Event times are NAIVE wall-clock datetimes emitted as floating local times
(no Z, no TZID) so calendar apps show the shift's wall-clock time.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IcsEvent:
    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str = ""


def escape_text(s: str) -> str:
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def fold_line(line: str, limit: int = 75) -> str:
    """Fold to <= `limit` octets per physical line (continuations start with
    one space, which counts toward their limit); never splits a UTF-8 char."""
    if len(line.encode("utf-8")) <= limit:
        return line
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


def _local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def render_ics(events, *, cal_name: str, now: datetime) -> str:
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HRMS//Roster//EN",
        "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{escape_text(cal_name)}",
    ]
    for e in events:
        lines += [
            "BEGIN:VEVENT", f"UID:{e.uid}", f"DTSTAMP:{stamp}",
            f"DTSTART:{_local(e.start)}", f"DTEND:{_local(e.end)}",
            f"SUMMARY:{escape_text(e.summary)}",
            f"DESCRIPTION:{escape_text(e.description)}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(fold_line(l) + "\r\n" for l in lines)
