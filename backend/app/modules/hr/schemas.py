from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmployeePublic(ORMModel):
    id: int

    employee_code: str | None

    first_name: str
    last_name: str | None

    email: str | None
    phone: str | None

    date_of_birth: dt.date | None
    gender: str | None

    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None

    bank_name: str | None
    bank_account_number: str | None
    bank_ifsc: str | None
    bank_branch: str | None

    emergency_contact_name: str | None
    emergency_contact_relation: str | None
    emergency_contact_phone: str | None

    employment_type: str
    employment_status: str

    joining_date: dt.date
    exit_date: dt.date | None

    created_at: dt.datetime
    updated_at: dt.datetime


class EmployeeCreate(BaseModel):
    employee_code: str | None = Field(default=None, max_length=50)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)

    date_of_birth: dt.date | None = None
    gender: str | None = Field(default=None, max_length=20)

    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)

    bank_name: str | None = Field(default=None, max_length=150)
    bank_account_number: str | None = Field(default=None, max_length=64)
    bank_ifsc: str | None = Field(default=None, max_length=32)
    bank_branch: str | None = Field(default=None, max_length=150)

    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_relation: str | None = Field(default=None, max_length=80)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    employment_type: str = Field(min_length=1, max_length=30)
    employment_status: str = Field(min_length=1, max_length=30)

    joining_date: dt.date
    exit_date: dt.date | None = None


class EmployeeUpdate(BaseModel):
    employee_code: str | None = Field(default=None, max_length=50)

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)

    date_of_birth: dt.date | None = None
    gender: str | None = Field(default=None, max_length=20)

    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)

    bank_name: str | None = Field(default=None, max_length=150)
    bank_account_number: str | None = Field(default=None, max_length=64)
    bank_ifsc: str | None = Field(default=None, max_length=32)
    bank_branch: str | None = Field(default=None, max_length=150)

    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_relation: str | None = Field(default=None, max_length=80)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    employment_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )
    employment_status: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )

    joining_date: dt.date | None = None
    exit_date: dt.date | None = None


class EmployeeDocumentPublic(ORMModel):
    id: int
    employee_id: int

    document_type: str
    title: str | None
    file_ref: str
    mime_type: str | None
    issued_on: dt.date | None
    expires_on: dt.date | None
    notes: str | None

    created_at: dt.datetime
    updated_at: dt.datetime


class EmployeeDocumentCreate(BaseModel):
    document_type: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=255)
    file_ref: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, max_length=100)
    issued_on: dt.date | None = None
    expires_on: dt.date | None = None
    notes: str | None = Field(default=None, max_length=500)


class EmployeeAssetPublic(ORMModel):
    id: int
    employee_id: int

    asset_category: str
    asset_name: str
    asset_tag: str | None

    issued_on: dt.date
    returned_on: dt.date | None
    notes: str | None

    created_at: dt.datetime
    updated_at: dt.datetime


class EmployeeAssetCreate(BaseModel):
    asset_category: str = Field(min_length=1, max_length=30)
    asset_name: str = Field(min_length=1, max_length=255)
    asset_tag: str | None = Field(default=None, max_length=80)
    issued_on: dt.date
    returned_on: dt.date | None = None
    notes: str | None = Field(default=None, max_length=500)


class EmployeeAssetUpdate(BaseModel):
    asset_category: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
    )
    asset_name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_tag: str | None = Field(default=None, max_length=80)
    issued_on: dt.date | None = None
    returned_on: dt.date | None = None
    notes: str | None = Field(default=None, max_length=500)


class LeaveTypePublic(ORMModel):
    id: int
    code: str
    name: str
    description: str | None
    is_active: bool

    created_at: dt.datetime
    updated_at: dt.datetime


class LeaveTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class LeaveTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class LeavePolicyPublic(ORMModel):
    id: int
    leave_type_id: int
    name: str
    monthly_credit_days: float
    max_balance_days: float | None
    is_active: bool
    notes: str | None

    created_at: dt.datetime
    updated_at: dt.datetime


class LeavePolicyCreate(BaseModel):
    leave_type_id: int
    name: str = Field(min_length=1, max_length=150)
    monthly_credit_days: float = Field(ge=0)
    max_balance_days: float | None = Field(default=None, ge=0)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=500)


class LeavePolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    monthly_credit_days: float | None = Field(default=None, ge=0)
    max_balance_days: float | None = Field(default=None, ge=0)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class LeaveBalancePublic(ORMModel):
    id: int
    employee_id: int
    leave_type_id: int
    balance_days: float

    created_at: dt.datetime
    updated_at: dt.datetime


class LeaveRequestPublic(ORMModel):
    id: int
    employee_id: int
    leave_type_id: int
    date_from: dt.date
    date_to: dt.date
    days: float
    reason: str | None
    status: str
    applied_at: dt.datetime
    decided_at: dt.datetime | None
    decided_by_user_id: int | None
    decision_comment: str | None

    created_at: dt.datetime
    updated_at: dt.datetime


class LeaveApplyRequest(BaseModel):
    employee_id: int
    leave_type_id: int
    date_from: dt.date
    date_to: dt.date
    reason: str | None = Field(default=None, max_length=500)


class LeaveDecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)


class HolidayCalendarPublic(ORMModel):
    id: int
    holiday_date: dt.date
    name: str
    is_optional: bool

    created_at: dt.datetime
    updated_at: dt.datetime


class HolidayCalendarCreate(BaseModel):
    holiday_date: dt.date
    name: str = Field(min_length=1, max_length=150)
    is_optional: bool = False
