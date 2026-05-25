import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import SessionLocal
from app.models.recruitment import Applicant, ApplicantStatus
from app.models.onboarding import OnboardingProcess, OnboardingTask, OnboardingStatus
from sqlalchemy import select

async def seed_onboarding():
    async with SessionLocal() as db:
        # Get applicants with status INTERVIEW or OFFERED or HIRED
        # We'll just pick some who we haven't onboarded yet
        result = await db.execute(select(Applicant))
        applicants = result.scalars().all()
        
        for app in applicants:
            # Check if process already exists
            proc_result = await db.execute(select(OnboardingProcess).where(OnboardingProcess.applicant_id == app.id))
            if proc_result.scalar_one_or_none():
                continue
            
            # Create process
            proc = OnboardingProcess(
                applicant_id=app.id,
                status=OnboardingStatus.IN_PROGRESS,
                current_step=2
            )
            db.add(proc)
            await db.flush()
            
            # Create 6 tasks
            tasks = [
                ("Offer Accepted", "Candidate converted to employee registry.", 1, "System"),
                ("Document Collection", "KYC, Education & Bank detail verification.", 2, "Employee"),
                ("Internal Setup", "ID creation & organizational mapping.", 3, "HR Ops"),
                ("Asset Assignment", "Hardware & software license provisioning.", 4, "IT Support"),
                ("First Day Setup", "Reporting manager & attendance activation.", 5, "Manager"),
                ("Welcome Protocol", "Final welcome email & policy handbook.", 6, "HR Strategic"),
            ]
            
            for title, desc, step, actor in tasks:
                task = OnboardingTask(
                    process_id=proc.id,
                    step_number=step,
                    title=title,
                    description=desc,
                    actor_role=actor,
                    status=OnboardingStatus.COMPLETED if step < 2 else OnboardingStatus.PENDING
                )
                db.add(task)
        
        await db.commit()
    print("Onboarding data seeded.")

if __name__ == "__main__":
    asyncio.run(seed_onboarding())
