"""Emergency profile data + night-shift consent (Roadmap v2 Phase 2, Task 8).

PRIVACY: gender, blood group and emergency contacts are sensitive personal
data. They are served ONLY by the routes below: to the employee themself
(`/me/*`), to HR (`/hr/employees/{user_id}/*`, `hr employee read|write`) and
to schedulers/managers for their scope (`/roster/team-contacts`, which omits
gender). They are intentionally absent from every general employee schema.
"""
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import deps
from app.api.v1.endpoints.hr import HR_READ, HR_WRITE, log_audit
from app.api.v1.endpoints.roster_common import (
    commit_or_409, guard_conflicts, require_manage,
)
from app.models.roster import RosterEntry
from app.models.safety import NightShiftConsent
from app.models.user import User
from app.services import roster as roster_svc
from app.services import safety_profile as svc

me_router = APIRouter()
hr_router = APIRouter()
roster_router = APIRouter()


class ProfileIn(BaseModel):
    gender: Optional[str] = None
    blood_group: Optional[str] = None


class ContactIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    relation: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., max_length=20)
    is_primary: bool = False


class ContactPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    relation: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    is_primary: Optional[bool] = None


async def _profile(db, user_id: int) -> dict:
    emp = await svc.employee_for_user(db, user_id)
    return svc.profile_dict(emp, await svc.list_contacts(db, user_id))


# ------------------------------- self --------------------------------

