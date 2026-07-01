"""Performance Management endpoints.

Read-only bridges to Prompt-5 revision cycles via
`GET /performance/ratings/{user_id}` — the revision workspace displays
each employee's latest final rating without triggering any hikes.

Release gate: any employee-facing read of a review checks
`is_visible_to_employee` (both instance.is_released AND
cycle.released_at) before returning content. Manager and HR views
skip the gate but still see per-permission checks.
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.api.v1.endpoints.hr import log_audit
from app.models.approval import ApprovalItem, ApprovalStatus, ApprovalStep
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.performance import (
    ActionItemStatus, CalibrationAdjustment, CalibrationSession,
    ConfidenceRAG, CycleStatus, CycleType, Goal, GoalCheckIn, GoalStatus,
    GoalType, KeyResult, OneOnOne, OneOnOneActionItem, QuestionType,
    ReviewCycle, ReviewForm, ReviewInstance, ReviewPhase, ReviewQuestion,
    ReviewResponse, ReviewSection, ReviewTemplateAssignment,
)
from app.models.user import User
from app.services.goals import (
    compute_goal_progress, is_at_risk, rollup_parent_progress,
    validate_weight_sum,
)
from app.services.performance import (
    apply_manager_override, compute_distribution, compute_overall_score,
    is_visible_to_employee,
)


router = APIRouter()


# ============================================================
# RBAC helpers
# ============================================================


PERM_CYCLE_ADMIN = "performance cycle admin"
PERM_CALIBRATION = "performance calibration"
PERM_VIEW_ALL = "performance view all"
PERM_MANAGE_1_1 = "performance one_on_one"


def _user_has_perm(user: User, name: str) -> bool:
    if user.is_superuser:
        return True
    for role in user.roles or []:
        for perm in role.permissions or []:
            if (perm.name or "") == name:
                return True
    return False


def _is_hr(user: User) -> bool:
    if user.is_superuser:
        return True
    role_names = [(r.name or "").lower() for r in user.roles or []]
    return any(n in role_names for n in ("hr", "super admin", "admin", "ceo"))


async def _team_user_ids(db, manager_user_id: int) -> List[int]:
    rows = (await db.execute(
        select(User.id).where(User.manager_id == manager_user_id)
    )).scalars().all()
    return list(rows)


async def _employee_by_user_id(db, user_id: int) -> Optional[Employee]:
    return (await db.execute(
        select(Employee).where(Employee.user_id == user_id)
    )).scalar_one_or_none()


# ============================================================
# GOALS
# ============================================================


def _goal_dict(g: Goal, *, warning: Optional[str] = None) -> dict:
    return {
        "id": g.id, "owner_id": g.owner_id, "title": g.title,
        "description": g.description, "goal_type": g.goal_type,
        "parent_goal_id": g.parent_goal_id, "weight": g.weight,
        "target": g.target, "unit": g.unit,
        "start_date": g.start_date, "due_date": g.due_date,
        "cycle_id": g.cycle_id, "status": g.status,
        "latest_progress": g.latest_progress,
        "latest_confidence": g.latest_confidence,
        "created_at": g.created_at, "updated_at": g.updated_at,
        "weight_warning": warning,
    }


async def _refresh_goal_progress(db, g: Goal) -> None:
    """Recompute latest_progress/confidence + at-risk from KRs+check-ins."""
    krs = (await db.execute(
        select(KeyResult).where(KeyResult.goal_id == g.id)
    )).scalars().all()
    cis = (await db.execute(
        select(GoalCheckIn).where(GoalCheckIn.goal_id == g.id)
    )).scalars().all()
    p, c = compute_goal_progress(key_results=krs, check_ins=cis)
    g.latest_progress = p
    g.latest_confidence = c
    if is_at_risk(cis):
        g.status = GoalStatus.AT_RISK
    elif g.status == GoalStatus.AT_RISK and not is_at_risk(cis):
        g.status = GoalStatus.ACTIVE


@router.get("/goals")
async def list_goals(
    db: deps.DBDep,
    owner_id: Optional[int] = Query(None),
    cycle_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(Goal)
    if owner_id is not None:
        stmt = stmt.where(Goal.owner_id == owner_id)
    if cycle_id is not None:
        stmt = stmt.where(Goal.cycle_id == cycle_id)
    if status_filter:
        stmt = stmt.where(Goal.status == status_filter)

    if not _is_hr(current_user):
        # Manager sees own + team, employee sees own.
        team = await _team_user_ids(db, current_user.id)
        allowed = set(team + [current_user.id])
        stmt = stmt.where(Goal.owner_id.in_(allowed))
    stmt = stmt.order_by(Goal.owner_id, Goal.due_date)
    rows = (await db.execute(stmt)).scalars().all()

    # Compute weight-sum warning per owner (for the owner's active goals).
    by_owner: Dict[int, List[Goal]] = {}
    for g in rows:
        by_owner.setdefault(g.owner_id, []).append(g)
    warnings_by_owner: Dict[int, str] = {}
    for uid, gs in by_owner.items():
        w = validate_weight_sum([g.weight for g in gs if g.status == GoalStatus.ACTIVE])
        if not w.within_tolerance:
            warnings_by_owner[uid] = w.message
    return [_goal_dict(g, warning=warnings_by_owner.get(g.owner_id)) for g in rows]


@router.get("/goals/my")
async def my_goals(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(Goal).where(Goal.owner_id == current_user.id)
        .order_by(Goal.due_date)
    )).scalars().all()
    w = validate_weight_sum([g.weight for g in rows if g.status == GoalStatus.ACTIVE])
    warning = None if w.within_tolerance else w.message
    return [_goal_dict(g, warning=warning) for g in rows]


@router.get("/goals/tree/{owner_id}")
async def goal_alignment_tree(
    owner_id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Return a nested company → dept → owner tree of goals aligned to
    each other via parent_goal_id."""
    if owner_id != current_user.id and not _is_hr(current_user):
        # Manager may see own reportees' trees.
        team = await _team_user_ids(db, current_user.id)
        if owner_id not in team:
            raise HTTPException(403, "Not authorized")

    my_goals_list = (await db.execute(
        select(Goal).where(Goal.owner_id == owner_id)
    )).scalars().all()
    parent_ids = {g.parent_goal_id for g in my_goals_list if g.parent_goal_id}
    # Walk up 3 levels max.
    ancestors: Dict[int, Goal] = {}
    layer = parent_ids
    for _ in range(3):
        if not layer:
            break
        rows = (await db.execute(
            select(Goal).where(Goal.id.in_(layer))
        )).scalars().all()
        for g in rows:
            ancestors[g.id] = g
        layer = {g.parent_goal_id for g in rows if g.parent_goal_id}
    return {
        "owner_goals": [_goal_dict(g) for g in my_goals_list],
        "ancestors": [_goal_dict(g) for g in ancestors.values()],
    }


