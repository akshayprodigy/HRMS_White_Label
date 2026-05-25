import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.user import User
from app.models.recruitment import (
    ManpowerRequisition, Applicant, Interview, 
    RequisitionStatus, RequisitionPriority, EmploymentType, ApplicantStatus
)
from app.core.config import settings

async def seed_recruitment():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # Get admin user
        result = await session.execute(select(User).where(User.email == "admin@example.com"))
        admin = result.scalars().first()
        if not admin:
            print("Admin user not found. Please run seed_demo_users first.")
            return

        # 1. Create Requisitions
        reqs_data = [
            {
                "req_id": "REQ-2026-0001",
                "title": "Senior Frontend Engineer (React)",
                "department": "Engineering",
                "positions_count": 2,
                "priority": RequisitionPriority.HIGH,
                "employment_type": EmploymentType.FULL_TIME,
                "job_description": "We are looking for a Senior React Developer to join our core team...",
                "status": RequisitionStatus.APPROVED,
                "creator_id": admin.id
            },
            {
                "req_id": "REQ-2026-0002",
                "title": "Product Manager",
                "department": "Product",
                "positions_count": 1,
                "priority": RequisitionPriority.MEDIUM,
                "employment_type": EmploymentType.FULL_TIME,
                "job_description": "Seeking an experienced PM to lead our new ERP modules...",
                "status": RequisitionStatus.PENDING,
                "creator_id": admin.id
            },
            {
                "req_id": "REQ-2026-0003",
                "title": "DevOps Intern",
                "department": "Infrastructure",
                "positions_count": 1,
                "priority": RequisitionPriority.LOW,
                "employment_type": EmploymentType.INTERN,
                "job_description": "AWS/Terraform enthusiasts wanted...",
                "status": RequisitionStatus.DRAFT,
                "creator_id": admin.id
            }
        ]

        created_reqs = []
        for data in reqs_data:
            # Check if exists
            res = await session.execute(select(ManpowerRequisition).where(ManpowerRequisition.req_id == data["req_id"]))
            if res.scalars().first():
                continue
            
            req = ManpowerRequisition(**data)
            session.add(req)
            created_reqs.append(req)
        
        await session.commit()
        print(f"Seeded {len(created_reqs)} Requisitions")

        # 2. Create Applicants for the approved requisition
        approved_req_res = await session.execute(
            select(ManpowerRequisition).where(ManpowerRequisition.req_id == "REQ-2026-0001")
        )
        approved_req = approved_req_res.scalars().first()

        if approved_req:
            applicants_data = [
                {
                    "first_name": "Robert",
                    "last_name": "Fox",
                    "email": "robert.fox@example.com",
                    "status": ApplicantStatus.SCREENING,
                    "source": "LinkedIn",
                    "experience_years": 5.5,
                    "requisition_id": approved_req.id
                },
                {
                    "first_name": "Guy",
                    "last_name": "Hawkins",
                    "email": "guy.hawkins@example.com",
                    "status": ApplicantStatus.INTERVIEW,
                    "source": "Referral",
                    "experience_years": 7.0,
                    "requisition_id": approved_req.id
                },
                {
                    "first_name": "Jane",
                    "last_name": "Cooper",
                    "email": "jane.cooper@example.com",
                    "status": ApplicantStatus.OFFERED,
                    "source": "Direct",
                    "experience_years": 4.0,
                    "requisition_id": approved_req.id
                },
                {
                    "first_name": "Eleanor",
                    "last_name": "Pena",
                    "email": "eleanor.pena@example.com",
                    "status": ApplicantStatus.HIRED,
                    "source": "LinkedIn",
                    "experience_years": 6.2,
                    "requisition_id": approved_req.id
                }
            ]

            for data in applicants_data:
                res = await session.execute(select(Applicant).where(Applicant.email == data["email"]))
                if res.scalars().first():
                    continue
                
                app = Applicant(**data)
                session.add(app)
                
                # If status is interview, add an interview entry
                if data["status"] == ApplicantStatus.INTERVIEW:
                    await session.flush()
                    interview = Interview(
                        applicant_id=app.id,
                        interview_type="technical",
                        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                        interviewer_id=admin.id,
                        notes="Guy has a strong background in AWS and React."
                    )
                    session.add(interview)

            await session.commit()
            print("Seeded Applicants and Interviews")

if __name__ == "__main__":
    asyncio.run(seed_recruitment())
