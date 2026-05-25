from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.bid_task import LeadBidTaskReviewStatus
from app.schemas.user import UserLinkRead


class LeadBidTaskCreate(BaseModel):
    # Either provide a title, or provide template_id.
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    template_id: Optional[int] = Field(default=None, ge=1)
    bd_estimated_hours: Optional[float] = Field(default=None, ge=0)
    bd_estimated_cost: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_title_or_template(self) -> "LeadBidTaskCreate":
        title = (self.title or "").strip()
        if not title and self.template_id is None:
            raise ValueError(
                "title is required when template_id is not provided"
            )
        return self


class LeadBidTaskRead(BaseModel):
    id: int
    lead_id: int
    title: str
    description: Optional[str] = None
    bd_estimated_hours: Optional[float] = None
    bd_estimated_cost: Optional[float] = None
    is_archived: bool = False
    delivery_pm_user_id: Optional[int] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadBidTaskAssignmentCreate(BaseModel):
    pm_user_ids: List[int] = Field(default_factory=list, min_length=1)
    lead_document_ids: List[int] = Field(default_factory=list)
    delivery_pm_user_id: Optional[int] = Field(default=None, ge=1)
    deadline: Optional[datetime] = None


class BidTaskAssignmentDocumentRead(BaseModel):
    id: int
    file_name: str
    mime_type: str
    file_size: int
    uploaded_at: datetime
    download_url: str


class LeadBidTaskAssignmentRead(BaseModel):
    id: int
    bid_task_id: int
    pm_user_id: int
    assigned_by_id: Optional[int] = None
    deadline: Optional[datetime] = None
    created_at: datetime

    pm_user: Optional[UserLinkRead] = None

    model_config = ConfigDict(from_attributes=True)


class LeadBidTaskReviewLineUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = None
    hours: float = 0.0
    cost: float = 0.0
    sort_order: int = 0


class LeadBidTaskReviewLineRead(LeadBidTaskReviewLineUpsert):
    id: int
    review_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadBidTaskReviewUpsert(BaseModel):
    pm_notes: Optional[str] = None
    lines: List[LeadBidTaskReviewLineUpsert] = Field(default_factory=list)


class LeadBidTaskReviewRead(BaseModel):
    id: int
    assignment_id: int
    estimate_version_id: int
    revision_number: int
    status: LeadBidTaskReviewStatus

    currency: str
    total_hours: float
    total_cost: float

    pm_notes: Optional[str] = None
    bd_notes: Optional[str] = None

    created_by_id: Optional[int] = None
    previous_review_id: Optional[int] = None

    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None

    lines: List[LeadBidTaskReviewLineRead] = []

    model_config = ConfigDict(from_attributes=True)


class LeadBidTaskReviewRevisionRequest(BaseModel):
    bd_notes: str = Field(min_length=1)


class LeadBidTaskWithAssignments(BaseModel):
    task: LeadBidTaskRead
    assignments: List[LeadBidTaskAssignmentRead] = []


class LeadBidTaskReviewSummary(BaseModel):
    assignment: LeadBidTaskAssignmentRead
    latest_review: Optional[LeadBidTaskReviewRead] = None


class LeadBidEvaluationsResponse(BaseModel):
    lead_id: int
    estimate_version_id: int
    tasks: List[LeadBidTaskWithAssignments] = []
    reviews: List[LeadBidTaskReviewSummary] = []


class PMSubmissionIncludedReview(BaseModel):
    review_id: int
    assignment_id: int
    revision_number: int


class PMSubmissionRoleTotal(BaseModel):
    role: str
    hours: float
    cost: float
    rate: float


class PMSubmissionsSummaryResponse(BaseModel):
    lead_id: int
    estimate_version_id: int
    included_reviews: List[PMSubmissionIncludedReview] = []
    role_totals: List[PMSubmissionRoleTotal] = []


class MyBidRequestItem(BaseModel):
    lead_id: int
    lead_title: str
    lead_code: str
    estimate_version_id: int

    bid_task_id: int
    bid_task_title: str
    bd_estimated_hours: Optional[float] = None
    bd_estimated_cost: Optional[float] = None

    assignment_id: int
    deadline: Optional[datetime] = None
    latest_review_status: LeadBidTaskReviewStatus
    latest_revision_number: int
    updated_at: datetime

    documents: List[BidTaskAssignmentDocumentRead] = []
