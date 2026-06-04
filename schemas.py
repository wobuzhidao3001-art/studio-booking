from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserCreate(BaseModel):
    username: str
    password: str
    real_name: str
    department: str
    phone: str = ""
    roles: List[str] = ["applicant"]


class UserUpdate(BaseModel):
    real_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[int] = None
    roles: Optional[List[str]] = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class MeetingTypeCreate(BaseModel):
    name: str


class MeetingTypeUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[int] = None


class ApplicationCreate(BaseModel):
    department: str
    contact: str
    meeting_topic: str
    meeting_type_id: int
    start_time: str
    end_time: str
    remarks: str = ""
    on_site_contact: str = ""


class ApplicationUpdate(BaseModel):
    department: Optional[str] = None
    contact: Optional[str] = None
    meeting_topic: Optional[str] = None
    meeting_type_id: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    remarks: Optional[str] = None
    on_site_contact: Optional[str] = None


class ApprovalAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: str = ""


class AssignExecutor(BaseModel):
    executor_id: int


class ReportCreate(BaseModel):
    items_returned: str
    cleanliness: str
    damage: str = ""
    score: float = Field(..., ge=0, le=10)


class ReminderCreate(BaseModel):
    target_stage: str
    message: str = ""
