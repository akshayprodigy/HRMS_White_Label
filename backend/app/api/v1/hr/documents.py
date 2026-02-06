from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.database import get_db
from app.db.models.hr import Employee, EmployeeDocument
from app.modules.hr.schemas import (
    EmployeeDocumentCreate,
    EmployeeDocumentPublic,
)
from app.modules.hr.service import (
    create_employee_document,
    delete_employee_document,
    list_employee_documents,
)

router = APIRouter(prefix="/employees/{employee_id}/documents")

_ERR_EMPLOYEE_NOT_FOUND = "Employee not found"


@router.get(
    "",
    response_model=list[EmployeeDocumentPublic],
    dependencies=[
        Depends(require_permissions({"hr.employee_documents.read"})),
    ],
)
def hr_list_employee_documents(
    employee_id: int,
    db: Session = Depends(get_db),
) -> list[EmployeeDocumentPublic]:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    docs = list_employee_documents(db, employee_id=employee_id)
    return [EmployeeDocumentPublic.model_validate(d) for d in docs]


@router.post(
    "",
    response_model=EmployeeDocumentPublic,
    dependencies=[
        Depends(require_permissions({"hr.employee_documents.write"})),
    ],
)
def hr_create_employee_document(
    employee_id: int,
    payload: EmployeeDocumentCreate,
    db: Session = Depends(get_db),
) -> EmployeeDocumentPublic:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    doc = create_employee_document(db, employee=employee, payload=payload)
    return EmployeeDocumentPublic.model_validate(doc)


@router.delete(
    "/{document_id}",
    dependencies=[
        Depends(require_permissions({"hr.employee_documents.write"})),
    ],
)
def hr_delete_employee_document(
    employee_id: int,
    document_id: int,
    db: Session = Depends(get_db),
) -> dict:
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail=_ERR_EMPLOYEE_NOT_FOUND)

    doc = db.get(EmployeeDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_employee_document(db, employee_id=employee_id, document=doc)
    return {"status": "ok"}
