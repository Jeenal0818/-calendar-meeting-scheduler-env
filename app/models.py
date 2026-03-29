from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field


class EventPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class MeetingType(str, Enum):
    one_on_one = "one_on_one"
    standup = "standup"
    review = "review"
    planning = "planning"
    sync = "sync"
    ad_hoc = "ad_hoc"


class DailyWindow(BaseModel):
    start: str = Field(..., description="Local time HH:MM")
    end: str = Field(..., description="Local time HH:MM")


class UserPreferences(BaseModel):
    daily_meeting_cap_hours: float = Field(3.0, ge=0.0, le=10.0)
    prefer_morning: Optional[bool] = None
    preferred_earliest_local: str = Field("09:00", description="Soft preference boundary")
    preferred_latest_local: str = Field("17:00", description="Soft preference boundary")


class User(BaseModel):
    user_id: str
    name: str
    timezone: str
    work_hours: Dict[str, DailyWindow] = Field(
        ..., description="Map weekday -> working window in local time"
    )
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class Event(BaseModel):
    event_id: str
    title: str
    owner_id: str
    attendees: List[str]
    start: datetime
    end: datetime
    is_virtual: bool = True
    location: Optional[str] = None
    is_mandatory: bool = False
    priority: EventPriority = EventPriority.medium
    source: str = Field("agent", description="seeded|agent")
    linked_request_id: Optional[str] = None


class MeetingRequest(BaseModel):
    request_id: str
    organizer_id: str
    attendees: List[str]
    duration_minutes: int = Field(..., ge=15, le=240)
    deadline: date
    meeting_type: MeetingType
    priority: EventPriority = EventPriority.medium
    title_hint: str = "Meeting"


class EnvMeta(BaseModel):
    task_id: str
    seed: int
    horizon_start: date
    horizon_days: int
    step_count: int = 0
    last_action: Optional[Dict[str, Any]] = None
    seeded_mandatory_anchors: Dict[str, Tuple[datetime, datetime]] = Field(
        default_factory=dict,
        description="For stability grading: event_id -> (original_start_utc, original_end_utc)",
    )


class EnvironmentState(BaseModel):
    meta: EnvMeta
    users: List[User]
    events: List[Event]
    meeting_requests: List[MeetingRequest]


class CreateMeetingAction(BaseModel):
    kind: Literal["create_meeting"] = "create_meeting"
    request_id: str
    start: datetime
    is_virtual: bool = True
    location: Optional[str] = None
    title: Optional[str] = None


class MoveEventAction(BaseModel):
    kind: Literal["move_event"] = "move_event"
    event_id: str
    new_start: datetime
    new_end: datetime


class CancelEventAction(BaseModel):
    kind: Literal["cancel_event"] = "cancel_event"
    event_id: str


class NoOpAction(BaseModel):
    kind: Literal["noop"] = "noop"


Action = Union[CreateMeetingAction, MoveEventAction, CancelEventAction, NoOpAction]


class ResetInput(BaseModel):
    task_id: str
    seed: Optional[int] = None


class ResetOutput(BaseModel):
    state: EnvironmentState


class StepInput(BaseModel):
    task_id: str
    action: Action


class StepOutput(BaseModel):
    state: EnvironmentState
    reward: float
    done: bool = False


class GraderInput(BaseModel):
    task_id: str
    state: EnvironmentState


class GraderOutput(BaseModel):
    grade: float


class BaselineOutput(BaseModel):
    scores: Dict[str, float]


class TaskInfo(BaseModel):
    task_id: str
    name: str
    description: str
    difficulty: Literal["easy", "medium", "hard"]
    action_schema: Dict[str, Any]
