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


class AttendanceRead(AttendanceBase):
    id: int
    user_id: int
    captured_at: datetime
    punch_out_time: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttendanceHRRead(AttendanceRead):
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class AttendanceToday(BaseModel):
    is_marked: bool
    attendance: Optional[AttendanceRead] = None


class AttendanceCorrectionBase(BaseModel):
    attendance_id: Optional[int] = None
    date: date
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
