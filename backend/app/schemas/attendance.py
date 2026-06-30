from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


class AttendanceHRRead(AttendanceRead):
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    shift_template_name: Optional[str] = None
    matched_fence_name: Optional[str] = None
    punch_out_matched_fence_name: Optional[str] = None


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
