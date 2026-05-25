from typing import Any, Optional, List, Annotated
import io
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
import pandas as pd

from app.api import deps
from app.models.bd import Account, ClientDetails
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.bd import (
    AccountRead,
    AccountCreate,
    AccountUpdate,
    ClientDetailsRead,
    ClientDetailsUpdate,
)

logger = logging.getLogger(__name__)

# Template column names
COL_CLIENT_NAME = "Client Name"
COL_DOMAIN = "Domain"
COL_INDUSTRY = "Industry"
COL_ADDRESS = "Address"
COL_EMAIL = "Email"
COL_WEBSITE = "Website"
COL_CONTACT_NAME = "Contact Person Name"
COL_CONTACT_PHONE = "Contact Person Phone"
COL_CONTACT_EMAIL = "Contact Person Email"
COL_GST = "GST Number"

TEMPLATE_COLUMNS = [
    COL_CLIENT_NAME, COL_DOMAIN, COL_INDUSTRY, COL_ADDRESS,
    COL_EMAIL, COL_WEBSITE, COL_CONTACT_NAME, COL_CONTACT_PHONE,
    COL_CONTACT_EMAIL, COL_GST,
]

# Example names used in the template — skip during upload
EXAMPLE_CLIENT_NAMES = {"acme corp", "techstart inc"}

EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)
GST_RE = re.compile(
    r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$"
)


CLIENT_READ = "client read"
CLIENT_CREATE = "client create"
CLIENT_WRITE = "client write"

router = APIRouter()


def _client_not_found_exc(client_id: int) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "CLIENT_NOT_FOUND",
                "message": "Client not found",
                "details": {"client_id": client_id},
            }
        },
    )


def _serialize_client_details(
    account: Account,
    details: Optional[ClientDetails],
) -> dict:
    return {
        "account_id": account.id,
        "name": account.name,
        "domain": account.domain,
        "industry": account.industry,
        "address": getattr(details, "address", None),
        "email": getattr(details, "email", None),
        "website": getattr(details, "website", None),
        "contact_person_name": getattr(details, "contact_person_name", None),
        "contact_person_phone": getattr(details, "contact_person_phone", None),
        "contact_person_email": getattr(details, "contact_person_email", None),
        "gst_number": getattr(details, "gst_number", None),
        "created_at": getattr(details, "created_at", None),
        "updated_at": getattr(details, "updated_at", None),
    }


async def _get_client_details(
    db: deps.DBDep,
    client_id: int,
) -> Optional[ClientDetails]:
    details_result = await db.execute(
        select(ClientDetails)
        .where(ClientDetails.account_id == client_id)
        .limit(1)
    )
    return details_result.scalar_one_or_none()


async def _ensure_unique_client_name(
    db: deps.DBDep,
    *,
    client_id: int,
    name: str,
) -> None:
    dup_result = await db.execute(
        select(Account.id)
        .where(func.lower(Account.name) == name.lower())
        .where(Account.id != client_id)
        .limit(1)
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "CLIENT_NAME_DUPLICATE",
                    "message": "Client name already exists",
                    "details": {"name": name},
                }
            },
        )


def _build_clients_search_query(q: Optional[str]):
    query = select(Account)
    if q:
        q_normalized = q.strip().lower()
        if q_normalized:
            like = f"%{q_normalized}%"
            query = query.where(
                func.lower(Account.name).like(like)
                | func.lower(func.coalesce(Account.domain, "")).like(like)
                | func.lower(func.coalesce(Account.industry, "")).like(like)
            )
    return query


