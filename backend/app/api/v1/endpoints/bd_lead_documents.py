from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_, select

from app.api import deps
from app.core.config import settings
from app.models.audit import AuditLog
from app.models.bd import EstimatePhase, EstimateVersion, Lead, LeadDocument
from app.models.bid_task import LeadBidTask, LeadBidTaskAssignment
from app.models.user import User
from app.schemas.bd import LeadDocumentRead

router = APIRouter()

BD_LEAD_READ = "bd lead read"
BD_LEAD_WRITE = "bd lead write"
LEAD_NOT_FOUND = "Lead not found"


def _err(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


async def _get_subordinate_ids(db: deps.DBDep, manager_id: int) -> List[int]:
    result = await db.execute(
        select(User.id).where(User.manager_id == manager_id)
    )
    return list(result.scalars().all())


async def _user_can_access_lead(
    db: deps.DBDep, current_user: User, lead: Lead
) -> bool:
    if current_user.is_superuser:
        return True

    subordinate_ids = await _get_subordinate_ids(db, current_user.id)
    if lead.owner_user_id == current_user.id:
        return True
    if subordinate_ids and lead.owner_user_id in subordinate_ids:
        return True

    assigned_check = await db.execute(
        select(EstimatePhase.id)
        .join(EstimateVersion, EstimatePhase.version_id == EstimateVersion.id)
        .where(
            and_(
                EstimateVersion.lead_id == lead.id,
                EstimatePhase.assigned_user_id == current_user.id,
            )
        )
        .limit(1)
    )
    if assigned_check.scalar_one_or_none() is not None:
        return True

    bid_task_assigned = await db.execute(
        select(LeadBidTaskAssignment.id)
        .join(LeadBidTask, LeadBidTaskAssignment.bid_task_id == LeadBidTask.id)
        .where(
            and_(
                LeadBidTask.lead_id == lead.id,
                LeadBidTaskAssignment.pm_user_id == current_user.id,
            )
        )
        .limit(1)
    )
    return bid_task_assigned.scalar_one_or_none() is not None


def _safe_filename(name: str) -> str:
    name = (name or "").strip().replace("\x00", "")
    # Avoid path traversal and weird separators.
    name = name.replace("/", "_").replace("\\", "_")
    if not name:
        return "upload.bin"
    return name[:200]


def _base_dir() -> Path:
    return Path(settings.LEAD_DOCUMENTS_DIR)


def _abs_path(storage_path: str) -> Path:
    base = _base_dir().resolve()
    target = (base / storage_path).resolve()
    if base not in target.parents and base != target:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "INVALID_STORAGE_PATH",
                "Invalid document storage path",
            ),
        )
    return target


def _as_read(doc: LeadDocument) -> LeadDocumentRead:
    out = LeadDocumentRead.model_validate(doc, from_attributes=True)
    out.download_url = (
        f"/api/v1/bd/leads/{doc.lead_id}/documents/{doc.id}/download"
    )
    return out


@router.get(
    "/leads/{lead_id}/documents",
    response_model=List[LeadDocumentRead],
)
async def list_lead_documents(
    lead_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_LEAD_READ]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "LEAD_NOT_FOUND",
                LEAD_NOT_FOUND,
                {"lead_id": lead_id},
            ),
        )

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(
            status_code=403,
            detail=_err(
                "FORBIDDEN",
                "Not authorized to view this lead",
                {"lead_id": lead_id},
            ),
        )

    q = (
        select(LeadDocument)
        .where(LeadDocument.lead_id == lead_id)
        .order_by(LeadDocument.uploaded_at.desc(), LeadDocument.id.desc())
    )
    res = await db.execute(q)
    docs = res.scalars().all()
    return [_as_read(d) for d in docs]


