"""Asset register models (Roadmap v2 Phase 5, Task 1). DB-backed; cleans up."""
import uuid
from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.asset import (
    Asset, AssetCategory, AssetMaintenance, AssetRequest, AssetRequestStatus,
    AssetStatus,
)
from app.models.employee import Employee, EmployeeStatus
from app.models.employee_asset import EmployeeAsset
from app.models.user import User


async def test_asset_models_and_uniqueness():
    sfx = uuid.uuid4().hex[:8]
    code = f"T{sfx[:5]}".upper()
    user_id = emp_id = cat_id = asset_id = None
    try:
        async with SessionLocal() as db:
            u = User(email=f"asset_{sfx}@test.com", full_name="Asset T",
                     hashed_password=get_password_hash("x"), is_active=True)
            db.add(u)
            await db.commit()
            user_id = u.id
            e = Employee(user_id=user_id, employee_id=f"AS{sfx}",
                         department="QA", designation="Tester", date_of_joining=date(2020, 1, 1),
                         status=EmployeeStatus.ACTIVE)
            cat = AssetCategory(name=f"Cat {sfx}", code=code)
            db.add_all([e, cat])
            await db.commit()
            emp_id, cat_id = e.id, cat.id

            a = Asset(asset_tag=f"{code}-000001", category_id=cat_id,
                      name="Test laptop", status=AssetStatus.ALLOCATED,
                      purchase_cost_paise=5500000, created_by_id=user_id)
            db.add(a)
            await db.commit()
            asset_id = a.id
            assert a.salvage_value_paise == 0

            db.add(AssetMaintenance(asset_id=asset_id, kind="repair",
                                    description="screen", cost_paise=1000,
                                    started_on=date.today()))
            alloc = EmployeeAsset(
                employee_id=emp_id, asset_type="Laptop", model="Test laptop",
                asset_id=asset_id, allocated_by_id=user_id)
            db.add(alloc)
            await db.commit()
            db.add(AssetRequest(
                employee_id=emp_id, category_id=cat_id, reason="need",
                fulfilled_asset_id=asset_id, allocation_id=alloc.id))
            await db.commit()

        async with SessionLocal() as db:
            a = (await db.execute(
                select(Asset).where(Asset.id == asset_id).options(
                    selectinload(Asset.category),
                    selectinload(Asset.allocations),
                    selectinload(Asset.maintenance)))).scalar_one()
            assert a.category.code == code
            assert len(a.allocations) == 1
            assert a.allocations[0].allocated_by_id == user_id
            assert len(a.maintenance) == 1
            r = (await db.execute(select(AssetRequest).where(
                AssetRequest.employee_id == emp_id))).scalar_one()
            assert r.status == AssetRequestStatus.PENDING

            db.add(Asset(asset_tag=f"{code}-000001", category_id=cat_id,
                         name="dup"))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
            db.add(AssetCategory(name=f"Other {sfx}", code=code))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        async with SessionLocal() as db:
            if emp_id:
                await db.execute(delete(AssetRequest).where(
                    AssetRequest.employee_id == emp_id))
                await db.execute(delete(EmployeeAsset).where(
                    EmployeeAsset.employee_id == emp_id))
            if asset_id:
                await db.execute(delete(Asset).where(Asset.id == asset_id))
            if cat_id:
                await db.execute(delete(AssetCategory).where(
                    AssetCategory.id == cat_id))
            if emp_id:
                await db.execute(delete(Employee).where(Employee.id == emp_id))
            if user_id:
                await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