@router.post("/goals")
async def create_goal(
    payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    owner_id = payload.get("owner_id", current_user.id)
    if owner_id != current_user.id and not _is_hr(current_user):
        raise HTTPException(403, "Cannot create goals for another employee")
    for k in ("title", "start_date", "due_date"):
        if not payload.get(k):
            raise HTTPException(400, f"{k} required")
    g = Goal(
        owner_id=owner_id,
        title=payload["title"],
        description=payload.get("description"),
        goal_type=payload.get("goal_type", GoalType.OKR),
        parent_goal_id=payload.get("parent_goal_id"),
        weight=float(payload.get("weight", 0.0)),
        target=payload.get("target"),
        unit=payload.get("unit"),
        start_date=date.fromisoformat(payload["start_date"]),
        due_date=date.fromisoformat(payload["due_date"]),
        cycle_id=payload.get("cycle_id"),
        status=payload.get("status", GoalStatus.DRAFT),
        created_by_id=current_user.id,
    )
    db.add(g)
    await db.flush()
    await log_audit(db, current_user.id, "GOAL_CREATE", "goal",
                    str(g.id), {"title": g.title}, request)
    await db.commit()
    await db.refresh(g)
    return _goal_dict(g)


@router.patch("/goals/{gid}")
async def update_goal(
    gid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    g = await db.get(Goal, gid)
    if g is None:
        raise HTTPException(404, "Goal not found")
    if g.owner_id != current_user.id and not _is_hr(current_user):
        raise HTTPException(403, "Cannot edit another employee's goal")
    for k in ("title", "description", "goal_type", "parent_goal_id",
              "weight", "target", "unit", "cycle_id", "status"):
        if k in payload:
            setattr(g, k, payload[k])
    for k in ("start_date", "due_date"):
        if k in payload:
            setattr(g, k, date.fromisoformat(payload[k]))
    await db.flush()
    await log_audit(db, current_user.id, "GOAL_UPDATE", "goal",
                    str(gid), payload, request)
    await db.commit()
    await db.refresh(g)
    return _goal_dict(g)


@router.delete("/goals/{gid}")
async def delete_goal(
    gid: int, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    g = await db.get(Goal, gid)
    if g is None:
        raise HTTPException(404, "Goal not found")
    if g.owner_id != current_user.id and not _is_hr(current_user):
        raise HTTPException(403, "Cannot delete another employee's goal")
    g.status = GoalStatus.CANCELLED
    await log_audit(db, current_user.id, "GOAL_CANCEL", "goal",
                    str(gid), {}, request)
    await db.commit()
    return {"message": "Cancelled"}


# ----- Key Results ----------------------------------


@router.post("/goals/{gid}/key-results")
async def add_kr(
    gid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    g = await db.get(Goal, gid)
    if g is None:
        raise HTTPException(404, "Goal not found")
    if g.owner_id != current_user.id and not _is_hr(current_user):
        raise HTTPException(403, "Not authorized")
    kr = KeyResult(
        goal_id=gid, title=payload["title"],
        target=payload.get("target"), unit=payload.get("unit"),
        weight=float(payload.get("weight", 0.0)),
        progress_percent=float(payload.get("progress_percent", 0.0)),
    )
    db.add(kr)
    await db.flush()
    await _refresh_goal_progress(db, g)
    await log_audit(db, current_user.id, "KR_CREATE", "key_result",
                    str(kr.id), {"title": kr.title}, request)
    await db.commit()
    await db.refresh(kr)
    return {c.name: getattr(kr, c.name) for c in kr.__table__.columns}


@router.patch("/key-results/{kid}")
async def patch_kr(
    kid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    kr = await db.get(KeyResult, kid)
    if kr is None:
        raise HTTPException(404, "KR not found")
    g = await db.get(Goal, kr.goal_id)
    if g is None or (g.owner_id != current_user.id and not _is_hr(current_user)):
        raise HTTPException(403, "Not authorized")
    for k in ("title", "target", "unit", "weight",
              "progress_percent", "status"):
        if k in payload:
            setattr(kr, k, payload[k])
    await db.flush()
    await _refresh_goal_progress(db, g)
    await log_audit(db, current_user.id, "KR_UPDATE", "key_result",
                    str(kid), payload, request)
    await db.commit()
    await db.refresh(kr)
    return {c.name: getattr(kr, c.name) for c in kr.__table__.columns}


# ----- Check-ins ------------------------------------


@router.post("/goals/{gid}/check-ins")
async def add_check_in(
    gid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    g = await db.get(Goal, gid)
    if g is None:
        raise HTTPException(404, "Goal not found")
    if g.owner_id != current_user.id and not _is_hr(current_user):
        # Managers can also add check-ins for team members.
        team = await _team_user_ids(db, current_user.id)
        if g.owner_id not in team:
            raise HTTPException(403, "Not authorized")
    ci = GoalCheckIn(
        goal_id=gid,
        progress_percent=float(payload.get("progress_percent", 0.0)),
        confidence=payload.get("confidence", ConfidenceRAG.GREEN),
        note=payload.get("note"),
        created_by_id=current_user.id,
    )
    db.add(ci)
    await db.flush()
    await _refresh_goal_progress(db, g)
    await log_audit(db, current_user.id, "GOAL_CHECKIN", "goal_check_in",
                    str(ci.id),
                    {"goal_id": gid, "progress": ci.progress_percent},
                    request)
    await db.commit()
    return {c.name: getattr(ci, c.name) for c in ci.__table__.columns}


@router.get("/goals/{gid}/check-ins")
async def list_check_ins(
    gid: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    g = await db.get(Goal, gid)
    if g is None:
        raise HTTPException(404, "Goal not found")
    if g.owner_id != current_user.id and not _is_hr(current_user):
        team = await _team_user_ids(db, current_user.id)
        if g.owner_id not in team:
            raise HTTPException(403, "Not authorized")
    rows = (await db.execute(
        select(GoalCheckIn).where(GoalCheckIn.goal_id == gid)
        .order_by(GoalCheckIn.created_at.desc())
    )).scalars().all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns}
            for r in rows]


# ============================================================
# REVIEW CYCLES + FORMS
# ============================================================


@router.get("/cycles")
async def list_cycles(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(ReviewCycle).order_by(ReviewCycle.start_date.desc())
    )).scalars().all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns}
            for r in rows]


@router.post("/cycles")
async def create_cycle(
    payload: dict, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CYCLE_ADMIN])),
) -> Any:
    c = ReviewCycle(
        name=payload["name"],
        cycle_type=payload.get("cycle_type", CycleType.ANNUAL),
        start_date=date.fromisoformat(payload["start_date"]),
        end_date=date.fromisoformat(payload["end_date"]),
        phases_json=payload.get("phases_json", {}),
        population_json=payload.get("population_json", {}),
        status=CycleStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(c)
    await db.flush()
    await log_audit(db, current_user.id, "CYCLE_CREATE", "review_cycle",
                    str(c.id), {"name": c.name}, request)
    await db.commit()
    await db.refresh(c)
    return {col.name: getattr(c, col.name) for col in c.__table__.columns}


@router.post("/cycles/{cid}/launch")
async def launch_cycle(
    cid: int, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CYCLE_ADMIN])),
) -> Any:
    """Create a ReviewInstance for every employee in the population."""
    cycle = await db.get(ReviewCycle, cid)
    if cycle is None:
        raise HTTPException(404, "Cycle not found")
    if cycle.status not in (CycleStatus.DRAFT,):
        raise HTTPException(400, "Cycle already launched")

    # Resolve population.
    pop = cycle.population_json or {}
    stmt = select(Employee).options(selectinload(Employee.user)).where(
        Employee.status == "active",
    )
    if pop.get("departments"):
        stmt = stmt.where(Employee.department.in_(pop["departments"]))
    if pop.get("employee_ids"):
        stmt = stmt.where(Employee.id.in_(pop["employee_ids"]))
    emps = (await db.execute(stmt)).scalars().all()

    # Pick a form via template assignments (simplified: first assignment).
    assigns = (await db.execute(
        select(ReviewTemplateAssignment).where(
            ReviewTemplateAssignment.cycle_id == cid
        ).order_by(ReviewTemplateAssignment.priority.desc())
    )).scalars().all()
    if not assigns:
        raise HTTPException(
            400,
            "Attach at least one ReviewForm template to this cycle before launch.",
        )

    default_form_id = assigns[0].form_id
    created = 0
    for e in emps:
        # Skip already-created.
        exist = (await db.execute(
            select(ReviewInstance).where(and_(
                ReviewInstance.cycle_id == cid,
                ReviewInstance.employee_id == e.user_id,
            ))
        )).scalar_one_or_none()
        if exist:
            continue

        # Pick a form: match by filter_json; fall back to default.
        form_id = default_form_id
        for a in assigns:
            fj = a.filter_json or {}
            depts = fj.get("departments")
            if depts and e.department not in depts:
                continue
            form_id = a.form_id
            break

        mgr_id = e.user.manager_id if e.user else None
        inst = ReviewInstance(
            cycle_id=cid, employee_id=e.user_id, manager_id=mgr_id,
            form_id=form_id, current_phase=ReviewPhase.SELF,
        )
        db.add(inst)
        # Notify employee.
        db.add(Notification(
            user_id=e.user_id,
            title=f"{cycle.name}: self-review is open",
            message="Head to My Review to complete the self-assessment.",
            type="info",
            resource_type="review_instance", resource_id="",
        ))
        created += 1

    cycle.status = CycleStatus.ACTIVE
    await log_audit(
        db, current_user.id, "CYCLE_LAUNCH", "review_cycle",
        str(cid), {"instances_created": created}, request,
    )
    await db.commit()
    return {"instances_created": created, "cycle_id": cid}


