from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class LeavePolicyCell(BaseModel):
    employment_type_id: int
    leave_type_id: int
    is_eligible: bool = True
    annual_quota: Optional[float] = None


class LeavePolicyRead(LeavePolicyCell):
    id: int
    model_config = ConfigDict(from_attributes=True)


class LeavePolicyMatrix(BaseModel):
    employment_types: List[dict]
    leave_types: List[dict]
    cells: List[LeavePolicyRead]


class AllocateRequest(BaseModel):
    user_id: Optional[int] = None
    employment_type_id: Optional[int] = None
    overwrite: bool = False
