"""Only the DOP service may write User.manager_id."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
OK = {"services/dop/assignments.py"}


def _writes(tree):
    for n in ast.walk(tree):
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "manager_id":
                    yield n.lineno
        if not isinstance(n, ast.Call):
            continue
        kws = {k.arg for k in n.keywords}
        f = n.func
        if isinstance(f, ast.Name) and f.id == "User" and "manager_id" in kws:
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