@router.get("/", response_model=List[AccountRead])
async def list_clients(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
    q: Annotated[
        Optional[str], Query(description="Search by name/domain")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    query = _build_clients_search_query(q)
    query = query.order_by(Account.name.asc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/page")
async def list_clients_paginated(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
    q: Annotated[
        Optional[str], Query(description="Search by name/domain/industry")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    base = _build_clients_search_query(q)
    total = (
        await db.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()

    page_query = (
        base.order_by(Account.name.asc()).limit(limit).offset(offset)
    )
    items = (await db.execute(page_query)).scalars().all()

    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "domain": a.domain,
                "industry": a.industry,
            }
            for a in items
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/",
    response_model=AccountRead,
    responses={
        400: {"description": "Validation error"},
    },
)
async def create_client(
    *,
    db: deps.DBDep,
    client_in: AccountCreate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_CREATE]))
    ],
) -> Any:
    name = client_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")

    existing_result = await db.execute(
        select(Account)
        .where(func.lower(Account.name) == name.lower())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Idempotent behavior: update known fields if provided.
        updated = False
        if (
            client_in.domain is not None
            and client_in.domain != existing.domain
        ):
            existing.domain = client_in.domain
            updated = True
        if (
            client_in.industry is not None
            and client_in.industry != existing.industry
        ):
            existing.industry = client_in.industry
            updated = True

        if updated:
            audit = AuditLog(
                user_id=current_user.id,
                action="update_client",
                resource_type="client",
                resource_id=str(existing.id),
                details={
                    "name": existing.name,
                    "domain": existing.domain,
                    "industry": existing.industry,
                },
            )
            db.add(audit)

            await db.commit()
            await db.refresh(existing)
        return existing

    db_obj = Account(
        name=name,
        domain=client_in.domain,
        industry=client_in.industry,
    )
    db.add(db_obj)
    await db.flush()  # Get db_obj.id for ClientDetails FK + audit

    # Optional detail fields. Write a single ClientDetails row in the same
    # transaction so create-then-PATCH cannot leave a half-populated client.
    detail_payload = {
        "address": client_in.address,
        "email": client_in.email,
        "website": client_in.website,
        "contact_person_name": client_in.contact_person_name,
        "contact_person_phone": client_in.contact_person_phone,
        "contact_person_email": client_in.contact_person_email,
        "gst_number": client_in.gst_number,
    }
    has_details = any(
        v is not None and str(v).strip() != "" for v in detail_payload.values()
    )
    if has_details:
        details = ClientDetails(account_id=db_obj.id)
        for key, value in detail_payload.items():
            if value is not None:
                setattr(details, key, value)
        db.add(details)

    audit = AuditLog(
        user_id=current_user.id,
        action="create_client",
        resource_type="client",
        resource_id=str(db_obj.id),
        details={
            "name": name,
            "domain": client_in.domain,
            "industry": client_in.industry,
            "with_details": has_details,
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(db_obj)

    return db_obj


@router.get("/template")
async def download_client_template(
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
) -> StreamingResponse:
    example_rows = [
        {
            COL_CLIENT_NAME: "Acme Corp",
            COL_DOMAIN: "acmecorp.com",
            COL_INDUSTRY: "Manufacturing",
            COL_ADDRESS: "123 Main St, Mumbai",
            COL_EMAIL: "info@acmecorp.com",
            COL_WEBSITE: "https://acmecorp.com",
            COL_CONTACT_NAME: "John Doe",
            COL_CONTACT_PHONE: "+91 9876543210",
            COL_CONTACT_EMAIL: "john@acmecorp.com",
            COL_GST: "27AABCU9603R1ZM",
        },
        {
            COL_CLIENT_NAME: "TechStart Inc",
            COL_DOMAIN: "techstart.io",
            COL_INDUSTRY: "Technology",
            COL_ADDRESS: "456 Tech Park, Bangalore",
            COL_EMAIL: "hello@techstart.io",
            COL_WEBSITE: "https://techstart.io",
            COL_CONTACT_NAME: "Jane Smith",
            COL_CONTACT_PHONE: "+91 9123456789",
            COL_CONTACT_EMAIL: "jane@techstart.io",
            COL_GST: "29AADCT1234F1ZP",
        },
    ]
    df = pd.DataFrame(example_rows, columns=TEMPLATE_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Clients")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition":
                "attachment; filename=client_template.xlsx"
        },
    )


@router.get("/export")
async def export_clients(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
) -> StreamingResponse:
    accounts = (
        await db.execute(
            select(Account).order_by(Account.name.asc())
        )
    ).scalars().all()

    rows = []
    for acct in accounts:
        det_result = await db.execute(
            select(ClientDetails)
            .where(ClientDetails.account_id == acct.id)
            .limit(1)
        )
        det = det_result.scalar_one_or_none()
        rows.append({
            COL_CLIENT_NAME: acct.name,
            COL_DOMAIN: acct.domain or "",
            COL_INDUSTRY: acct.industry or "",
            COL_ADDRESS: getattr(det, "address", "") or "",
            COL_EMAIL: getattr(det, "email", "") or "",
            COL_WEBSITE: getattr(det, "website", "") or "",
            COL_CONTACT_NAME: (
                getattr(det, "contact_person_name", "") or ""
            ),
            COL_CONTACT_PHONE: (
                getattr(det, "contact_person_phone", "") or ""
            ),
            COL_CONTACT_EMAIL: (
                getattr(det, "contact_person_email", "") or ""
            ),
            COL_GST: getattr(det, "gst_number", "") or "",
        })

    df = pd.DataFrame(rows, columns=TEMPLATE_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Clients")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition":
                "attachment; filename=clients_export.xlsx"
        },
    )


@router.post("/bulk-upload")
async def bulk_upload_clients(
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_CREATE]))
    ],
    file: UploadFile = File(...),
) -> Any:
    if not file.filename or not file.filename.endswith(
        (".xlsx", ".xls")
    ):
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel file (.xlsx)",
        )

    contents = await file.read()
    try:
        df = pd.read_excel(
            io.BytesIO(contents), engine="openpyxl"
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read Excel file: {e}",
        )

    df.columns = df.columns.str.strip()

    if COL_CLIENT_NAME not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required column: "
                   f"'{COL_CLIENT_NAME}'",
        )

    created = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    seen_names: dict[str, int] = {}  # name_lower -> first row

    for idx, row in df.iterrows():
        row_num = idx + 2
        client_name = str(
            row.get(COL_CLIENT_NAME, "")
        ).strip()
        if not client_name or client_name.lower() == "nan":
            errors.append(
                f"Row {row_num}: Client Name is required"
            )
            continue

        # Skip template example rows
        if client_name.lower() in EXAMPLE_CLIENT_NAMES:
            skipped += 1
            continue

        # Detect duplicate names within the file
        name_key = client_name.lower()
        if name_key in seen_names:
            errors.append(
                f"Row {row_num} ({client_name}): "
                f"duplicate of row {seen_names[name_key]}"
            )
            continue
        seen_names[name_key] = row_num

        def get_val(col: str) -> Optional[str]:
            val = str(row.get(col, "")).strip()
            if val and val.lower() != "nan":
                return val
            return None

        # Validate emails
        email_val = get_val(COL_EMAIL)
        contact_email_val = get_val(COL_CONTACT_EMAIL)
        row_errors: List[str] = []

        if email_val and not EMAIL_RE.match(email_val):
            row_errors.append(f"invalid email '{email_val}'")
        if (
            contact_email_val
            and not EMAIL_RE.match(contact_email_val)
        ):
            row_errors.append(
                f"invalid contact email "
                f"'{contact_email_val}'"
            )

        # Validate GST
        gst_val = get_val(COL_GST)
        if gst_val and not GST_RE.match(gst_val.upper()):
            row_errors.append(
                f"invalid GST number '{gst_val}'"
            )

        if row_errors:
            errors.append(
                f"Row {row_num} ({client_name}): "
                + "; ".join(row_errors)
            )
            continue

        try:
            existing_result = await db.execute(
                select(Account)
                .where(
                    func.lower(Account.name)
                    == client_name.lower()
                )
                .limit(1)
            )
            account = existing_result.scalar_one_or_none()

            domain_val = get_val(COL_DOMAIN)
            industry_val = get_val(COL_INDUSTRY)

            if account:
                if domain_val:
                    account.domain = domain_val
                if industry_val:
                    account.industry = industry_val
                is_update = True
            else:
                account = Account(
                    name=client_name,
                    domain=domain_val,
                    industry=industry_val,
                )
                db.add(account)
                await db.flush()
                is_update = False

            details_result = await db.execute(
                select(ClientDetails)
                .where(
                    ClientDetails.account_id == account.id
                )
                .limit(1)
            )
            details = details_result.scalar_one_or_none()

            address_val = get_val(COL_ADDRESS)
            website_val = get_val(COL_WEBSITE)
            contact_name_val = get_val(COL_CONTACT_NAME)
            contact_phone_val = get_val(COL_CONTACT_PHONE)

            has_details = any([
                address_val, email_val, website_val,
                contact_name_val, contact_phone_val,
                contact_email_val, gst_val,
            ])

            if has_details:
                if details is None:
                    details = ClientDetails(
                        account_id=account.id
                    )
                    db.add(details)

                if address_val:
                    details.address = address_val
                if email_val:
                    details.email = email_val
                if website_val:
                    details.website = website_val
                if contact_name_val:
                    details.contact_person_name = (
                        contact_name_val
                    )
                if contact_phone_val:
                    details.contact_person_phone = (
                        contact_phone_val
                    )
                if contact_email_val:
                    details.contact_person_email = (
                        contact_email_val
                    )
                if gst_val:
                    details.gst_number = gst_val

            audit = AuditLog(
                user_id=current_user.id,
                action="bulk_upload_client",
                resource_type="client",
                resource_id=str(account.id),
                details={
                    "name": client_name,
                    "action": (
                        "update" if is_update else "create"
                    ),
                },
            )
            db.add(audit)

            if is_update:
                updated += 1
            else:
                created += 1

        except Exception as e:
            logger.exception(
                f"Row {row_num} ({client_name}): "
                f"error processing"
            )
            errors.append(
                f"Row {row_num} ({client_name}): {str(e)}"
            )

    await db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": created + updated,
    }


