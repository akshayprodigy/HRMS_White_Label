from typing import Any, List
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.onboarding import OnboardingProcess, OnboardingTask, OnboardingStatus
from app.models.recruitment import Applicant, ApplicantStatus
from app.schemas.onboarding import (
    OnboardingProcessRead, OnboardingUpdate, OnboardingTaskUpdate, OnboardingCreate
)
from datetime import datetime, timezone

router = APIRouter()


@router.get("/ready")
async def get_ready_applicants(
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Return hired applicants who don't have an onboarding process yet."""
    # All applicant_ids already in onboarding
    existing_result = await db.execute(select(OnboardingProcess.applicant_id))
    onboarded_ids = {row[0] for row in existing_result.all()}

    result = await db.execute(
        select(Applicant)
        .where(Applicant.status == ApplicantStatus.HIRED)
        .options(selectinload(Applicant.requisition))
    )
    applicants = result.scalars().all()

    return [
        {
            "id": a.id,
            "full_name": a.full_name,
            "email": a.email,
            "role_title": a.requisition.title if a.requisition else "Unknown",
            "department": a.requisition.department if a.requisition else "Unknown",
        }
        for a in applicants
        if a.id not in onboarded_ids
    ]


@router.get("/", response_model=List[OnboardingProcessRead])
async def get_onboarding_processes(
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Get all active onboarding processes."""
    query = select(OnboardingProcess).options(
        selectinload(OnboardingProcess.tasks),
        selectinload(OnboardingProcess.applicant).selectinload(Applicant.requisition)
    )
    result = await db.execute(query)
    processes = result.scalars().all()
    
    # Map applicant details to process for UI
    output = []
    for p in processes:
        read = OnboardingProcessRead.model_validate(p)
        read.applicant_name = p.applicant.full_name
        read.role_title = p.applicant.requisition.title if p.applicant.requisition else "Unknown"
        read.department = p.applicant.requisition.department if p.applicant.requisition else "Unknown"
        output.append(read)
        
    return output

@router.post("/{process_id}/tasks/{task_id}/complete")
async def complete_onboarding_task(
    process_id: int,
    task_id: int,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Complete a specific onboarding task."""
    query = select(OnboardingTask).where(
        OnboardingTask.id == task_id,
        OnboardingTask.process_id == process_id
    )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task.status = OnboardingStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by_user_id = current_user.id
    
    # Update process current step if this was the current step
    process_query = select(OnboardingProcess).where(OnboardingProcess.id == process_id)
    process_result = await db.execute(process_query)
    process = process_result.scalar_one_or_none()
    
    if process and process.current_step == task.step_number:
        process.current_step += 1
        if process.current_step > 6:  # completed all 6 steps
            process.status = OnboardingStatus.COMPLETED
            process.completed_at = datetime.now(timezone.utc)
            
            # Also update applicant status to HIRED
            applicant_query = select(Applicant).where(Applicant.id == process.applicant_id)
            applicant_result = await db.execute(applicant_query)
            applicant = applicant_result.scalar_one_or_none()
            if applicant:
                applicant.status = "hired"
            
    await db.commit()
    return {"status": "success"}


ONBOARDING_TASKS = [
    ("Offer Accepted", "Candidate converted to employee registry.", 1, "System"),
    ("Document Collection", "KYC, Education & Bank detail verification.", 2, "Employee"),
    ("Internal Setup", "ID creation & organizational mapping.", 3, "HR Ops"),
    ("Asset Assignment", "Hardware & software license provisioning.", 4, "IT Support"),
    ("First Day Setup", "Reporting manager & attendance activation.", 5, "Manager"),
    ("Welcome Protocol", "Final welcome email & policy handbook.", 6, "HR Strategic"),
]


@router.post("/", response_model=OnboardingProcessRead)
async def initiate_onboarding(
    payload: OnboardingCreate,
    db: deps.DBDep,
    current_user: deps.CurrentUser
) -> Any:
    """Initiate a new onboarding process for an applicant."""
    # Verify applicant exists
    applicant_result = await db.execute(
        select(Applicant).where(Applicant.id == payload.applicant_id)
    )
    applicant = applicant_result.scalar_one_or_none()
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    # Check for existing process
    existing = await db.execute(
        select(OnboardingProcess).where(OnboardingProcess.applicant_id == payload.applicant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Onboarding process already exists for this applicant")

    # Create process
    process = OnboardingProcess(
        applicant_id=payload.applicant_id,
        status=OnboardingStatus.IN_PROGRESS,
        current_step=1
    )
    db.add(process)
    await db.flush()

    # Create 6 standard tasks
    for title, desc, step, actor in ONBOARDING_TASKS:
        task = OnboardingTask(
            process_id=process.id,
            step_number=step,
            title=title,
            description=desc,
            actor_role=actor,
            status=OnboardingStatus.IN_PROGRESS if step == 1 else OnboardingStatus.PENDING
        )
        db.add(task)

    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(OnboardingProcess)
        .where(OnboardingProcess.id == process.id)
        .options(
            selectinload(OnboardingProcess.tasks),
            selectinload(OnboardingProcess.applicant).selectinload(Applicant.requisition)
        )
    )
    process = result.scalar_one()

    read = OnboardingProcessRead.model_validate(process)
    read.applicant_name = process.applicant.full_name
    read.role_title = process.applicant.requisition.title if process.applicant.requisition else "Unknown"
    read.department = process.applicant.requisition.department if process.applicant.requisition else "Unknown"
    return read