@router.post("/cycles/{cid}/assign-template")
async def assign_template(
    cid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CYCLE_ADMIN])),
) -> Any:
    a = ReviewTemplateAssignment(
        cycle_id=cid,
        form_id=payload["form_id"],
        filter_json=payload.get("filter_json", {}),
        priority=payload.get("priority", 0),
    )
    db.add(a)
    await db.flush()
    await log_audit(db, current_user.id, "CYCLE_ASSIGN_TEMPLATE",
                    "review_template_assignment", str(a.id),
                    payload, request)
    await db.commit()
    await db.refresh(a)
    return {c.name: getattr(a, c.name) for c in a.__table__.columns}


# ----- forms ---------------------------------------


@router.get("/forms")
async def list_forms(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(ReviewForm).options(
        selectinload(ReviewForm.sections).selectinload(ReviewSection.questions)
    )
    forms = (await db.execute(stmt)).scalars().all()
    out = []
    for f in forms:
        out.append({
            "id": f.id, "name": f.name, "description": f.description,
            "scale_json": f.scale_json, "is_active": f.is_active,
            "sections": [
                {
                    "id": s.id, "title": s.title, "description": s.description,
                    "sequence": s.sequence, "weight": s.weight,
                    "questions": [
                        {
                            "id": q.id, "prompt": q.prompt,
                            "sequence": q.sequence,
                            "question_type": q.question_type,
                            "weight_within_section": q.weight_within_section,
                            "scale_json": q.scale_json,
                            "is_required": q.is_required,
                        }
                        for q in s.questions
                    ],
                }
                for s in f.sections
            ],
        })
    return out


@router.post("/forms")
async def create_form(
    payload: dict, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CYCLE_ADMIN])),
) -> Any:
    f = ReviewForm(
        name=payload["name"], description=payload.get("description"),
        scale_json=payload.get("scale_json", {"min": 1, "max": 5}),
    )
    db.add(f)
    await db.flush()

    for si, section in enumerate(payload.get("sections", [])):
        s = ReviewSection(
            form_id=f.id, title=section["title"],
            description=section.get("description"),
            sequence=section.get("sequence", si),
            weight=float(section.get("weight", 0.0)),
        )
        db.add(s)
        await db.flush()
        for qi, q in enumerate(section.get("questions", [])):
            db.add(ReviewQuestion(
                section_id=s.id, prompt=q["prompt"],
                sequence=q.get("sequence", qi),
                question_type=q.get("question_type", QuestionType.RATING),
                weight_within_section=float(q.get("weight_within_section", 1.0)),
                scale_json=q.get("scale_json"),
                is_required=q.get("is_required", True),
            ))
    await log_audit(db, current_user.id, "FORM_CREATE", "review_form",
                    str(f.id), {"name": f.name}, request)
    await db.commit()
    return {"id": f.id, "name": f.name}