@router.patch(
    "/{id}",
    response_model=AccountRead,
    responses={
        400: {"description": "Validation error"},
        404: {"description": "Not found"},
    },
)
async def update_client(
    id: int,
    *,
    db: deps.DBDep,
    client_in: AccountUpdate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_WRITE]))
    ],
) -> Any:
    db_obj = await db.get(Account, id)
    if not db_obj:
        raise HTTPException(
            status_code=404,
            detail="Client not found",
        )

    payload = client_in.model_dump(exclude_unset=True)

    if "name" in payload:
        new_name = (payload.get("name") or "").strip()
        if not new_name:
            raise HTTPException(
                status_code=400,
                detail="Client name cannot be empty",
            )

        dup_result = await db.execute(
            select(Account.id)
            .where(func.lower(Account.name) == new_name.lower())
            .where(Account.id != id)
            .limit(1)
        )
        if dup_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400,
                detail="Client name already exists",
            )

        db_obj.name = new_name

    if "domain" in payload:
        db_obj.domain = payload["domain"]
    if "industry" in payload:
        db_obj.industry = payload["industry"]

    audit = AuditLog(
        user_id=current_user.id,
        action="update_client",
        resource_type="client",
        resource_id=str(id),
        details={"updates": payload},
    )
    db.add(audit)

    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/{id}/details",
    response_model=ClientDetailsRead,
    responses={
        404: {"description": "Not found"},
    },
)
async def get_client_details(
    id: int,
    *,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
) -> Any:
    account = await db.get(Account, id)
    if not account:
        raise _client_not_found_exc(id)

    details = await _get_client_details(db, id)
    return _serialize_client_details(account, details)


