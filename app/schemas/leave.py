from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LeaveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leave_type: Literal["事假", "病假", "年假", "调休"]
    start_date: date
    end_date: date
    reason: str = Field(min_length=2, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("请填写至少2个字的请假事由")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class LeaveReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_rejection_reason(self):
        self.comment = self.comment.strip()
        if self.decision == "rejected" and not self.comment:
            raise ValueError("驳回时请填写审批意见")
        return self


class LeaveInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applicant: str
    leave_type: str
    start_date: date
    end_date: date
    days: int
    reason: str
    status: str
    review_comment: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
