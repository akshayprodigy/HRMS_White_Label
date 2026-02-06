from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_audit, model_to_dict
from app.db.models.hr import Employee, EmployeeAsset, EmployeeDocument
from app.modules.hr.schemas import (
    EmployeeAssetCreate,
    EmployeeAssetUpdate,
    EmployeeCreate,
    EmployeeDocumentCreate,
    EmployeeUpdate,
)


def list_employees(db: Session) -> list[Employee]:
    stmt = select(Employee).order_by(Employee.id.desc())
    return list(db.execute(stmt).scalars().all())


def create_employee(db: Session, *, payload: EmployeeCreate) -> Employee:
    if payload.employee_code:
        stmt = select(Employee).where(
            Employee.employee_code == payload.employee_code
        )
        existing = db.execute(stmt).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Employee code exists")

    employee = Employee(
        employee_code=payload.employee_code,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone=payload.phone,
        date_of_birth=payload.date_of_birth,
        gender=payload.gender,
        address_line1=payload.address_line1,
        address_line2=payload.address_line2,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        country=payload.country,
        bank_name=payload.bank_name,
        bank_account_number=payload.bank_account_number,
        bank_ifsc=payload.bank_ifsc,
        bank_branch=payload.bank_branch,
        emergency_contact_name=payload.emergency_contact_name,
        emergency_contact_relation=payload.emergency_contact_relation,
        emergency_contact_phone=payload.emergency_contact_phone,
        employment_type=payload.employment_type,
        employment_status=payload.employment_status,
        joining_date=payload.joining_date,
        exit_date=payload.exit_date,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    log_audit(
        db,
        entity_type="employees",
        entity_id=str(employee.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(employee),
    )
    return employee


def update_employee(
    db: Session,
    *,
    employee: Employee,
    payload: EmployeeUpdate,
) -> Employee:
    before = model_to_dict(employee)

    if (
        payload.employee_code is not None
        and payload.employee_code != employee.employee_code
    ):
        if payload.employee_code:
            existing = db.execute(
                select(Employee).where(
                    Employee.employee_code == payload.employee_code,
                    Employee.id != employee.id,
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="Employee code exists",
                )
        employee.employee_code = payload.employee_code

    for field in (
        "first_name",
        "last_name",
        "email",
        "phone",
        "date_of_birth",
        "gender",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "bank_name",
        "bank_account_number",
        "bank_ifsc",
        "bank_branch",
        "emergency_contact_name",
        "emergency_contact_relation",
        "emergency_contact_phone",
        "employment_type",
        "employment_status",
        "joining_date",
        "exit_date",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(employee, field, value)

    db.add(employee)
    db.commit()
    db.refresh(employee)

    log_audit(
        db,
        entity_type="employees",
        entity_id=str(employee.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(employee),
    )
    return employee


def delete_employee(db: Session, *, employee: Employee) -> None:
    before = model_to_dict(employee)
    db.delete(employee)
    db.commit()

    log_audit(
        db,
        entity_type="employees",
        entity_id=str(employee.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_employee_documents(
    db: Session,
    *,
    employee_id: int,
) -> list[EmployeeDocument]:
    return list(
        db.execute(
            select(EmployeeDocument)
            .where(EmployeeDocument.employee_id == employee_id)
            .order_by(EmployeeDocument.id.desc())
        )
        .scalars()
        .all()
    )


def create_employee_document(
    db: Session,
    *,
    employee: Employee,
    payload: EmployeeDocumentCreate,
) -> EmployeeDocument:
    doc = EmployeeDocument(
        employee_id=employee.id,
        document_type=payload.document_type,
        title=payload.title,
        file_ref=payload.file_ref,
        mime_type=payload.mime_type,
        issued_on=payload.issued_on,
        expires_on=payload.expires_on,
        notes=payload.notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_audit(
        db,
        entity_type="employee_documents",
        entity_id=str(doc.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(doc),
    )
    return doc


def delete_employee_document(
    db: Session,
    *,
    employee_id: int,
    document: EmployeeDocument,
) -> None:
    if document.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Document not found")

    before = model_to_dict(document)
    db.delete(document)
    db.commit()

    log_audit(
        db,
        entity_type="employee_documents",
        entity_id=str(document.id),
        action="delete",
        before_json=before,
        after_json=None,
    )


def list_employee_assets(
    db: Session,
    *,
    employee_id: int,
) -> list[EmployeeAsset]:
    return list(
        db.execute(
            select(EmployeeAsset)
            .where(EmployeeAsset.employee_id == employee_id)
            .order_by(EmployeeAsset.id.desc())
        )
        .scalars()
        .all()
    )


def assign_employee_asset(
    db: Session,
    *,
    employee: Employee,
    payload: EmployeeAssetCreate,
) -> EmployeeAsset:
    asset = EmployeeAsset(
        employee_id=employee.id,
        asset_category=payload.asset_category,
        asset_name=payload.asset_name,
        asset_tag=payload.asset_tag,
        issued_on=payload.issued_on,
        returned_on=payload.returned_on,
        notes=payload.notes,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    log_audit(
        db,
        entity_type="employee_assets",
        entity_id=str(asset.id),
        action="create",
        before_json=None,
        after_json=model_to_dict(asset),
    )
    return asset


def update_employee_asset(
    db: Session,
    *,
    employee_id: int,
    asset: EmployeeAsset,
    payload: EmployeeAssetUpdate,
) -> EmployeeAsset:
    if asset.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    before = model_to_dict(asset)

    for field in (
        "asset_category",
        "asset_name",
        "asset_tag",
        "issued_on",
        "returned_on",
        "notes",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(asset, field, value)

    db.add(asset)
    db.commit()
    db.refresh(asset)

    log_audit(
        db,
        entity_type="employee_assets",
        entity_id=str(asset.id),
        action="update",
        before_json=before,
        after_json=model_to_dict(asset),
    )
    return asset


def delete_employee_asset(
    db: Session,
    *,
    employee_id: int,
    asset: EmployeeAsset,
) -> None:
    if asset.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Asset not found")

    before = model_to_dict(asset)
    db.delete(asset)
    db.commit()

    log_audit(
        db,
        entity_type="employee_assets",
        entity_id=str(asset.id),
        action="delete",
        before_json=before,
        after_json=None,
    )