# ============================================================
# REVIEW INSTANCE — self / manager / release
# ============================================================


async def _load_form_shape(db, form_id: int):
    sections = (await db.execute(
        select(ReviewSection).where(ReviewSection.form_id == form_id)
        .options(selectinload(ReviewSection.questions))
        .order_by(ReviewSection.sequence)
    )).scalars().all()
    return sections


@router.get("/my-review")
async def my_review(
    db: deps.DBDep,
    cycle_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Current employee's own review. Pre-release views hide manager
    ratings; post-release exposes everything."""
    stmt = select(ReviewInstance).where(ReviewInstance.employee_id == current_user.id)
    if cycle_id:
        stmt = stmt.where(ReviewInstance.cycle_id == cycle_id)
    inst = (await db.execute(
        stmt.order_by(ReviewInstance.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if inst is None:
        return None

    cycle = await db.get(ReviewCycle, inst.cycle_id)
    sections = await _load_form_shape(db, inst.form_id)
    responses = (await db.execute(
        select(ReviewResponse).where(ReviewResponse.instance_id == inst.id)
    )).scalars().all()
    visible = is_visible_to_employee(instance=inst, cycle=cycle)

    return {
        "instance": {
            "id": inst.id, "cycle_id": inst.cycle_id,
            "current_phase": inst.current_phase,
            "is_released": inst.is_released,
            "self_submitted_at": inst.self_submitted_at,
            "manager_submitted_at": inst.manager_submitted_at,
            # Manager fields only exposed post-release.
            "final_rating": inst.final_rating if visible else None,
            "manager_override_reason": (
                inst.manager_override_reason if visible else None
            ),
        },
        "cycle": {"id": cycle.id, "name": cycle.name, "released_at": cycle.released_at}
        if cycle else None,
        "sections": [
            {
                "id": s.id, "title": s.title, "weight": s.weight,
                "questions": [
                    {
                        "id": q.id, "prompt": q.prompt,
                        "question_type": q.question_type,
                        "weight_within_section": q.weight_within_section,
                        "scale_json": q.scale_json,
                        "is_required": q.is_required,
                    }
                    for q in s.questions
                ],
            }
            for s in sections
        ],
        "responses": [
            {
                "question_id": r.question_id,
                "self_rating": r.self_rating, "self_comment": r.self_comment,
                # Manager side hidden pre-release.
                "manager_rating": r.manager_rating if visible else None,
                "manager_comment": r.manager_comment if visible else None,
                "goal_snapshot_json": r.goal_snapshot_json,
            }
            for r in responses
        ],
    }


@router.post("/instances/{iid}/self-submit")
async def submit_self_review(
    iid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    inst = await db.get(ReviewInstance, iid)
    if inst is None:
        raise HTTPException(404, "Instance not found")
    if inst.employee_id != current_user.id:
        raise HTTPException(403, "Not your review")
    if inst.current_phase not in (ReviewPhase.SELF, ReviewPhase.NOT_STARTED):
        raise HTTPException(400, f"Cannot submit self in phase {inst.current_phase}")

    # Upsert responses.
    for resp in payload.get("responses", []):
        qid = resp["question_id"]
        r = (await db.execute(
            select(ReviewResponse).where(and_(
                ReviewResponse.instance_id == iid,
                ReviewResponse.question_id == qid,
            ))
        )).scalar_one_or_none()
        if r is None:
            r = ReviewResponse(instance_id=iid, question_id=qid)
            db.add(r)
        r.self_rating = resp.get("self_rating")
        r.self_comment = resp.get("self_comment")

    inst.current_phase = ReviewPhase.MANAGER
    inst.self_submitted_at = datetime.now(timezone.utc)

    # Notify manager.
    if inst.manager_id:
        db.add(Notification(
            user_id=inst.manager_id,
            title="Team review awaiting your input",
            message=f"Review #{iid} is ready for your assessment.",
            type="info",
            resource_type="review_instance", resource_id=str(iid),
        ))
    await log_audit(db, current_user.id, "REVIEW_SELF_SUBMIT",
                    "review_instance", str(iid), {}, request)
    await db.commit()
    return {"message": "Submitted", "next_phase": inst.current_phase}


@router.post("/instances/{iid}/manager-submit")
async def submit_manager_review(
    iid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    inst = await db.get(ReviewInstance, iid)
    if inst is None:
        raise HTTPException(404, "Instance not found")
    if inst.manager_id != current_user.id and not _is_hr(current_user):
        raise HTTPException(403, "Not this employee's manager")
    if inst.current_phase not in (ReviewPhase.MANAGER, ReviewPhase.SKIP_LEVEL):
        raise HTTPException(400, f"Cannot submit manager in phase {inst.current_phase}")

    for resp in payload.get("responses", []):
        qid = resp["question_id"]
        r = (await db.execute(
            select(ReviewResponse).where(and_(
                ReviewResponse.instance_id == iid,
                ReviewResponse.question_id == qid,
            ))
        )).scalar_one_or_none()
        if r is None:
            r = ReviewResponse(instance_id=iid, question_id=qid)
            db.add(r)
        r.manager_rating = resp.get("manager_rating")
        r.manager_comment = resp.get("manager_comment")

    # Compute overall + apply override.
    sections = await _load_form_shape(db, inst.form_id)
    responses = (await db.execute(
        select(ReviewResponse).where(ReviewResponse.instance_id == iid)
    )).scalars().all()
    overall = compute_overall_score(sections=sections, responses=responses)
    inst.computed_overall_rating = overall.computed_manager

    override_val = payload.get("manager_override_rating")
    override_reason = payload.get("manager_override_reason")
    decision = apply_manager_override(
        computed=overall.computed_manager,
        override=override_val, reason=override_reason,
    )
    if not decision.is_valid:
        raise HTTPException(400, decision.error or "Invalid override")
    if override_val is not None:
        inst.manager_override_rating = float(override_val)
        inst.manager_override_reason = decision.reason
    inst.calibrated_rating = None
    inst.final_rating = decision.final_rating
    inst.current_phase = ReviewPhase.CALIBRATION
    inst.manager_submitted_at = datetime.now(timezone.utc)

    await log_audit(
        db, current_user.id, "REVIEW_MGR_SUBMIT", "review_instance",
        str(iid),
        {
            "computed": overall.computed_manager,
            "override": override_val,
            "override_reason": override_reason,
        },
        request,
    )
    await db.commit()
    return {
        "message": "Submitted",
        "computed_overall_rating": overall.computed_manager,
        "final_rating": inst.final_rating,
    }


@router.get("/team-reviews")
async def team_reviews(
    db: deps.DBDep,
    cycle_id: Optional[int] = Query(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Manager's team-review queue."""
    stmt = select(ReviewInstance).where(
        ReviewInstance.manager_id == current_user.id
    )
    if cycle_id:
        stmt = stmt.where(ReviewInstance.cycle_id == cycle_id)
    stmt = stmt.order_by(ReviewInstance.current_phase, ReviewInstance.employee_id)
    rows = (await db.execute(stmt)).scalars().all()
    out = []
    for r in rows:
        user = await db.get(User, r.employee_id)
        out.append({
            "id": r.id, "employee_id": r.employee_id,
            "employee_name": user.full_name if user else None,
            "current_phase": r.current_phase,
            "self_submitted_at": r.self_submitted_at,
            "cycle_id": r.cycle_id,
        })
    return out


@router.post("/cycles/{cid}/release")
async def release_cycle(
    cid: int, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CYCLE_ADMIN])),
) -> Any:
    cycle = await db.get(ReviewCycle, cid)
    if cycle is None:
        raise HTTPException(404, "Cycle not found")
    now = datetime.now(timezone.utc)
    cycle.status = CycleStatus.RELEASED
    cycle.released_at = now
    instances = (await db.execute(
        select(ReviewInstance).where(ReviewInstance.cycle_id == cid)
    )).scalars().all()
    released_count = 0
    for i in instances:
        # Use calibrated_rating when set, else final_rating already set.
        if i.calibrated_rating is not None:
            i.final_rating = i.calibrated_rating
        i.is_released = True
        i.released_at = now
        i.current_phase = ReviewPhase.RELEASED
        released_count += 1
        # Notify employee.
        db.add(Notification(
            user_id=i.employee_id,
            title=f"{cycle.name}: your review is available",
            message="Head to My Review to see the outcome.",
            type="success",
            resource_type="review_instance", resource_id=str(i.id),
        ))
    await log_audit(
        db, current_user.id, "CYCLE_RELEASE", "review_cycle",
        str(cid), {"released_count": released_count}, request,
    )
    await db.commit()
    return {"released_count": released_count}


