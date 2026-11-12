"""Emergency profile data + night-shift consent (Phase 2 Task 8)."""
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.safety import EmployeeEmergencyContact, NightShiftConsent

GENDERS = ("female", "male", "other", "undisclosed")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
MAX_CONTACTS = 3


def validate_gender(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    v = v.strip().lower()
    if v not in GENDERS:
        raise HTTPException(422, f"gender must be one of {', '.join(GENDERS)}")
    return v


def validate_blood_group(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    v = v.strip().upper()
    if v not in BLOOD_GROUPS:
        raise HTTPException(
            422, f"blood_group must be one of {', '.join(BLOOD_GROUPS)}")
    return v


def validate_phone(v: str) -> str:
    v = (v or "").strip()
    digits = [c for c in v if c.isdigit()]
    if not (7 <= len(digits) <= 15) or any(
            c not in "0123456789+-() " for c in v):
        raise HTTPException(422, "phone must be 7-15 digits (spaces, +, -, () allowed)")
    return v


async def employee_for_user(db: AsyncSession, user_id: int) -> Employee:
    emp = (await db.execute(select(Employee).where(
        Employee.user_id == user_id))).scalars().first()
    if emp is None:
        raise HTTPException(404, "Employee profile not found")
    return emp


def profile_dict(emp: Employee, contacts: List[EmployeeEmergencyContact]) -> dict:
    return {"user_id": emp.user_id, "gender": emp.gender,
            "blood_group": emp.blood_group,
            "contacts": [contact_dict(c) for c in contacts]}


def contact_dict(c: EmployeeEmergencyContact) -> dict:
    return {"id": c.id, "name": c.name, "relation": c.relation,
            "phone": c.phone, "is_primary": c.is_primary}


async def list_contacts(db: AsyncSession, user_id: int, lock: bool = False):
    """`lock=True` does a current read (FOR UPDATE, refreshing identity-map
    rows): the transaction snapshot may predate the employee row lock."""
    q = (select(EmployeeEmergencyContact)
         .where(EmployeeEmergencyContact.user_id == user_id)
         .order_by(EmployeeEmergencyContact.is_primary.desc(),
                   EmployeeEmergencyContact.id))
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    return list((await db.execute(q)).scalars().all())


async def contacts_for_users(db: AsyncSession, user_ids: Iterable[int]) -> dict:
    ids = list(user_ids)
    out: dict = {u: [] for u in ids}
    if not ids:
        return out
    for c in (await db.execute(
        select(EmployeeEmergencyContact)
        .where(EmployeeEmergencyContact.user_id.in_(ids))
        .order_by(EmployeeEmergencyContact.is_primary.desc(),
                  EmployeeEmergencyContact.id))).scalars().all():
        out[c.user_id].append(c)
    return out


async def _lock_employee(db: AsyncSession, user_id: int) -> None:
    """Serialise contact writes per employee (row lock on the Employee)."""
    emp = (await db.execute(select(Employee).where(
        Employee.user_id == user_id).with_for_update())).scalars().first()
    if emp is None:
        raise HTTPException(404, "Employee profile not found")


async def _normalise_primary(
    db: AsyncSession, user_id: int, prefer_id: Optional[int] = None
) -> None:
    """Exactly one primary when any contact exists (prefer `prefer_id`,
    else keep the existing first primary, else the oldest contact)."""
    rows = await list_contacts(db, user_id, lock=True)
    if not rows:
        return
    keep = None
    if prefer_id is not None:
        keep = next((c for c in rows if c.id == prefer_id), None)
    if keep is None:
        keep = next((c for c in rows if c.is_primary), rows[0])
    for c in rows:
        c.is_primary = c.id == keep.id
    await db.flush()


async def add_contact(
    db: AsyncSession, user_id: int, *, name: str, relation: str, phone: str,
    is_primary: bool,
) -> EmployeeEmergencyContact:
    await _lock_employee(db, user_id)
    count = len(await list_contacts(db, user_id, lock=True))
    if count >= MAX_CONTACTS:
        raise HTTPException(
            400, f"At most {MAX_CONTACTS} emergency contacts are allowed")
    c = EmployeeEmergencyContact(
        user_id=user_id, name=name.strip(), relation=relation.strip(),
        phone=validate_phone(phone), is_primary=False)
    db.add(c)
    await db.flush()
    # First contact is always primary.
    await _normalise_primary(db, user_id, c.id if (is_primary or count == 0) else None)
    return c


async def update_contact(
    db: AsyncSession, user_id: int, contact_id: int, changes: dict,
) -> EmployeeEmergencyContact:
    await _lock_employee(db, user_id)
    c = await db.get(EmployeeEmergencyContact, contact_id)
    if c is None or c.user_id != user_id:
        raise HTTPException(404, "Emergency contact not found")
    for k in ("name", "relation"):
        if changes.get(k) is not None:
            setattr(c, k, changes[k].strip())
    if changes.get("phone") is not None:
        c.phone = validate_phone(changes["phone"])
    if changes.get("is_primary") is True:
        await _normalise_primary(db, user_id, c.id)
    elif changes.get("is_primary") is False and c.is_primary:
        raise HTTPException(
            400, "Mark another contact as primary instead; one primary is required")
    await db.flush()
    return c


async def delete_contact(db: AsyncSession, user_id: int, contact_id: int) -> None:
    await _lock_employee(db, user_id)
    c = await db.get(EmployeeEmergencyContact, contact_id)
    if c is None or c.user_id != user_id:
        raise HTTPException(404, "Emergency contact not found")
    await db.delete(c)
    await db.flush()
    await _normalise_primary(db, user_id)


async def set_profile(db: AsyncSession, user_id: int, data: dict) -> Employee:
    emp = await employee_for_user(db, user_id)
    if "gender" in data:
        emp.gender = validate_gender(data["gender"])
    if "blood_group" in data:
        emp.blood_group = validate_blood_group(data["blood_group"])
    await db.flush()
    return emp


# ---- night-shift consent ----

def utc_today() -> date:
    """The single 'today' for consent logic (UTC, like the rest of the roster)."""
    return datetime.now(timezone.utc).date()


async def apply_refusal(db: AsyncSession, refusal: NightShiftConsent) -> None:
    """A recorded refusal (consent_given=False) supersedes earlier grants that
    overlap its window: a grant that started before it is end-dated to the day
    before the refusal's valid_from; one starting on/after it is withdrawn.
    (Overlapping rows are otherwise allowed; the highest id wins per date.)"""
    grants = (await db.execute(select(NightShiftConsent).where(
        NightShiftConsent.user_id == refusal.user_id,
        NightShiftConsent.consent_given.is_(True),
        NightShiftConsent.id != refusal.id).with_for_update())).scalars().all()
    for g in grants:
        overlaps = (g.valid_to is None or g.valid_to >= refusal.valid_from) and (
            refusal.valid_to is None or g.valid_from <= refusal.valid_to)
        if not overlaps:
            continue
        if g.valid_from < refusal.valid_from:
            g.valid_to = refusal.valid_from - timedelta(days=1)
        else:
            g.consent_given = False
    await db.flush()


def consent_dict(c: NightShiftConsent, today: Optional[date] = None) -> dict:
    today = today or utc_today()
    active = (c.consent_given and c.valid_from <= today
              and (c.valid_to is None or c.valid_to >= today))
    return {"id": c.id, "user_id": c.user_id, "consent_given": c.consent_given,
            "valid_from": c.valid_from, "valid_to": c.valid_to,
            "recorded_by_id": c.recorded_by_id, "document_url": c.document_url,
            "note": c.note, "created_at": c.created_at, "active": active}


async def consents_for_users(db: AsyncSession, user_ids: Iterable[int]) -> dict:
    ids = list(user_ids)
    out: dict = {}
    if not ids:
        return out
    for c in (await db.execute(select(NightShiftConsent).where(
            NightShiftConsent.user_id.in_(ids)))).scalars().all():
        out.setdefault(c.user_id, []).append(
            (c.id, c.consent_given, c.valid_from, c.valid_to))
    return out
