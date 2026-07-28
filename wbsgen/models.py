"""Data models for WBS-GEN."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .validation import ValidationResult


__all__ = [
    "DAY_WIDTH",
    "ROW_HEIGHT",
    "BAR_HEIGHT",
    "PROGRESS_BAR_HEIGHT",
    "ACTUAL_BAR_HEIGHT",
    "MONTH_LABEL_MIN_DAYS",
    "DEFAULT_TASK_NAME_WIDTH",
    "DEFAULT_ASSIGNEE_WIDTH",
    "DEFAULT_COMMENT_WIDTH",
    "Project",
    "DisplaySettings",
    "Task",
    "ComputedTask",
    "DisplayRow",
    "ProgressAnalysis",
    "ChartScale",
    "Holiday",
    "Milestone",
    "MILESTONE_TIER_HEIGHT",
    "PlacedMilestone",
    "WorkCalendar",
    "BuildResult",
]

DAY_WIDTH = 32
ROW_HEIGHT = 32
BAR_HEIGHT = 12
PROGRESS_BAR_HEIGHT = 8
ACTUAL_BAR_HEIGHT = 2
MONTH_LABEL_MIN_DAYS = 3
MILESTONE_TIER_HEIGHT = 24
DEFAULT_TASK_NAME_WIDTH = 220
DEFAULT_ASSIGNEE_WIDTH = 56
DEFAULT_COMMENT_WIDTH = 220
STANDARD_COLUMN_ORDER = ("assignee", "planned-period", "actual-period", "progress", "expected-progress", "issue")
ANALYSIS_COLUMN_ORDER = ("assignee", "progress", "expected-progress", "delta", "delay", "pace")


@dataclass
class Project:
    name: str
    status_date: date
    start_date: date | None = None
    end_date: date | None = None
    issue_base_url: str | None = None


@dataclass(frozen=True)
class DisplaySettings:
    standard_columns: tuple[str, ...] = ("*",)
    standard_column_widths: dict[str, int] = field(default_factory=dict)
    standard_column_order: tuple[str, ...] = STANDARD_COLUMN_ORDER
    analysis_column_order: tuple[str, ...] = ANALYSIS_COLUMN_ORDER
    layers: tuple[str, ...] = ("*",)

@dataclass
class Task:
    id: str
    name: str
    planned_start: date | None = None
    planned_duration: int | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: int | None = None
    has_progress_input: bool = False
    issue: int | None = None
    comment: str | None = None
    assignee: str | None = None
    source_index: int | None = None
    generated: bool = False
    children: list["Task"] = field(default_factory=list)


@dataclass
class ComputedTask:
    id: str
    name: str
    source_task: Task
    planned_start: date | None = None
    planned_end: date | None = None
    planned_duration: int | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: int = 0
    issue: int | None = None
    comment: str | None = None
    assignee: str | None = None
    generated: bool = False
    children: list["ComputedTask"] = field(default_factory=list)


@dataclass(frozen=True)
class ProgressAnalysis:
    delta: int | None = None
    delay_business_days: int | None = None
    required_pace: float | None = None
    pace_unattainable: bool = False


@dataclass(frozen=True)
class DisplayRow:
    task: ComputedTask
    depth: int


@dataclass(frozen=True)
class ChartScale:
    start_date: date
    end_date: date
    day_width: int = DAY_WIDTH

    @property
    def column_count(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def chart_width(self) -> int:
        return self.column_count * self.day_width

    def x_for_date(self, value: date) -> int:
        return (value - self.start_date).days * self.day_width

    def x_for_date_end(self, value: date) -> int:
        return self.x_for_date(value) + self.day_width


@dataclass(frozen=True)
class Holiday:
    date: date
    name: str | None = None


@dataclass(frozen=True)
class Milestone:
    date: date
    name: str
    source_index: int | None = None


@dataclass(frozen=True)
class PlacedMilestone:
    milestone: Milestone
    tier: int
    x: int


@dataclass(frozen=True)
class WorkCalendar:
    holidays: tuple[Holiday, ...] = ()

    @property
    def holiday_dates(self) -> frozenset[date]:
        return frozenset(holiday.date for holiday in self.holidays)

    def is_non_working_day(self, value: date) -> bool:
        return value.weekday() >= 5 or value in self.holiday_dates

    def holiday_for(self, value: date) -> Holiday | None:
        for holiday in self.holidays:
            if holiday.date == value:
                return holiday
        return None


@dataclass
class BuildResult:
    project: Project | None
    tasks: list[Task]
    roots: list[Task]
    computed_roots: list[ComputedTask]
    display_start_date: date | None
    display_end_date: date | None
    validation: ValidationResult
    holidays: list[Holiday] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    display_settings: DisplaySettings = field(default_factory=DisplaySettings)
