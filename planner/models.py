from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Task:
    id: str
    topic_id: int
    subject: str
    topic: str
    minutes: int
    mastery: float
    difficulty: int
    deadline: datetime
    available_from: datetime
    kind: str = "learn"
    prerequisite: str | None = None
    card_id: int | None = None


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class PlannedSession:
    task: Task
    start: datetime
    end: datetime
    priority: float
    reason: str


@dataclass
class Plan:
    sessions: list[PlannedSession] = field(default_factory=list)
    unscheduled: dict[str, int] = field(default_factory=dict)
