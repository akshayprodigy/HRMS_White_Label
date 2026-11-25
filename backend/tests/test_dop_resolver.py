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
    assert r.acting_for == {3: [2]}


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


# ---- review fixes ----

def test_dept_head_is_requester_falls_to_deputy():
    w = world(heads={"eng": (1, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).user_ids == [4]


def test_dept_head_post_unusable_falls_to_head():
    heads = {"eng": (3, 4)}
    posts = {7: R.Post(7, "Head", True, "eng")}
    people = {i: P(i, i != 5, "Eng", "Mumbai") for i in range(1, 10)}
    inactive = world(people=people, heads=heads, posts=posts,
                     holders=[R.Holder(7, 5, D, None)])
    assert go(inactive, R.Approver("dept_head_of_requester")).user_ids == [3]
    mine = world(heads=heads, posts=posts, holders=[R.Holder(7, 1, D, None)])
    assert go(mine, R.Approver("dept_head_of_requester")).user_ids == [3]


@pytest.mark.parametrize("ap", [
    R.Approver("post", "abc"), R.Approver("post", None),
    R.Approver("specific_user", "abc"), R.Approver("specific_user", None)])
def test_malformed_reference_yields_nobody(ap):
    r = go(world(), ap)
    assert r.via == "hr" and r.user_ids == [9]
    assert any("invalid reference" in x for x in r.explanation)
    f = go(world(assignments=[asg(1, 4, kind="functional")]), ap,
           fallback=R.Approver("manager_kind", "functional"))
    assert (f.user_ids, f.via) == ([4], "fallback")


def test_blank_department_never_matches_blank_head():
    people = {i: P(i, True, None, "Mumbai") for i in range(1, 10)}
    w = world(people=people, heads={"": (3, 4)})
    assert go(w, R.Approver("dept_head_of_requester")).via == "hr"


def test_cover_does_not_apply_to_acting_persons_own_request():
    w = world(assignments=[asg(3, 2, user=3)], covers=[cover(1, 3, user=2)])
    assert go(w, requester=3).user_ids == [2]
    # original unusable too: fallback / HR
    people = {i: P(i, i != 2, "Eng", "Mumbai") for i in range(1, 10)}
    w = world(people=people, assignments=[asg(3, 2, user=3)],
              covers=[cover(1, 3, user=2)])
    assert go(w, requester=3).via == "hr"
    # a lower-ranked usable cover may still apply
    w = world(assignments=[asg(3, 2, user=3)],
              covers=[cover(1, 3, user=2, subs={"leave"}),
                      cover(2, 5, user=2)])
    assert go(w, requester=3).user_ids == [5]


def test_cover_on_inactive_post_does_not_act():
    w = world(posts={7: R.Post(7, "HR Mgr", False, None)},
              covers=[cover(1, 5, post=7)])
    assert go(w, R.Approver("post", "7")).via == "hr"


def test_acting_for_lists_every_covered_user_sorted():
    w = world(role_users={"Fin": [6, 5]},
              covers=[cover(1, 3, user=6), cover(2, 3, user=5)])
    r = go(w, R.Approver("role", "Fin"))
    assert r.user_ids == [3] and r.acting_for == {3: [5, 6]}


def test_seat_holder_in_own_right_is_not_acting():
    w = world(role_users={"Fin": [5, 6]},
              covers=[cover(1, 6, user=5, original=True)])
    r = go(w, R.Approver("role", "Fin"))
    assert sorted(r.user_ids) == [5, 6] and r.acting_for == {}


def test_unknown_or_inactive_kind_yields_nobody():
    w = world(assignments=[asg(1, 4, kind="matrix")])
    r = go(w, R.Approver("manager_kind", "matrix"))
    assert r.via == "hr"
    assert any("unknown or inactive" in x for x in r.explanation)
    r = go(world(kinds={"functional"}), REPORTING)
    assert r.via == "hr"


def test_user_scope_self_manager_stops_the_search():
    w = world(assignments=[asg(1, 1), asg(2, 3, "company")])
    r = go(w)
    assert r.via == "hr" and r.user_ids == [9]


def test_cover_date_window():
    base = dict(assignments=[asg(1, 2)])
    ended = cover(1, 3, user=2, start=date(2030, 6, 1), end=date(2030, 6, 9))
    starts = cover(1, 3, user=2, start=date(2030, 6, 11), end=None)
    assert go(world(**base, covers=[ended])).user_ids == [2]
    assert go(world(**base, covers=[starts])).user_ids == [2]


def test_post_cover_beats_user_cover_and_named_beats_all():
    posts = {7: R.Post(7, "Mgr", True, None)}
    hold = [R.Holder(7, 2, date(2020, 1, 1), None)]
    w = world(assignments=[asg(1, None, post=7)], posts=posts, holders=hold,
              covers=[cover(1, 3, user=2), cover(2, 4, post=7)])
    assert go(w).user_ids == [4]
    w = world(assignments=[asg(1, 2)],
              covers=[cover(1, 3, user=2), cover(2, 4, user=2, subs={"leave"})])
    assert go(w).user_ids == [4]


def test_role_with_several_covered_users():
    w = world(role_users={"Fin": [5, 6]},
              covers=[cover(1, 7, user=5), cover(2, 8, user=6)])
    r = go(w, R.Approver("role", "Fin"))
    assert sorted(r.user_ids) == [7, 8]


def test_via_post_id():
    posts = {7: R.Post(7, "Mgr", True, None)}
    hold = [R.Holder(7, 4, date(2020, 1, 1), None)]
    assert go(world(posts=posts, holders=hold),
              R.Approver("post", "7")).via_post_id == 7
    assert go(world(), R.Approver("specific_user", "6")).via_post_id is None


def test_hr_sorted_and_excludes_inactive():
    people = {i: P(i, i != 3, "Eng", "Mumbai") for i in range(1, 10)}
    r = go(world(people=people, hr_ids=[8, 3, 2, 8]))
    assert r.via == "hr" and r.user_ids == [2, 8]


def test_base_index_matches_find_assignment():
    a = [asg(1, 2, "company"), asg(2, 3, "location", loc=" mumbai "),
         asg(3, 4, "department", dept="ENG"), asg(4, 5, user=1),
         asg(5, 6, user=1, subs={"leave"}), asg(6, 7, user=2),
         asg(7, 8, "company", kind="functional"),
         asg(8, 8, user=3, end=date(2030, 1, 1))]
    w = world(assignments=a)
    look = R.base_index(w, D)
    for kind in ("reporting", "functional"):
        for uid in list(range(1, 10)) + [99]:
            got = look(kind, uid)
            want = R.find_assignment(w, kind, uid, "", D)
            assert (got and got.id) == (want and want.id), (kind, uid)


def test_explanation_names_users_with_at_and_assignments_with_hash():
    w = world(assignments=[asg(7, 2)], covers=[cover(1, 3, user=2)])
    text = " ".join(go(w).explanation)
    assert "assignment #7" in text and "@3 is acting for @2" in text