# ============================================================
# CALIBRATION
# ============================================================


@router.post("/calibration-sessions")
async def create_calibration_session(
    payload: dict, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CALIBRATION])),
) -> Any:
    s = CalibrationSession(
        cycle_id=payload["cycle_id"],
        department=payload.get("department"),
        name=payload.get("name"),
        target_curve_json=payload.get("target_curve_json"),
        facilitator_id=current_user.id,
    )
    db.add(s)
    await db.flush()
    await log_audit(db, current_user.id, "CALIBRATION_START",
                    "calibration_session", str(s.id), payload, request)
    await db.commit()
    await db.refresh(s)
    return {c.name: getattr(s, c.name) for c in s.__table__.columns}


@router.get("/calibration/{cid}/data")
async def calibration_data(
    cid: int, db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([PERM_CALIBRATION])),
) -> Any:
    session = await db.get(CalibrationSession, cid)
    if session is None:
        raise HTTPException(404, "Session not found")
    inst_stmt = select(ReviewInstance).where(
        ReviewInstance.cycle_id == session.cycle_id
    )
    instances = (await db.execute(inst_stmt)).scalars().all()

    # Filter by department if set.
    dept_filter = session.department
    filtered_rows = []
    for i in instances:
        emp = await _employee_by_user_id(db, i.employee_id)
        if dept_filter and (emp is None or emp.department != dept_filter):
            continue
        user = await db.get(User, i.employee_id)
        filtered_rows.append({
            "instance_id": i.id, "employee_id": i.employee_id,
            "employee_name": user.full_name if user else None,
            "department": emp.department if emp else None,
            "computed_overall_rating": i.computed_overall_rating,
            "manager_override_rating": i.manager_override_rating,
            "calibrated_rating": i.calibrated_rating,
            "final_rating": i.final_rating,
        })

    ratings = [
        r["final_rating"] for r in filtered_rows if r["final_rating"] is not None
    ]
    dist = compute_distribution(
        ratings=ratings,
        target_curve=session.target_curve_json,
    )
    return {
        "session": {c.name: getattr(session, c.name) for c in session.__table__.columns},
        "rows": filtered_rows,
        "distribution": {
            "total": dist.total,
            "mean": dist.mean, "stdev": dist.stdev,
            "buckets": [b.__dict__ for b in dist.buckets],
            "skew_warnings": dist.skew_warnings,
        },
    }