@router.patch(
    "/{id}/details",
    response_model=ClientDetailsRead,
    responses={
        400: {"description": "Validation error"},
        404: {"description": "Not found"},
    },
)
async def update_client_details(
    id: int,
    *,
    db: deps.DBDep,
    client_in: ClientDetailsUpdate,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_WRITE]))
    ],
) -> Any:
    account = await db.get(Account, id)
    if not account:
        raise _client_not_found_exc(id)

    payload = client_in.model_dump(exclude_unset=True)

    account_updates = {}
    if "name" in payload:
        new_name = (payload.get("name") or "").strip()
        if not new_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "CLIENT_NAME_REQUIRED",
                        "message": "Client name cannot be empty",
                        "details": {},
                    }
                },
            )

        await _ensure_unique_client_name(
            db,
            client_id=id,
            name=new_name,
        )

        if new_name != account.name:
            account.name = new_name
            account_updates["name"] = new_name

    if "domain" in payload:
        account.domain = payload["domain"]
        account_updates["domain"] = payload["domain"]
    if "industry" in payload:
        account.industry = payload["industry"]
        account_updates["industry"] = payload["industry"]

    details = await _get_client_details(db, id)

    detail_keys = {
        "address",
        "email",
        "website",
        "contact_person_name",
        "contact_person_phone",
        "contact_person_email",
        "gst_number",
    }
    details_updates = {
        key: payload[key] for key in payload.keys() if key in detail_keys
    }

    if details is None and details_updates:
        details = ClientDetails(account_id=id)
        db.add(details)

    if details is not None:
        for key, value in details_updates.items():
            setattr(details, key, value)

    audit = AuditLog(
        user_id=current_user.id,
        action="update_client_details",
        resource_type="client",
        resource_id=str(id),
        details={
            "account_updates": account_updates,
            "details_updates": details_updates,
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(account)
    if details is not None:
        await db.refresh(details)

    return _serialize_client_details(account, details)


async def _client_delete_blockers(
    db: deps.DBDep, client_id: int
) -> dict:
    """Count business-meaningful links that should warn before delete."""
    from app.models.bd import Lead
    from app.models.project import Project

    project_count = (
        await db.execute(
            select(func.count())
            .select_from(Project)
            .where(Project.client_id == client_id)
        )
    ).scalar_one()
    lead_count = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.account_id == client_id)
        )
    ).scalar_one()
    return {
        "project_count": int(project_count),
        "lead_count": int(lead_count),
    }


