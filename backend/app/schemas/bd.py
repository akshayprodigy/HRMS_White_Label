from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime, date
from app.models.bd import LeadStage, ActivityType, EstimateStatus


class ActivityLogBase(BaseModel):
    type: ActivityType
    summary: str
    next_follow_up_at: Optional[datetime] = None


class ActivityLogCreate(ActivityLogBase):
    pass


class ActivityLogRead(ActivityLogBase):
    id: int
    lead_id: int
    created_by_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AccountBase(BaseModel):
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None


class AccountCreate(AccountBase):
    # Optional detail fields. When any are provided on create, the endpoint
    # writes a ClientDetails row in the same transaction so partial-create
    # is impossible.
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    contact_person_name: Optional[str] = None
    contact_person_phone: Optional[str] = None
    contact_person_email: Optional[EmailStr] = None
    gst_number: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None


class AccountRead(AccountBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClientDetailsBase(BaseModel):
    address: Optional[str] = None
    email: Optional[EmailStr] = None
    website: Optional[str] = None
    contact_person_name: Optional[str] = None
    contact_person_phone: Optional[str] = None
    contact_person_email: Optional[EmailStr] = None
    gst_number: Optional[str] = None


class ClientDetailsUpdate(ClientDetailsBase):
    name: Optional[str] = None
    domain: Optional[str] = None
    industry: Optional[str] = None


class ClientDetailsRead(ClientDetailsBase):
    account_id: int
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ContactBase(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None


class ContactCreate(ContactBase):
    account_id: int


class ContactRead(ContactBase):
    id: int
    account_id: int
    model_config = ConfigDict(from_attributes=True)


class LeadBase(BaseModel):
    title: str
    source: Optional[str] = None
    industry: Optional[str] = None
    stage: LeadStage = LeadStage.NEW
    probability_percent: int = 0
    expected_close_date: Optional[date] = None
    estimated_value: float = 0.0
    notes: Optional[str] = None


class LeadCreate(LeadBase):
    # If omitted, the API will auto-generate a unique lead_id.
    lead_id: Optional[str] = None
    # Convenience for UI: create/link an Account by name.
    account_name: Optional[str] = None
    account_id: Optional[int] = None
    contact_id: Optional[int] = None
    # If omitted, defaults to the current user.
    owner_user_id: Optional[int] = None


class LeadUpdate(BaseModel):
    title: Optional[str] = None
    source: Optional[str] = None
    industry: Optional[str] = None
    stage: Optional[LeadStage] = None
    probability_percent: Optional[int] = None
    expected_close_date: Optional[date] = None
    estimated_value: Optional[float] = None
    notes: Optional[str] = None
    owner_user_id: Optional[int] = None


class LeadRead(LeadBase):
    id: int
    lead_id: str
    account_id: Optional[int] = None
    contact_id: Optional[int] = None
    owner_user_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LeadNested(LeadRead):
    account: Optional[AccountRead] = None
    contact: Optional[ContactRead] = None
    activities: List[ActivityLogRead] = []


class LeadDocumentRead(BaseModel):
    id: int
    lead_id: int
    file_name: str
    mime_type: str
    file_size: int
    uploaded_at: datetime
    uploader_id: int
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PipelineStageSummary(BaseModel):
    stage: LeadStage
    count: int
    total_value: float
    weighted_value: float


class PipelineSummary(BaseModel):
    stages: List[PipelineStageSummary]
    total_count: int
    total_value: float
    total_weighted_value: float


class BDDashboard(BaseModel):
    pipeline: PipelineSummary
    expected_closes_this_month: int
    win_count: int
    loss_count: int
    avg_sales_cycle_days: float
    win_rate_percent: float


class EstimateAccuracyReport(BaseModel):
    # Stub for now
    total_estimates: int
    avg_variance_percent: float


# --- Estimates ---

class EstimatePhaseBase(BaseModel):
    phase_name: str
    start_offset_days: Optional[int] = None
    duration_days: int = 0
    description: Optional[str] = None
    assigned_user_id: Optional[int] = None


class EstimatePhaseCreate(EstimatePhaseBase):
    pass


class EstimatePhaseRead(EstimatePhaseBase):
    id: int
    version_id: int
    model_config = ConfigDict(from_attributes=True)


class EstimateResourceLineBase(BaseModel):
    role_name: str
    quantity: float = 1.0
    hours: float = 0.0
    rate: float = 0.0
    cost_decimal: float = 0.0


class EstimateResourceLineCreate(EstimateResourceLineBase):
    pass


class EstimateResourceLineRead(EstimateResourceLineBase):
    id: int
    version_id: int
    model_config = ConfigDict(from_attributes=True)


class EstimateVersionBase(BaseModel):
    name: str
    assumptions: Optional[str] = None
    scope_included: Optional[str] = None
    scope_excluded: Optional[str] = None
    currency: str = "INR"
    contingency_percent: float = 0.0
    margin_percent: float = 0.0


class EstimateVersionCreate(EstimateVersionBase):
    phases: List[EstimatePhaseCreate] = []
    resource_lines: List[EstimateResourceLineCreate] = []


class EstimateVersionUpdate(BaseModel):
    name: Optional[str] = None
    assumptions: Optional[str] = None
    scope_included: Optional[str] = None
    scope_excluded: Optional[str] = None
    currency: Optional[str] = None
    contingency_percent: Optional[float] = None
    margin_percent: Optional[float] = None
    phases: Optional[List[EstimatePhaseCreate]] = None
    resource_lines: Optional[List[EstimateResourceLineCreate]] = None


class EstimateVersionRead(EstimateVersionBase):
    id: int
    lead_id: int
    version_number: int
    status: EstimateStatus
    total_cost_decimal: float
    total_price_decimal: float
    created_by_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EstimateVersionDetailed(EstimateVersionRead):
    phases: List[EstimatePhaseRead] = []
    resource_lines: List[EstimateResourceLineRead] = []


class EstimateCompareItem(BaseModel):
    id: int
    version_number: int
    name: str
    status: EstimateStatus
    total_cost: float
    total_price: float
    margin_percent: float
    contingency_percent: float
    resource_count: int
    phase_count: int


class EstimateCompareResponse(BaseModel):
    version_a: EstimateVersionDetailed
    version_b: EstimateVersionDetailed
    summary_a: EstimateCompareItem
    summary_b: EstimateCompareItem


# --- Proposals ---

class ProposalSnapshotBase(BaseModel):
    snapshot_data: dict


class ProposalSnapshotCreate(ProposalSnapshotBase):
    pass


class EstimateSubmitRequest(BaseModel):
    approver_id: int


class ProposalSnapshotRead(ProposalSnapshotBase):
    id: int
    version_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class QuotationVersionRead(BaseModel):
    id: int
    estimate_version_id: int
    version_number: int
    status: str
    filename: str
    mime_type: str
    sha256: str
    created_by_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LeadToProjectConvert(BaseModel):
    project_manager_id: int
    start_date: date
    project_code: str
