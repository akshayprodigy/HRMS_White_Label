from datetime import date
from typing import Optional, List, Union
from pydantic import BaseModel, ConfigDict, EmailStr
from .user import UserRead


class EmployeeUserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    manager_id: Optional[int] = None


class EmployeeBase(BaseModel):
    employee_id: str
    department: str
    designation: str
    date_of_joining: date
    status: str = "active"


class EmployeeCreate(EmployeeBase):
    user_id: int
    salary: Optional[float] = None
    conveyance_allowance: Optional[float] = None
    hra: Optional[float] = None
    other_allowance: Optional[float] = None
    esic_applicable: Optional[bool] = None
    bank_account: Optional[str] = None
    pf_number: Optional[str] = None
    pan_number: Optional[str] = None
    manager_id: Optional[int] = None
    notice_period_days: Optional[int] = 30


class EmployeeCreateWithUser(EmployeeBase):
    user: EmployeeUserCreate
    salary: Optional[float] = None
    conveyance_allowance: Optional[float] = None
    hra: Optional[float] = None
    other_allowance: Optional[float] = None
    esic_applicable: Optional[bool] = None
    bank_account: Optional[str] = None
    pf_number: Optional[str] = None
    pan_number: Optional[str] = None
    notice_period_days: Optional[int] = 30


class EmployeeUpdate(BaseModel):
    department: Optional[str] = None
    designation: Optional[str] = None
    date_of_joining: Optional[date] = None
    status: Optional[str] = None
    employment_type: Optional[str] = None
    salary: Optional[float] = None
    conveyance_allowance: Optional[float] = None
    hra: Optional[float] = None
    other_allowance: Optional[float] = None
    esic_applicable: Optional[bool] = None
    bank_account: Optional[str] = None
    pf_number: Optional[str] = None
    pan_number: Optional[str] = None
    manager_id: Optional[int] = None
    kra: Optional[str] = None
    notice_period_days: Optional[int] = None


class EmployeeProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


class EmployeeRead(EmployeeBase):
    id: int
    user_id: int
    user: UserRead
    kra: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    notice_period_days: int = 30

    model_config = ConfigDict(from_attributes=True)


class EmployeeHRRead(EmployeeRead):
    employment_type: str = "permanent"
    salary: Optional[float] = None
    conveyance_allowance: Optional[float] = None
    hra: Optional[float] = None
    other_allowance: Optional[float] = None
    esic_applicable: Optional[bool] = None
    bank_account: Optional[str] = None
    pf_number: Optional[str] = None
    pan_number: Optional[str] = None


class EmployeeList(BaseModel):
    items: List[Union[EmployeeHRRead, EmployeeRead]]
    total: int