@me_router.get("/me/safety-profile")
async def get_my_profile(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    return await _profile(db, current_user.id)


@me_router.put("/me/safety-profile")
@guard_conflicts
async def put_my_profile(
    *, db: deps.DBDep, body: ProfileIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    await svc.set_profile(db, current_user.id, body.model_dump(exclude_unset=True))
    await commit_or_409(db)
    return await _profile(db, current_user.id)


@me_router.get("/me/emergency-contacts")
async def list_my_contacts(
    db: deps.DBDep, current_user: User = Depends(deps.get_current_user),
) -> Any:
    return [svc.contact_dict(c) for c in await svc.list_contacts(db, current_user.id)]


@me_router.post("/me/emergency-contacts", status_code=201)
@guard_conflicts
async def add_my_contact(
    *, db: deps.DBDep, body: ContactIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    c = await svc.add_contact(db, current_user.id, **body.model_dump())
    await commit_or_409(db)
    await db.refresh(c)
    return svc.contact_dict(c)


@me_router.put("/me/emergency-contacts/{contact_id}")
@guard_conflicts
async def update_my_contact(
    *, db: deps.DBDep, contact_id: int, body: ContactPatch,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    c = await svc.update_contact(
        db, current_user.id, contact_id, body.model_dump(exclude_unset=True))
    await commit_or_409(db)
    await db.refresh(c)
    return svc.contact_dict(c)


@me_router.delete("/me/emergency-contacts/{contact_id}")
@guard_conflicts
async def delete_my_contact(
    *, db: deps.DBDep, contact_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    await svc.delete_contact(db, current_user.id, contact_id)
    await commit_or_409(db)
    return {"ok": True}


# -------------------------------- HR ---------------------------------

def _hr_read(user: User) -> None:
    if not (deps.user_has_permission(user, HR_READ)
            or deps.user_has_permission(user, HR_WRITE)):
        raise HTTPException(403, f"Not enough permissions: {HR_READ}")


def _hr_write(user: User) -> None:
    if not deps.user_has_permission(user, HR_WRITE):
        raise HTTPException(403, f"Not enough permissions: {HR_WRITE}")


async def _audit(db, request, actor, action, uid, details=None):
    await log_audit(db, actor.id, action, "employee_safety", str(uid),
                    details or {}, request)


@hr_router.get("/employees/{user_id}/safety-profile")
async def hr_get_profile(
    *, db: deps.DBDep, request: Request, user_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_read(current_user)
    out = await _profile(db, user_id)
    await _audit(db, request, current_user, "safety.profile.view", user_id)
    return out


@hr_router.put("/employees/{user_id}/safety-profile")
@guard_conflicts
async def hr_put_profile(
    *, db: deps.DBDep, request: Request, user_id: int, body: ProfileIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_write(current_user)
    data = body.model_dump(exclude_unset=True)
    await svc.set_profile(db, user_id, data)
    await commit_or_409(db)
    await _audit(db, request, current_user, "safety.profile.update", user_id,
                 {"fields": list(data)})
    return await _profile(db, user_id)


@hr_router.post("/employees/{user_id}/emergency-contacts", status_code=201)
@guard_conflicts
async def hr_add_contact(
    *, db: deps.DBDep, request: Request, user_id: int, body: ContactIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_write(current_user)
    c = await svc.add_contact(db, user_id, **body.model_dump())
    await commit_or_409(db)
    await db.refresh(c)
    await _audit(db, request, current_user, "safety.contact.add", user_id)
    return svc.contact_dict(c)


@hr_router.put("/employees/{user_id}/emergency-contacts/{contact_id}")
@guard_conflicts
async def hr_update_contact(
    *, db: deps.DBDep, request: Request, user_id: int, contact_id: int,
    body: ContactPatch, current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_write(current_user)
    c = await svc.update_contact(
        db, user_id, contact_id, body.model_dump(exclude_unset=True))
    await commit_or_409(db)
    await db.refresh(c)
    await _audit(db, request, current_user, "safety.contact.update", user_id)
    return svc.contact_dict(c)


@hr_router.delete("/employees/{user_id}/emergency-contacts/{contact_id}")
@guard_conflicts
async def hr_delete_contact(
    *, db: deps.DBDep, request: Request, user_id: int, contact_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_write(current_user)
    await svc.delete_contact(db, user_id, contact_id)
    await commit_or_409(db)
    await _audit(db, request, current_user, "safety.contact.delete", user_id)
    return {"ok": True}


# ---- night-shift consent (HR-managed; HR read can list) ----

class ConsentIn(BaseModel):
    consent_given: bool = True
    valid_from: date
    valid_to: Optional[date] = None
    document_url: Optional[str] = Field(None, max_length=500)
    note: Optional[str] = Field(None, max_length=255)


class ConsentEnd(BaseModel):
    valid_to: Optional[date] = None


async def _need_employee(db, user_id: int) -> None:
    await svc.employee_for_user(db, user_id)


@hr_router.get("/employees/{user_id}/night-consents")
async def list_consents(
    *, db: deps.DBDep, user_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_read(current_user)
    await _need_employee(db, user_id)
    rows = (await db.execute(
        select(NightShiftConsent).where(NightShiftConsent.user_id == user_id)
        .order_by(NightShiftConsent.valid_from.desc(), NightShiftConsent.id.desc())
    )).scalars().all()
    return [svc.consent_dict(c) for c in rows]


@hr_router.post("/employees/{user_id}/night-consents", status_code=201)
@guard_conflicts
async def create_consent(
    *, db: deps.DBDep, request: Request, user_id: int, body: ConsentIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _hr_write(current_user)
    await _need_employee(db, user_id)
    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise HTTPException(422, "valid_to cannot be before valid_from")
    c = NightShiftConsent(
        user_id=user_id, consent_given=body.consent_given,
        valid_from=body.valid_from, valid_to=body.valid_to,
        recorded_by_id=current_user.id,
        document_url=(body.document_url or None),
        note=(body.note or None))
    db.add(c)
    await commit_or_409(db)
    await db.refresh(c)
    await _audit(db, request, current_user, "safety.consent.create", user_id,
                 {"consent_id": c.id, "consent_given": c.consent_given})
    return svc.consent_dict(c)


@hr_router.post("/employees/{user_id}/night-consents/{consent_id}/end")
@guard_conflicts
async def end_consent(
    *, db: deps.DBDep, request: Request, user_id: int, consent_id: int,
    body: ConsentEnd, current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Revoke / end-date a consent. Default end = today (the consent stops
    applying after today); a consent that has not started yet is withdrawn."""
    _hr_write(current_user)
    c = (await db.execute(select(NightShiftConsent).where(
        NightShiftConsent.id == consent_id,
        NightShiftConsent.user_id == user_id).with_for_update())
    ).scalars().first()
    if c is None:
        raise HTTPException(404, "Consent not found")
    today = datetime.now(timezone.utc).date()
    end = body.valid_to
    if end is None:
        if c.valid_from > today:
            c.consent_given = False
        else:
            end = today
    if end is not None:
        if end < c.valid_from:
            raise HTTPException(422, "valid_to cannot be before valid_from")
        c.valid_to = end
    await commit_or_409(db)
    await db.refresh(c)
    await _audit(db, request, current_user, "safety.consent.end", user_id,
                 {"consent_id": c.id})
    return svc.consent_dict(c)


# ------------------------------ roster -------------------------------

@roster_router.get("/team-contacts")
async def team_contacts(
    *, db: deps.DBDep, request: Request, department: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Emergency contacts for the caller's manageable employees. Gender is
    deliberately NOT included. Reads are audited."""
    scoped_all = await roster_svc.scoped_employees(db, current_user)
    if not scoped_all and not roster_svc.is_roster_admin(current_user):
        raise HTTPException(403, "You have no roster scope.")
    scoped = [e for e in scoped_all if not department or e.department == department]
    allowed = await roster_svc.manageable_subset(
        db, current_user, {e.user_id for e in scoped if e.user_id})
    emps = sorted((e for e in scoped if e.user_id in allowed),
                  key=lambda e: ((e.user.full_name if e.user else "") or "").lower())
    contacts = await svc.contacts_for_users(db, [e.user_id for e in emps])
    await log_audit(db, current_user.id, "safety.team_contacts.view",
                    "employee_safety", department or "*",
                    {"count": len(emps)}, request)
    return [{
        "user_id": e.user_id,
        "name": e.user.full_name if e.user else None,
        "department": e.department,
        "phone": e.user.phone if e.user else None,
        "blood_group": e.blood_group,
        "contacts": [svc.contact_dict(c) for c in contacts[e.user_id]],
    } for e in emps]


class TransportIn(BaseModel):
    required: bool


@roster_router.patch("/entries/{entry_id}/transport")
@guard_conflicts
async def set_transport(
    *, db: deps.DBDep, entry_id: int, body: TransportIn,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Cab/transport flag on a working cell. Not a schedule change: no
    history row, no lock-window guard, no acknowledgement."""
    entry = (await db.execute(select(RosterEntry).where(
        RosterEntry.id == entry_id).with_for_update())).scalars().first()
    if entry is None:
        raise HTTPException(404, "Roster entry not found")
    await require_manage(db, current_user, entry.employee_id)
    if body.required and (entry.is_week_off or not entry.shift_template_id):
        raise HTTPException(400, "Transport can only be set on a working shift")
    entry.transport_required = body.required
    await commit_or_409(db)
    await db.refresh(entry)
    return {"id": entry.id, "transport_required": entry.transport_required}
