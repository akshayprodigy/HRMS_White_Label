from typing import List
from pydantic import BaseModel, ConfigDict
from datetime import date


class AttendanceCompliance(BaseModel):
    date: date
    total_employees: int
    present_count: int
    compliance_percentage: float
    model_config = ConfigDict(from_attributes=True)


class ProjectUtilization(BaseModel):
    project_id: int
    project_name: str
    total_hours: float
    billable_hours: float
    utilization_percentage: float
    model_config = ConfigDict(from_attributes=True)


class LeaveBalanceSummary(BaseModel):
    employee_id: int
    employee_name: str
    leave_type: str
    total_allotted: float
    taken: float
    remaining: float
    model_config = ConfigDict(from_attributes=True)


class CostVariance(BaseModel):
    category: str
    budgeted_cost: float
    actual_cost: float
    variance: float
    variance_percentage: float
    model_config = ConfigDict(from_attributes=True)


class ReportsSummary(BaseModel):
    attendance_compliance: List[AttendanceCompliance]
    project_utilization: List[ProjectUtilization]
    leave_balances: List[LeaveBalanceSummary]
    cost_variance: List[CostVariance]
