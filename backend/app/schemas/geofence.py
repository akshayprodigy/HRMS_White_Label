from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.geofence import MIN_RADIUS_METERS, EnforcementMode


# ---- GeoFenceLocation ---------------------------------------------------


class GeoFenceLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_meters: int = Field(..., ge=MIN_RADIUS_METERS, le=10_000)
    is_active: bool = True


class GeoFenceLocationCreate(GeoFenceLocationBase):
    pass


class GeoFenceLocationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    radius_meters: Optional[int] = Field(
        default=None, ge=MIN_RADIUS_METERS, le=10_000
    )
    is_active: Optional[bool] = None


class GeoFenceLocationRead(GeoFenceLocationBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# ---- EmployeeGeoConfig --------------------------------------------------


_VALID_MODES = {m.value for m in EnforcementMode}


class EmployeeGeoConfigBase(BaseModel):
    enforcement_mode: str = Field(default="strict")
    geo_enabled: bool = True
    fence_ids: List[int] = Field(default_factory=list)

    @field_validator("enforcement_mode")
    @classmethod
    def _mode_valid(cls, v: str) -> str:
        if v not in _VALID_MODES:
            raise ValueError(
                f"enforcement_mode must be one of {sorted(_VALID_MODES)}"
            )
        return v


class EmployeeGeoConfigUpsert(EmployeeGeoConfigBase):
    """Used for single-employee create-or-update."""
    user_id: int


class EmployeeGeoConfigToggle(BaseModel):
    geo_enabled: bool


class EmployeeGeoConfigRead(EmployeeGeoConfigBase):
    user_id: int
    updated_at: datetime
    updated_by_id: Optional[int] = None

    # Enrichment for tables (not stored on row).
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    employee_department: Optional[str] = None
    fences: List[GeoFenceLocationRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ---- Bulk-assign --------------------------------------------------------


class BulkGeoAssignRequest(BaseModel):
    """Apply the SAME config to many employees.

    Provide EITHER employee_ids OR department (Employee.department string).
    """
    employee_ids: Optional[List[int]] = None
    department: Optional[str] = Field(default=None, min_length=1, max_length=100)
    enforcement_mode: str = Field(default="strict")
    geo_enabled: bool = True
    fence_ids: List[int] = Field(default_factory=list)

    @field_validator("enforcement_mode")
    @classmethod
    def _mode_valid(cls, v: str) -> str:
        if v not in _VALID_MODES:
            raise ValueError(
                f"enforcement_mode must be one of {sorted(_VALID_MODES)}"
            )
        return v

    @model_validator(mode="after")
    def _exactly_one_target(self):
        has_ids = bool(self.employee_ids)
        has_dept = bool(self.department)
        if has_ids == has_dept:
            raise ValueError(
                "Provide exactly one of employee_ids or department"
            )
        return self


class BulkGeoAssignResult(BaseModel):
    upserted: int
    failed: int
    errors: List[str] = Field(default_factory=list)


# ---- Punch error payload (returned on STRICT rejection) ----------------


class GeoRejectionDetail(BaseModel):
    """Structured error body returned from a STRICT-mode rejection.

    Sent inside `HTTPException.detail` so the frontend can render
    a precise message. The endpoint deliberately uses HTTP 422 to
    distinguish geo rejections from generic 400 validation errors.
    """
    error: str  # 'OUTSIDE_GEOFENCE' or 'MOCK_LOCATION'
    message: str
    nearest_fence_id: Optional[int] = None
    nearest_fence_name: Optional[str] = None
    distance_to_fence_meters: Optional[float] = None
    allowed_fence_ids: List[int] = Field(default_factory=list)
