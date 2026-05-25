import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.project import Project, ProjectMember
from app.models.task import Task, Subtask, TaskComment
from app.models.user import User, Role, Permission
from app.models.attendance import Attendance
from app.models.timesheet import TimeEntry, TimerSession
from app.models.leave import LeaveRequest, LeaveType, LeaveBalanceLedger
from app.models.approval import ApprovalItem, ApprovalStep
from app.core.config import settings
from datetime import datetime, timedelta, timezone


async def seed_tasks():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        # Get users
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == "admin@gmail.com")
        )
        user = result.scalars().first()
        if not user:
            print("User admin@gmail.com not found. Run seed_demo_users.py.")
            return

        employee_result = await session.execute(
            select(User).where(User.email == "employee@gmail.com")
        )
        employee_user = employee_result.scalars().first()
        if not employee_user:
            print(
                "User employee@gmail.com not found; skipping e2e task seed."
            )

        # Create Project
        result = await session.execute(
            select(Project).where(Project.code == "PRJ001")
        )
        project1 = result.scalars().first()
        if not project1:
            project1 = Project(
                name="Q1 Financial Compliance",
                code="PRJ001",
                description="Operational deliverables for Q1 compliance.",
                status="active"
            )
            session.add(project1)
            await session.flush()

        # Add member
        result = await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project1.id,
                ProjectMember.user_id == user.id
            )
        )
        if not result.scalars().first():
            member1 = ProjectMember(
                project_id=project1.id, user_id=user.id, role="lead"
            )
            session.add(member1)

        if employee_user:
            result = await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project1.id,
                    ProjectMember.user_id == employee_user.id,
                )
            )
            if not result.scalars().first():
                session.add(
                    ProjectMember(
                        project_id=project1.id,
                        user_id=employee_user.id,
                        role="member",
                    )
                )

        # Create Tasks
        result = await session.execute(
            select(Task).where(
                Task.project_id == project1.id,
                Task.title == "Update Tax Calculation Logic",
            )
        )
        task1 = result.scalars().first()
        if not task1:
            task1 = Task(
                project_id=project1.id,
                title="Update Tax Calculation Logic",
                description="Implement changes for regional tax brackets.",
                status="in_progress",
                priority="high",
                due_date=datetime.now(timezone.utc) + timedelta(days=7),
                creator_id=user.id,
                assignee_id=user.id
            )
            session.add(task1)
            await session.flush()

        if employee_user:
            result = await session.execute(
                select(Task).where(
                    Task.project_id == project1.id,
                    Task.title == "E2E: Assigned Task Timer",
                )
            )
            employee_task = result.scalars().first()
            if not employee_task:
                employee_task = Task(
                    project_id=project1.id,
                    title="E2E: Assigned Task Timer",
                    description=(
                        "Seeded task to validate timer sync"
                    ),
                    status="pending",
                    priority="medium",
                    due_date=datetime.now(timezone.utc) + timedelta(days=3),
                    creator_id=user.id,
                    assignee_id=employee_user.id,
                )
                session.add(employee_task)

        # Create Subtasks
        result = await session.execute(
            select(Subtask).where(Subtask.task_id == task1.id)
        )
        if not result.scalars().first():
            subtasks = [
                Subtask(
                    task_id=task1.id, title="Review docs", is_completed=True
                ),
                Subtask(
                    task_id=task1.id, title="Update Python", is_completed=False
                ),
                Subtask(
                    task_id=task1.id,
                    title="Verify with QA",
                    is_completed=False
                )
            ]
            session.add_all(subtasks)

        # Create Comment
        comment_text = "Initial documentation review complete."
        result = await session.execute(
            select(TaskComment).where(
                TaskComment.task_id == task1.id,
                TaskComment.content == comment_text,
            )
        )
        if not result.scalars().first():
            comment = TaskComment(
                task_id=task1.id,
                user_id=user.id,
                content=comment_text
            )
            session.add(comment)

        # Another Project
        result = await session.execute(
            select(Project).where(Project.code == "PRJ002")
        )
        project2 = result.scalars().first()
        if not project2:
            project2 = Project(
                name="HR System Migration",
                code="PRJ002",
                description="Migrating legacy data to the new ERP core.",
                status="active"
            )
            session.add(project2)
            await session.flush()

        result = await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project2.id,
                ProjectMember.user_id == user.id
            )
        )
        if not result.scalars().first():
            member2 = ProjectMember(
                project_id=project2.id, user_id=user.id, role="member"
            )
            session.add(member2)

        if employee_user:
            result = await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project2.id,
                    ProjectMember.user_id == employee_user.id,
                )
            )
            if not result.scalars().first():
                session.add(
                    ProjectMember(
                        project_id=project2.id,
                        user_id=employee_user.id,
                        role="member",
                    )
                )

        result = await session.execute(
            select(Task).where(
                Task.project_id == project2.id,
                Task.title == "Map Employee Salary Histories",
            )
        )
        task2 = result.scalars().first()
        if not task2:
            task2 = Task(
                project_id=project2.id,
                title="Map Employee Salary Histories",
                description="Ensure historical data is correctly mapped.",
                status="pending",
                priority="medium",
                due_date=datetime.now(timezone.utc) + timedelta(days=14),
                creator_id=user.id,
                assignee_id=user.id,
            )
            session.add(task2)

        await session.commit()
        print("Successfully seeded projects and tasks.")

if __name__ == "__main__":
    asyncio.run(seed_tasks())