@router.post(
    "/leads/{lead_id}/documents",
    response_model=List[LeadDocumentRead],
)
async def upload_lead_documents(
    lead_id: int,
    db: deps.DBDep,
    files: Annotated[List[UploadFile], File(...)],
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_LEAD_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "LEAD_NOT_FOUND",
                LEAD_NOT_FOUND,
                {"lead_id": lead_id},
            ),
        )

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(
            status_code=403,
            detail=_err(
                "FORBIDDEN",
                "Not authorized to update this lead",
                {"lead_id": lead_id},
            ),
        )

    if not files:
        raise HTTPException(
            status_code=400,
            detail=_err(
                "VALIDATION_ERROR",
                "At least one file is required",
            ),
        )

    base = _base_dir()
    lead_dir = base / str(lead_id)
    lead_dir.mkdir(parents=True, exist_ok=True)

    created_docs: list[LeadDocument] = []
    written_paths: list[Path] = []

    try:
        for upload in files:
            filename = _safe_filename(upload.filename or "")
            stored_name = f"{uuid4().hex}_{filename}"
            storage_path = f"{lead_id}/{stored_name}"
            dest = _abs_path(storage_path)

            max_bytes = int(settings.LEAD_DOCUMENT_MAX_BYTES)
            total = 0

            with dest.open("wb") as f:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=_err(
                                "FILE_TOO_LARGE",
                                "File exceeds maximum size",
                                {
                                    "file_name": filename,
                                    "max_bytes": max_bytes,
                                },
                            ),
                        )
                    f.write(chunk)

            written_paths.append(dest)

            doc = LeadDocument(
                lead_id=lead_id,
                file_name=filename,
                storage_path=storage_path,
                mime_type=upload.content_type or "application/octet-stream",
                file_size=total,
                uploader_id=current_user.id,
            )
            db.add(doc)
            created_docs.append(doc)

        await db.flush()

        audit = AuditLog(
            user_id=current_user.id,
            action="bd.lead_document.upload",
            resource_type="lead",
            resource_id=str(lead.lead_id),
            details={
                "lead_id": lead_id,
                "document_ids": [d.id for d in created_docs],
                "files": [
                    {
                        "file_name": d.file_name,
                        "mime_type": d.mime_type,
                        "file_size": d.file_size,
                    }
                    for d in created_docs
                ],
            },
        )
        db.add(audit)

        await db.commit()

        # Reload created docs for response
        ids = [d.id for d in created_docs]
        q = select(LeadDocument).where(LeadDocument.id.in_(ids))
        res = await db.execute(q)
        docs = res.scalars().all()
        return [_as_read(d) for d in docs]

    except Exception:
        # Cleanup any files written if DB commit fails.
        for p in written_paths:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        raise


@router.get("/leads/{lead_id}/documents/{doc_id}/download")
async def download_lead_document(
    lead_id: int,
    doc_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_LEAD_READ]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "LEAD_NOT_FOUND",
                LEAD_NOT_FOUND,
                {"lead_id": lead_id},
            ),
        )

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(
            status_code=403,
            detail=_err(
                "FORBIDDEN",
                "Not authorized to view this lead",
                {"lead_id": lead_id},
            ),
        )

    q = select(LeadDocument).where(
        and_(LeadDocument.id == doc_id, LeadDocument.lead_id == lead_id)
    )
    res = await db.execute(q)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "DOCUMENT_NOT_FOUND",
                "Document not found",
                {"lead_id": lead_id, "doc_id": doc_id},
            ),
        )

    abs_path = _abs_path(doc.storage_path)
    if not abs_path.exists():
        raise HTTPException(
            status_code=404,
            detail=_err(
                "DOCUMENT_MISSING",
                "Document file missing on server",
                {"lead_id": lead_id, "doc_id": doc_id},
            ),
        )

    audit = AuditLog(
        user_id=current_user.id,
        action="bd.lead_document.download",
        resource_type="lead_document",
        resource_id=str(doc.id),
        details={
            "lead_id": lead_id,
            "doc_id": doc_id,
            "file_name": doc.file_name,
        },
    )
    db.add(audit)
    await db.commit()

    return FileResponse(
        path=str(abs_path),
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.file_name,
    )


@router.delete("/leads/{lead_id}/documents/{doc_id}")
async def delete_lead_document(
    lead_id: int,
    doc_id: int,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([BD_LEAD_WRITE]))
    ],
) -> Any:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "LEAD_NOT_FOUND",
                LEAD_NOT_FOUND,
                {"lead_id": lead_id},
            ),
        )

    if not await _user_can_access_lead(db, current_user, lead):
        raise HTTPException(
            status_code=403,
            detail=_err(
                "FORBIDDEN",
                "Not authorized to update this lead",
                {"lead_id": lead_id},
            ),
        )

    q = select(LeadDocument).where(
        and_(LeadDocument.id == doc_id, LeadDocument.lead_id == lead_id)
    )
    res = await db.execute(q)
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=_err(
                "DOCUMENT_NOT_FOUND",
                "Document not found",
                {"lead_id": lead_id, "doc_id": doc_id},
            ),
        )

    abs_path = _abs_path(doc.storage_path)
    try:
        abs_path.unlink(missing_ok=True)
    except Exception:
        pass

    await db.delete(doc)

    audit = AuditLog(
        user_id=current_user.id,
        action="bd.lead_document.delete",
        resource_type="lead_document",
        resource_id=str(doc.id),
        details={
            "lead_id": lead_id,
            "doc_id": doc_id,
            "file_name": doc.file_name,
        },
    )
    db.add(audit)

    await db.commit()
    return {"ok": True}