@router.post("/calibration/{cid}/adjust")
async def adjust_calibration(
    cid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.check_permissions([PERM_CALIBRATION])),
) -> Any:
    if not payload.get("reason") or len(payload["reason"].strip()) < 10:
        raise HTTPException(400, "Reason required (min 10 chars)")
    session = await db.get(CalibrationSession, cid)
    if session is None:
        raise HTTPException(404, "Session not found")
    inst = await db.get(ReviewInstance, payload["instance_id"])
    if inst is None:
        raise HTTPException(404, "Instance not found")
    old = inst.calibrated_rating or inst.final_rating
    new = float(payload["new_rating"])
    inst.calibrated_rating = new
    inst.final_rating = new
    inst.calibration_done_at = datetime.now(timezone.utc)
    adj = CalibrationAdjustment(
        session_id=cid, instance_id=inst.id,
        old_rating=old, new_rating=new, reason=payload["reason"],
        adjusted_by_id=current_user.id,
    )
    db.add(adj)
    await log_audit(
        db, current_user.id, "CALIBRATION_ADJUST",
        "calibration_adjustment", str(inst.id),
        {"old": old, "new": new, "reason": payload["reason"]},
        request,
    )
    await db.commit()
    return {"instance_id": inst.id, "new_rating": new}


# ============================================================
# 1:1 s
# ============================================================


