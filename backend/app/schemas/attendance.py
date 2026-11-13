from datetime import datetime, date
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class AttendanceBase(BaseModel):
    mode: str
    remarks: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None


class AttendanceMark(AttendanceBase):
    captured_at: Optional[datetime] = None
    # Device-reported flag set by the mobile/web client. Untrusted by
    # design — only the resolver decides what to do with it.
    is_mock_location: Optional[bool] = False
    # Selfie (POST /attendance/selfie) + on-device liveness result.
    selfie_id: Optional[int] = None
    liveness_passed: Optional[bool] = None
    liveness_score: Optional[float] = None


class AttendanceRead(AttendanceBase):
    id: int
    user_id: int
    captured_at: datetime
    punch_out_time: Optional[datetime] = None
    created_at: datetime

    # Shift-aware fields. work_date is the primary date for queries
    # and reporting; the calendar date of captured_at may differ for
    # overnight shifts.
    work_date: Optional[date] = None
    shift_template_id: Optional[int] = None
    is_cross_midnight: bool = False
    attribution_flag: Optional[str] = None

    # Geo-fencing snapshot at punch-in. punch_out_* mirror them.
    is_mock_location: bool = False
    matched_fence_id: Optional[int] = None
    distance_to_fence_meters: Optional[float] = None
    geo_flag: Optional[str] = None
    punch_out_latitude: Optional[float] = None
    punch_out_longitude: Optional[float] = None
    punch_out_accuracy: Optional[float] = None
    punch_out_is_mock: bool = False
    punch_out_matched_fence_id: Optional[int] = None
    punch_out_distance_to_fence_meters: Optional[float] = None
    punch_out_geo_flag: Optional[str] = None

    # Selfie / liveness / offline (Phase 3). The raw filename is never
    # exposed; fetch the image via GET /attendance/{id}/selfie?side=in|out.
    has_selfie: bool = False
    has_punch_out_selfie: bool = False
    liveness_passed: Optional[bool] = None
    punch_out_liveness_passed: Optional[bool] = None
    is_offline: bool = False
    review_flag: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AttendanceHRRead(AttendanceRead):
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    shift_template_name: Optional[str] = None
    matched_fence_name: Optional[str] = None
    punch_out_matched_fence_name: Optional[str] = None
    # Section Q: time-rule flags (None when flags disabled / not
    # applicable) + HR edit-trail badge fields.
    late_minutes: Optional[int] = None
    early_exit_minutes: Optional[int] = None
    edited_at: Optional[datetime] = None
    edited_by_name: Optional[str] = None


class OfflinePunchItem(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=64)
    kind: Literal["in", "out"]
    captured_at: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    is_mock_location: Optional[bool] = False
    selfie_id: Optional[int] = None
    liveness_passed: Optional[bool] = None
    liveness_score: Optional[float] = None


class OfflineSyncRequest(BaseModel):
    punches: List[OfflinePunchItem] = Field(min_length=1, max_length=50)


class OfflinePunchResult(BaseModel):
    client_uuid: str
    kind: str
    status: str  # created | duplicate | rejected
    reason: Optional[str] = None
    attendance_id: Optional[int] = None


class OfflineSyncResponse(BaseModel):
    results: List[OfflinePunchResult]
    counts: dict[str, int]


class AttendanceTimesEdit(BaseModel):
    """HR/admin direct edit of punch times. At least one time required."""
    punch_in_time: Optional[datetime] = None
    punch_out_time: Optional[datetime] = None
    reason: str

    model_config = ConfigDict(str_strip_whitespace=True)


class AttendanceManualCreate(BaseModel):
    """HR/admin creates a record for a fully-missed day."""
    user_id: int
    work_date: date
    punch_in_time: datetime
    punch_out_time: Optional[datetime] = None
    reason: str

    model_config = ConfigDict(str_strip_whitespace=True)


class AttendanceBulkMark(BaseModel):
    """Supervisor/HR fallback when the punch system is down. Times are UTC
    wall-clock: 'HH:MM' (on work_date) or an ISO datetime."""
    work_date: date
    user_ids: List[int] = Field(min_length=1, max_length=200)
    punch_in_time: str
    punch_out_time: Optional[str] = None
    reason: str

    model_config = ConfigDict(str_strip_whitespace=True)


class AttendanceBulkResult(BaseModel):
    user_id: int
    status: str  # created|skipped_existing|out_of_scope|locked|error
    attendance_id: Optional[int] = None
    message: Optional[str] = None


class AttendanceBulkResponse(BaseModel):
    batch_id: str
    work_date: date
    results: List[AttendanceBulkResult]
    counts: dict[str, int]


class TimeRulesRead(BaseModel):
    rules: dict[str, str]


class TimeRulesUpdate(BaseModel):
    rules: dict[str, str]


class AttendanceToday(BaseModel):
    is_marked: bool
    attendance: Optional[AttendanceRead] = None


class AttendanceCorrectionBase(BaseModel):
    attendance_id: Optional[int] = None
    date: date
    # Optional: when set, the approver will retag the attendance record
    # to this work_date. None = unchanged from existing record.
    requested_work_date: Optional[date] = None
    requested_mode: str
    requested_remarks: Optional[str] = None
    reason: str
    attachment_url: Optional[str] = None


class AttendanceCorrectionCreate(AttendanceCorrectionBase):
    pass


class AttendanceCorrectionUpdate(BaseModel):
    status: str  # approved, rejected


class AttendanceCorrectionRead(AttendanceCorrectionBase):
    id: int
    user_id: int
    status: str
    created_by_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