@router.get("/{id}/delete-blockers")
async def get_client_delete_blockers(
    id: int,
    *,
    db: deps.DBDep,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_READ]))
    ],
) -> Any:
    account = await db.get(Account, id)
    if not account:
        raise _client_not_found_exc(id)
    return await _client_delete_blockers(db, id)


@router.delete(
    "/{id}",
    status_code=204,
    responses={
        404: {"description": "Not found"},
        409: {"description": "Has linked records — pass ?force=true"},
    },
)
async def delete_client(
    id: int,
    *,
    db: deps.DBDep,
    request: Request,
    force: Annotated[bool, Query()] = False,
    current_user: Annotated[
        User, Depends(deps.check_permissions([CLIENT_WRITE]))
    ],
) -> None:
    account = await db.get(Account, id)
    if not account:
        raise _client_not_found_exc(id)

    blockers = await _client_delete_blockers(db, id)
    if not force and (
        blockers["project_count"] > 0 or blockers["lead_count"] > 0
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "CLIENT_HAS_LINKED_RECORDS",
                    "message": (
                        "Client is linked to active projects or leads. "
                        "Pass ?force=true to delete anyway "
                        "(projects/leads stay but are unlinked)."
                    ),
                    "details": blockers,
                }
            },
        )

    name_for_audit = account.name
    await db.delete(account)
    db.add(AuditLog(
        user_id=current_user.id,
        action="delete_client",
        resource_type="client",
        resource_id=str(id),
        details={
            "name": name_for_audit,
            "forced": force,
            "blockers": blockers,
        },
        ip_address=request.client.host if request and request.client else None,
    ))
    await db.commit()
