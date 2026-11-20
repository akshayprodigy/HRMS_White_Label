"""Guard: business 'today' must be org-local (Phase 6A). Fails on UTC/system-date
idioms in backend/app (services, api, models, core, schemas) unless allow-listed
in tests/org_time_allowlist.txt.

Allow-list format, one per line:  relative/path.py:substring  # reason
(paths relative to backend/app). An EMPTY substring whitelists the WHOLE FILE.
Every entry must still match a finding; a stale entry fails this test.

Checks: (1) regex lines (date.today(), now(..).date(), utcnow().date(),
datetime.combine(..start_time/end_time), func.date/time(X.captured_at);
(2) AST: names bound to a UTC/naive now()/utcnow() value that then get
.date() / .year / .month / .weekday() / .replace(hour=...); naive
datetime.now() and any utcnow(); bare `date.today` references (callable
passed, e.g. default_factory=date.today)."""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
ALLOW = Path(__file__).resolve().parent / "org_time_allowlist.txt"
DIRS = ("services", "api", "models", "core", "schemas")

PATTERNS = [
    re.compile(r"\.today\(\)"),
    re.compile(r"\.now\([^)]*\)\.date\(\)"),
    re.compile(r"utcnow\(\)\.date\(\)"),
    re.compile(r"datetime\.combine\([^)]*(start_time|end_time)"),
    re.compile(r"func\.(date|time)\(\s*\w+\.captured_at"),
]
BAD_ATTRS = {"date", "year", "month", "weekday"}
UTC_ARGS = {"timezone.utc", "utc", "UTC", "_tz.utc", "dt_timezone.utc"}


def _allow():
    out = []
    for raw in ALLOW.read_text().splitlines():
        line = raw.split("  #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        path, _, sub = line.partition(":")
        out.append((path.strip(), sub.strip()))
    return out


def _utcish_now(node) -> bool:
    """A `.now(...)`/`.utcnow()` call that yields a UTC or naive datetime."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if isinstance(node.func.value, ast.Name) and node.func.value.id == "func":
        return False                                 # SQL func.now()
    if node.func.attr == "utcnow":
        return True
    if node.func.attr != "now":
        return False
    if not node.args and not node.keywords:
        return True                                  # naive local clock
    arg = node.args[0] if node.args else node.keywords[0].value
    return ast.unparse(arg) in UTC_ARGS


def _walk_scope(scope):
    """ast.walk limited to this scope (nested function bodies excluded)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))


def _is_now_expr(v) -> bool:
    """Value expression that evaluates to a UTC/naive now() instant."""
    if _utcish_now(v):
        return True
    if isinstance(v, ast.BoolOp):
        return any(_is_now_expr(x) for x in v.values)
    if isinstance(v, ast.IfExp):
        return _is_now_expr(v.body) or _is_now_expr(v.orelse)
    if isinstance(v, ast.BinOp):
        return _is_now_expr(v.left)
    return False


def _ast_findings(tree, lines):
    out = []

    def add(node, why):
        out.append((node.lineno, f"{why}: {lines[node.lineno - 1].strip()}"))

    # bare `date.today` (not called) and naive/utc now() / utcnow()
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == "today" \
                and id(n) not in called:
            add(n, "bare .today reference")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if isinstance(n.func.value, ast.Name) and n.func.value.id == "func":
                continue
            if n.func.attr == "utcnow":
                add(n, "utcnow()")
            elif n.func.attr == "now" and not n.args and not n.keywords:
                add(n, "naive now()")

    # per-function tracking of names bound to UTC-ish now() values
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for scope in scopes:
        tracked = set()
        for n in _walk_scope(scope):
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                val = n.value
                if val is None:
                    continue
                if _is_now_expr(val):
                    targets = (n.targets if isinstance(n, ast.Assign)
                               else [n.target])
                    for t in targets:
                        if isinstance(t, ast.Name):
                            tracked.add(t.id)
        if not tracked:
            continue
        for n in _walk_scope(scope):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                    and n.value.id in tracked and n.attr in BAD_ATTRS:
                add(n, f"'{n.value.id}' is a UTC now(); .{n.attr}")
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "replace" \
                    and isinstance(n.func.value, ast.Name) \
                    and n.func.value.id in tracked \
                    and any(k.arg == "hour" for k in n.keywords):
                add(n, f"'{n.func.value.id}' is a UTC now(); .replace(hour=)")
    return out


def _findings():
    found = []
    for sub in DIRS:
        for f in sorted((APP / sub).rglob("*.py")):
            rel = f.relative_to(APP).as_posix()
            text = f.read_text()
            lines = text.splitlines()
            hits = {}
            for n, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                if any(p.search(line) for p in PATTERNS):
                    hits[n] = line.strip()
            for n, why in _ast_findings(ast.parse(text), lines):
                hits.setdefault(n, why)
            found += [(rel, n, t) for n, t in sorted(hits.items())]
    return found


def test_no_utc_today_in_business_code():
    allow = _allow()
    used = set()
    bad = []
    for rel, n, text in _findings():
        hit = [(a, s) for a, s in allow if a == rel and s in text]
        if hit:
            used.update(hit)
        else:
            bad.append(f"{rel}:{n}: {text}")
    assert not bad, "UTC/system 'today' found (use org_time.local_today):\n" + "\n".join(bad)
    stale = [f"{a}:{s}" for a, s in allow if (a, s) not in used]
    assert not stale, "stale allow-list entries (match nothing): " + ", ".join(stale)
