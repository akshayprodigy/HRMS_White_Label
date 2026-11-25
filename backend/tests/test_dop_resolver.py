"""DOP D1: pure resolver. No DB."""
from datetime import date

import pytest

from app.services.dop import resolver as R

D = date(2030, 6, 10)
P = R.Person


def world(**kw):
    base = dict(
        people={i: P(i, True, "Eng", "Mumbai") for i in range(1, 10)},
        kinds={"reporting", "functional"}, assignments=[], posts={},
        holders=[], covers=[], heads={}, role_users={}, hr_ids=[9])
    base.update(kw)
    return R.World(**base)


def asg(id, mgr, scope="user", kind="reporting", user=1, dept=None, loc=None,
        post=None, start=date(2020, 1, 1), end=None, subs=()):
    return R.Assignment(id, kind, scope, user if scope == "user" else None,
                        dept, loc, mgr, post, start, end, frozenset(subs))


def cover(id, acting, user=None, post=None, subs=(), original=False,
          start=D, end=D):
    return R.Cover(id, user, post, acting, frozenset(subs), start, end, original)


REPORTING = R.Approver("manager_kind", "reporting")


def go(w, approver=REPORTING, fallback=None, sub="leave", on=D, requester=1):
    return R.resolve(w, approver, fallback, requester, sub, on)


def test_most_specific_scope_wins():
    a = [asg(1, 2, "company"), asg(2, 3, "location", loc="Mumbai"),
         asg(3, 4, "department", dept="Eng"), asg(4, 5)]
    for expected in (5, 4, 3, 2):
        assert go(world(assignments=a)).user_ids == [expected]
        a = a[:-1]


def test_named_subdomain_beats_all_at_same_scope():
    w = world(assignments=[asg(1, 2), asg(2, 3, subs={"expense"})])
    assert go(w, sub="expense").user_ids == [3]
    assert go(w, sub="leave").user_ids == [2]


def test_user_scope_all_beats_department_named():
    w = world(assignments=[asg(1, 2), asg(2, 3, "department", dept="Eng",
                                           subs={"leave"})])
    assert go(w).user_ids == [2]


def test_unrelated_subdomain_falls_through_to_wider_scope():
    w = world(assignments=[asg(1, 2, subs={"expense"}),
                           asg(2, 3, "company")])
    assert go(w, sub="leave").user_ids == [3]


def test_dates_are_inclusive():
    w = world(assignments=[asg(1, 2, start=D, end=D)])
    assert go(w).user_ids == [2]
    assert go(w, on=date(2030, 6, 11)).user_ids == [9]      # HR


def test_scope_text_ignores_case_and_spaces():
    w = world(assignments=[asg(1, 2, "location", loc="  mumBAI ")])
    assert go(w).user_ids == [2]


def test_post_manager_and_vacancy():
    posts = {7: R.Post(7, "HR Mgr", True, None)}
    w = world(assignments=[asg(1, None, post=7)], posts=posts,
              holders=[R.Holder(7, 4, date(2020, 1, 1), None)])
    assert go(w).user_ids == [4]
    vacant = world(assignments=[asg(1, None, post=7)], posts=posts)
    r = go(vacant)
    assert r.user_ids == [9] and r.via == "hr"


def test_acting_replaces_or_joins_original():
    base = dict(assignments=[asg(1, 2)])
    assert go(world(**base, covers=[cover(1, 3, user=2)])).user_ids == [3]
    r = go(world(**base, covers=[cover(1, 3, user=2, original=True)]))
    assert sorted(r.user_ids) == [2, 3]
    assert r.acting_for == {3: 2}


def test_acting_subdomain_and_no_chaining():
    w = world(assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2, subs={"expense"})])
    assert go(w, sub="leave").user_ids == [2]
    w = world(assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2), cover(2, 4, user=3)])
    assert go(w).user_ids == [3]


def test_post_cover_works_when_vacant():
    w = world(posts={7: R.Post(7, "HR Mgr", True, None)},
              covers=[cover(1, 5, post=7)])
    assert go(w, R.Approver("post", "7")).user_ids == [5]


def test_inactive_and_requester_are_dropped():
    people = {i: P(i, i != 2, "Eng", "Mumbai") for i in range(1, 10)}
    assert go(world(people=people, assignments=[asg(1, 2)])).via == "hr"
    assert go(world(assignments=[asg(1, 1)])).via == "hr"


def test_inactive_acting_keeps_original():
    people = {i: P(i, i != 3, "Eng", "Mumbai") for i in range(1, 10)}
    w = world(people=people, assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2)])
    assert go(w).user_ids == [2]


def test_fallback_then_hr_then_blocked():
    w = world(assignments=[asg(1, 4, kind="functional")])
    r = go(w, fallback=R.Approver("manager_kind", "functional"))
    assert (r.user_ids, r.via) == ([4], "fallback")
    assert go(world()).via == "hr"
    r = go(world(hr_ids=[1]))            # only HR is the requester
    assert r.via == "blocked" and r.user_ids == []


def test_department_head_post_then_head_then_deputy():
    w = world(heads={"eng": (3, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [3]
    people = {i: P(i, i != 3, "Eng", "Mumbai") for i in range(1, 10)}
    w = world(people=people, heads={"eng": (3, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [4]
    w = world(heads={"eng": (3, 4)}, posts={7: R.Post(7, "Head", True, "eng")},
              holders=[R.Holder(7, 5, D, None)])
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [5]


def test_person_and_role():
    assert go(world(), R.Approver("specific_user", "6")).user_ids == [6]
    w = world(role_users={"Finance": [5, 6, 1]})
    assert go(w, R.Approver("role", "Finance")).user_ids == [5, 6]


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        go(world(), R.Approver("nope"))


def test_explanation_is_readable():
    r = go(world(assignments=[asg(1, 2)], covers=[cover(1, 3, user=2)]))
    assert any("acting" in line for line in r.explanation)
