from typing import Optional

from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentRead(DepartmentBase):
    id: int
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class DepartmentHeadUpdate(BaseModel):
    """Assign/clear the functional head and/or deputy of a department.
    Only provided fields are changed; pass null to clear."""
    head_user_id: Optional[int] = None
    deputy_head_user_id: Optional[int] = None


class TeamMemberRead(BaseModel):
    employee_id: str
    user_id: int
    full_name: Optional[str] = None
    department: str
    designation: Optional[str] = None
    status: str
    model_config = ConfigDict(from_attributes=True)


class HeadOfEmployeeRead(BaseModel):
    employee_id: int
    head_user_id: Optional[int] = None
    head_name: Optional[str] = None