@router.get("/one-on-ones")
async def list_one_on_ones(
    db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    stmt = select(OneOnOne).where(or_(
        OneOnOne.manager_id == current_user.id,
        OneOnOne.reportee_id == current_user.id,
    )).order_by(OneOnOne.scheduled_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns}
            for r in rows]


@router.post("/one-on-ones")
async def create_one_on_one(
    payload: dict, db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    o = OneOnOne(
        manager_id=payload.get("manager_id", current_user.id),
        reportee_id=payload["reportee_id"],
        scheduled_at=datetime.fromisoformat(payload["scheduled_at"]),
        cadence=payload.get("cadence", "once"),
        duration_minutes=int(payload.get("duration_minutes", 30)),
        agenda_json=payload.get("agenda_json", []),
        shared_notes=payload.get("shared_notes"),
    )
    db.add(o)
    await db.flush()
    await log_audit(db, current_user.id, "ONE_ON_ONE_CREATE", "one_on_one",
                    str(o.id), {"reportee": o.reportee_id}, request)
    await db.commit()
    await db.refresh(o)
    return {c.name: getattr(o, c.name) for c in o.__table__.columns}


@router.patch("/one-on-ones/{oid}")
async def update_one_on_one(
    oid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    o = await db.get(OneOnOne, oid)
    if o is None:
        raise HTTPException(404, "Not found")
    if current_user.id not in (o.manager_id, o.reportee_id):
        raise HTTPException(403, "Not part of this meeting")
    for k in ("scheduled_at",):
        if k in payload:
            setattr(o, k, datetime.fromisoformat(payload[k]))
    for k in ("cadence", "duration_minutes", "agenda_json",
              "shared_notes", "status"):
        if k in payload:
            setattr(o, k, payload[k])
    # Private notes only editable by the owner.
    if "manager_private_notes" in payload and current_user.id == o.manager_id:
        o.manager_private_notes = payload["manager_private_notes"]
    if "reportee_private_notes" in payload and current_user.id == o.reportee_id:
        o.reportee_private_notes = payload["reportee_private_notes"]
    if payload.get("status") == "completed":
        o.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(o)
    return {c.name: getattr(o, c.name) for c in o.__table__.columns}


@router.post("/one-on-ones/{oid}/action-items")
async def add_action_item(
    oid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    o = await db.get(OneOnOne, oid)
    if o is None:
        raise HTTPException(404, "Not found")
    if current_user.id not in (o.manager_id, o.reportee_id):
        raise HTTPException(403, "Not part of this meeting")
    ai = OneOnOneActionItem(
        one_on_one_id=oid, title=payload["title"],
        description=payload.get("description"),
        owner_id=payload.get("owner_id", current_user.id),
        due_date=date.fromisoformat(payload["due_date"])
        if payload.get("due_date") else None,
        goal_id=payload.get("goal_id"),
    )
    db.add(ai)
    await db.flush()
    await db.commit()
    await db.refresh(ai)
    return {c.name: getattr(ai, c.name) for c in ai.__table__.columns}


@router.patch("/action-items/{aid}")
async def update_action_item(
    aid: int, payload: dict,
    db: deps.DBDep, request: Request,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    ai = await db.get(OneOnOneActionItem, aid)
    if ai is None:
        raise HTTPException(404, "Not found")
    for k in ("title", "description", "owner_id", "status"):
        if k in payload:
            setattr(ai, k, payload[k])
    if "due_date" in payload:
        ai.due_date = date.fromisoformat(payload["due_date"]) if payload["due_date"] else None
    if payload.get("status") == ActionItemStatus.DONE:
        ai.done_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ai)
    return {c.name: getattr(ai, c.name) for c in ai.__table__.columns}


@router.get("/one-on-ones/{oid}/action-items")
async def list_action_items(
    oid: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    rows = (await db.execute(
        select(OneOnOneActionItem).where(OneOnOneActionItem.one_on_one_id == oid)
    )).scalars().all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]


# ============================================================
# Ratings → hike bridge (READ-ONLY)
# ============================================================


@router.get("/ratings/{user_id}")
async def rating_for_user(
    user_id: int, db: deps.DBDep,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Latest RELEASED rating for `user_id`. Consumed by the revision
    workspace as decision context. Read-only bridge — never triggers
    a hike."""
    if user_id != current_user.id and not _is_hr(current_user):
        team = await _team_user_ids(db, current_user.id)
        if user_id not in team:
            raise HTTPException(403, "Not authorized")
    stmt = (
        select(ReviewInstance).where(and_(
            ReviewInstance.employee_id == user_id,
            ReviewInstance.is_released.is_(True),
        )).order_by(ReviewInstance.released_at.desc()).limit(1)
    )
    inst = (await db.execute(stmt)).scalar_one_or_none()
    if inst is None:
        return {"user_id": user_id, "final_rating": None}
    cycle = await db.get(ReviewCycle, inst.cycle_id)
    return {
        "user_id": user_id,
        "final_rating": inst.final_rating,
        "cycle_id": inst.cycle_id,
        "cycle_name": cycle.name if cycle else None,
        "released_at": inst.released_at,
    }
