from typing import Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.audit import AuditLog
from app.models.recruitment import (
    ManpowerRequisition, RequisitionStatus, Applicant, ApplicantStatus, Interview
)
from app.models.user import User, Role
from app.models.approval import ApprovalItem, ApprovalStep, ApprovalStatus
from app.schemas.recruitment import (
    RequisitionRead, RequisitionCreate, RequisitionUpdate,
    RequisitionWithApplicants,
    ApplicantRead, ApplicantCreate, ApplicantWithInterviews,
    InterviewRead, InterviewCreate
)

router = APIRouter()

RECRUITMENT_READ = "recruitment read"
RECRUITMENT_WRITE = "recruitment write"
RECRUITMENT_APPROVE = "recruitment approve"


@router.post("/", response_model=RequisitionRead)
async def create_requisition(
    *,
    db: deps.DBDep,
    req_in: RequisitionCreate,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_WRITE]))
) -> Any:
    # 1. Generate unique request ID
    count_query = await db.execute(select(func.count(ManpowerRequisition.id)))
    count = count_query.scalar() or 0
    req_id = f"REQ-{datetime.now().year}-{count + 1:04d}"

    # 2. Create requisition in draft
    db_req = ManpowerRequisition(
        **req_in.model_dump(),
        req_id=req_id,
        creator_id=current_user.id,
        status=RequisitionStatus.DRAFT
    )
    db.add(db_req)
    await db.commit()
    await db.refresh(db_req)
    return db_req


@router.post("/{id}/submit", response_model=RequisitionRead)
async def submit_requisition(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_WRITE]))
) -> Any:
    req = await db.get(ManpowerRequisition, id)
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
    
    if req.status != RequisitionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft requisitions can be submitted")

    # Initiate multi-level approval flow
    # Step 1: HR Approval
    # Step 2: CEO Approval (if high priority or large headcount)
    
    hr_role_query = await db.execute(select(Role).where(Role.name == "HR"))
    hr_role = hr_role_query.scalar_one_or_none()
    
    ceo_role_query = await db.execute(select(Role).where(Role.name == "CEO"))
    ceo_role = ceo_role_query.scalar_one_or_none()

    approval_item = ApprovalItem(
        resource_type="requisition",
        resource_id=str(req.id),
        status=ApprovalStatus.PENDING,
        requested_by_id=current_user.id
    )
    db.add(approval_item)
    await db.flush()

    # Step 1: HR
    db.add(ApprovalStep(
        approval_item_id=approval_item.id,
        step_number=1,
        role_id=hr_role.id if hr_role else None,
        status=ApprovalStatus.PENDING
    ))

    # Step 2: CEO (if urgent or > 3 positions)
    if req.priority == "urgent" or req.positions_count > 3:
        db.add(ApprovalStep(
            approval_item_id=approval_item.id,
            step_number=2,
            role_id=ceo_role.id if ceo_role else None,
            status=ApprovalStatus.PENDING
        ))

    req.status = RequisitionStatus.PENDING
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        action="submit_requisition",
        resource_type="requisition",
        resource_id=str(req.id),
        details={"req_id": req.req_id}
    )
    db.add(audit)
    
    await db.commit()
    await db.refresh(req)
    return req


@router.get("/", response_model=List[RequisitionRead])
async def list_requisitions(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_READ])),
    status: Optional[RequisitionStatus] = None
) -> Any:
    query = select(ManpowerRequisition)
    
    # Non-HR/Admin users only see their own or their department's if we had department mapping
    # For now, let's allow read permission holders to see all if they are Recruiter/CEO/HR
    # Else filter by creator
    
    user_roles = [r.name for r in current_user.roles]
    if "HR" not in user_roles and "CEO" not in user_roles and "RECRUITER" not in user_roles and "Super Admin" not in user_roles:
        query = query.where(ManpowerRequisition.creator_id == current_user.id)
        
    if status:
        query = query.where(ManpowerRequisition.status == status)
        
    result = await db.execute(query.order_by(ManpowerRequisition.created_at.desc()))
    return result.scalars().all()


# NOTE: the :int converter keeps this catch-all from swallowing the
# literal /applicants and /interviews routes declared below it —
# without it, GET /recruitment/applicants 422s ("applicants" as id).
@router.get("/{id:int}", response_model=RequisitionRead)
async def get_requisition(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_READ]))
) -> Any:
    req = await db.get(ManpowerRequisition, id)
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
    return req


# Applicant Endpoints

@router.post("/applicants", response_model=ApplicantRead)
async def create_applicant(
    *,
    db: deps.DBDep,
    applicant_in: ApplicantCreate,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_WRITE]))
) -> Any:
    # Verify requisition exists and is approved
    req = await db.get(ManpowerRequisition, applicant_in.requisition_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
    if req.status != RequisitionStatus.APPROVED:
        raise HTTPException(
            status_code=400, 
            detail="Cannot add applicants to non-approved requisition"
        )
    
    db_applicant = Applicant(
        **applicant_in.model_dump(),
        status=ApplicantStatus.APPLIED
    )
    db.add(db_applicant)
    await db.commit()
    await db.refresh(db_applicant)
    return db_applicant


@router.get("/applicants", response_model=List[ApplicantWithInterviews])
async def list_applicants(
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_READ]))
) -> Any:
    """Return all applicants with their interviews."""
    result = await db.execute(
        select(Applicant).options(selectinload(Applicant.interviews))
    )
    return result.scalars().all()


@router.get("/applicants/{id}", response_model=ApplicantRead)
async def get_applicant(
    id: int,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_READ]))
) -> Any:
    query = select(Applicant).where(Applicant.id == id).options(
        selectinload(Applicant.interviews)
    )
    result = await db.execute(query)
    applicant = result.scalar_one_or_none()
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return applicant


@router.patch("/applicants/{id}/status", response_model=ApplicantRead)
async def update_applicant_status(
    id: int,
    status: ApplicantStatus,
    db: deps.DBDep,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_WRITE]))
) -> Any:
    applicant = await db.get(Applicant, id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    
    applicant.status = status
    await db.commit()
    await db.refresh(applicant)
    return applicant


# Interview Endpoints

@router.post("/interviews", response_model=InterviewRead)
async def schedule_interview(
    *,
    db: deps.DBDep,
    interview_in: InterviewCreate,
    current_user: User = Depends(deps.check_permissions([RECRUITMENT_WRITE]))
) -> Any:
    applicant = await db.get(Applicant, interview_in.applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    
    db_interview = Interview(
        **interview_in.model_dump(),
        status="scheduled"
    )
    db.add(db_interview)
    
    # Update applicant status to interview
    applicant.status = ApplicantStatus.INTERVIEW
    
    await db.commit()
    await db.refresh(db_interview)
    return db_interview
