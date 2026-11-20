"""Guard: business 'today' must be org-local (Phase 6A). Fails on UTC/system-date
idioms in backend/app/services and backend/app/api unless allow-listed in
tests/org_time_allowlist.txt (`relative/path.py:substring  # reason`)."""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
ALLOW = Path(__file__).resolve().parent / "org_time_allowlist.txt"

PATTERNS = [
    re.compile(r"\.today\(\)"),
    re.compile(r"\.now\([^)]*\)\.date\(\)"),
    re.compile(r"utcnow\(\)\.date\(\)"),
    re.compile(r"datetime\.combine\([^)]*(start_time|end_time)"),
    re.compile(r"func\.(date|time)\(\s*\w+\.captured_at"),
]


def _allow():
    out = []
    for raw in ALLOW.read_text().splitlines():
        line = raw.split("  #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        path, _, sub = line.partition(":")
        out.append((path.strip(), sub.strip()))
    return out


def test_no_utc_today_in_business_code():
    allow = _allow()
    bad = []
    for sub in ("services", "api"):
        for f in sorted((APP / sub).rglob("*.py")):
            rel = f.relative_to(APP).as_posix()
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if not any(p.search(line) for p in PATTERNS):
                    continue
                if any(rel == a and s in line for a, s in allow):
                    continue
                bad.append(f"{rel}:{n}: {line.strip()}")
    assert not bad, "UTC/system 'today' found (use org_time.local_today):\n" + "\n".join(bad)
