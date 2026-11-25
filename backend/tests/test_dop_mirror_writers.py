"""Only the DOP service may write User.manager_id."""
import ast
import re
from pathlib import Path

# Only app/ is scanned. Two dev seed scripts also write manager_id directly
# (they run once, before any assignment exists):
#   scripts/seed_demo_users.py:482, scripts/seed_month_data.py:380
RAW_SQL = re.compile(r"UPDATE\s+users?\b.*manager_id", re.I | re.S)

APP = Path(__file__).resolve().parents[1] / "app"
OK = {"services/dop/assignments.py"}


def _writes(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                and RAW_SQL.search(n.value):
            yield n.lineno
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "manager_id":
                    yield n.lineno
        if not isinstance(n, ast.Call):
            continue
        kws = {k.arg for k in n.keywords}
        f = n.func
        fname = f.id if isinstance(f, ast.Name) else (
            f.attr if isinstance(f, ast.Attribute) else "")
        if fname.endswith("User") and "manager_id" in kws:
            yield n.lineno
        # .values(manager_id=...) / .update(manager_id=...) style writes
        if isinstance(f, ast.Attribute) and f.attr in ("values", "update") \
                and "manager_id" in kws:
            yield n.lineno
        # setattr(obj, "manager_id", ...)
        if isinstance(f, ast.Name) and f.id == "setattr" and len(n.args) > 1 \
                and isinstance(n.args[1], ast.Constant) \
                and n.args[1].value == "manager_id":
            yield n.lineno
        # .values({"manager_id": ...})
        if isinstance(f, ast.Attribute) and f.attr == "values":
            for a in n.args:
                if isinstance(a, ast.Dict) and any(
                        isinstance(k, ast.Constant) and k.value == "manager_id"
                        for k in a.keys):
                    yield n.lineno


def test_no_direct_manager_id_writes():
    bad = []
    for f in APP.rglob("*.py"):
        rel = f.relative_to(APP).as_posix()
        if rel in OK:
            continue
        bad += [f"{rel}:{ln}" for ln in _writes(ast.parse(f.read_text()))]
    assert bad == []
