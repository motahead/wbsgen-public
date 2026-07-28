"""Validation models and codes for WBS-GEN."""

from __future__ import annotations

from dataclasses import dataclass, field


__all__ = [
    "LEVEL_ERROR",
    "LEVEL_WARNING",
    "CODE_PROJECT_REQUIRED",
    "CODE_PROJECT_NAME_REQUIRED",
    "CODE_PROJECT_DATE_INVALID",
    "CODE_PROJECT_STATUS_DATE_OUT_OF_RANGE",
    "CODE_TASKS_REQUIRED",
    "CODE_TASK_REQUIRED",
    "CODE_TASK_ID_REQUIRED",
    "CODE_TASK_ID_INVALID",
    "CODE_TASK_ID_DUPLICATED",
    "CODE_TASK_NAME_REQUIRED",
    "CODE_TASK_DATE_INVALID",
    "CODE_TASK_DATE_OUT_OF_RANGE",
    "CODE_TASK_PROGRESS_INVALID",
    "CODE_TASK_PLANNED_DURATION_INVALID",
    "CODE_TASK_UNPLANNED",
    "CODE_TASK_PLANNED_START_WEEKEND",
    "CODE_TASK_PLANNED_START_NON_WORKING_DAY",
    "CODE_TASK_ACTUAL_END_WITHOUT_ACTUAL_START",
    "CODE_TASK_ACTUAL_END_BEFORE_ACTUAL_START",
    "CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH",
    "CODE_TASK_PROGRESS_COMPLETE_WITHOUT_ACTUAL_END",
    "CODE_MISSING_PARENT_TASK",
    "CODE_PARENT_FIELD_IGNORED",
    "CODE_DISPLAY_INVALID",
    "CODE_HOLIDAYS_INVALID",
    "CODE_HOLIDAY_REQUIRED",
    "CODE_HOLIDAY_DATE_INVALID",
    "CODE_HOLIDAY_NAME_INVALID",
    "CODE_HOLIDAY_DATE_DUPLICATED",
    "CODE_MILESTONES_INVALID",
    "CODE_MILESTONE_REQUIRED",
    "CODE_MILESTONE_DATE_INVALID",
    "CODE_MILESTONE_NAME_REQUIRED",
    "CODE_MILESTONE_DUPLICATED",
    "CODE_MILESTONE_DATE_OUT_OF_RANGE",
    "ValidationMessage",
    "ValidationResult",
    "format_validation_messages",
    "validation_report_to_dict",
]

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"

CODE_PROJECT_REQUIRED = "PROJECT_REQUIRED"
CODE_PROJECT_NAME_REQUIRED = "PROJECT_NAME_REQUIRED"
CODE_PROJECT_DATE_INVALID = "PROJECT_DATE_INVALID"
CODE_PROJECT_STATUS_DATE_OUT_OF_RANGE = "PROJECT_STATUS_DATE_OUT_OF_RANGE"
CODE_TASKS_REQUIRED = "TASKS_REQUIRED"
CODE_TASK_REQUIRED = "TASK_REQUIRED"
CODE_TASK_ID_REQUIRED = "TASK_ID_REQUIRED"
CODE_TASK_ID_INVALID = "TASK_ID_INVALID"
CODE_TASK_ID_DUPLICATED = "TASK_ID_DUPLICATED"
CODE_TASK_NAME_REQUIRED = "TASK_NAME_REQUIRED"
CODE_TASK_DATE_INVALID = "TASK_DATE_INVALID"
CODE_TASK_DATE_OUT_OF_RANGE = "TASK_DATE_OUT_OF_RANGE"
CODE_TASK_PROGRESS_INVALID = "TASK_PROGRESS_INVALID"
CODE_TASK_PLANNED_DURATION_INVALID = "TASK_PLANNED_DURATION_INVALID"
CODE_TASK_UNPLANNED = "TASK_UNPLANNED"
CODE_TASK_PLANNED_START_WEEKEND = "TASK_PLANNED_START_WEEKEND"
CODE_TASK_PLANNED_START_NON_WORKING_DAY = "TASK_PLANNED_START_NON_WORKING_DAY"
CODE_TASK_ACTUAL_END_WITHOUT_ACTUAL_START = "TASK_ACTUAL_END_WITHOUT_ACTUAL_START"
CODE_TASK_ACTUAL_END_BEFORE_ACTUAL_START = "TASK_ACTUAL_END_BEFORE_ACTUAL_START"
CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH = "TASK_PROGRESS_ACTUAL_END_MISMATCH"
CODE_TASK_PROGRESS_COMPLETE_WITHOUT_ACTUAL_END = (
    "TASK_PROGRESS_COMPLETE_WITHOUT_ACTUAL_END"
)
CODE_MISSING_PARENT_TASK = "MISSING_PARENT_TASK"
CODE_PARENT_FIELD_IGNORED = "PARENT_FIELD_IGNORED"
CODE_DISPLAY_INVALID = "DISPLAY_INVALID"
CODE_HOLIDAYS_INVALID = "HOLIDAYS_INVALID"
CODE_HOLIDAY_REQUIRED = "HOLIDAY_REQUIRED"
CODE_HOLIDAY_DATE_INVALID = "HOLIDAY_DATE_INVALID"
CODE_HOLIDAY_NAME_INVALID = "HOLIDAY_NAME_INVALID"
CODE_HOLIDAY_DATE_DUPLICATED = "HOLIDAY_DATE_DUPLICATED"
CODE_MILESTONES_INVALID = "MILESTONES_INVALID"
CODE_MILESTONE_REQUIRED = "MILESTONE_REQUIRED"
CODE_MILESTONE_DATE_INVALID = "MILESTONE_DATE_INVALID"
CODE_MILESTONE_NAME_REQUIRED = "MILESTONE_NAME_REQUIRED"
CODE_MILESTONE_DUPLICATED = "MILESTONE_DUPLICATED"
CODE_MILESTONE_DATE_OUT_OF_RANGE = "MILESTONE_DATE_OUT_OF_RANGE"


@dataclass(frozen=True)
class ValidationMessage:
    level: str
    code: str
    path: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def error(self, code: str, path: str, message: str) -> None:
        self.errors.append(ValidationMessage(LEVEL_ERROR, code, path, message))

    def warning(self, code: str, path: str, message: str) -> None:
        self.warnings.append(ValidationMessage(LEVEL_WARNING, code, path, message))


def format_validation_messages(validation: ValidationResult) -> list[str]:
    messages = validation.errors + validation.warnings
    return [
        f"wbsgen: {message.level} {message.code} {message.path}: {message.message}"
        for message in messages
    ]


def validation_message_to_dict(message: ValidationMessage) -> dict[str, str]:
    return {
        "level": message.level,
        "code": message.code,
        "path": message.path,
        "message": message.message,
    }


def validation_report_to_dict(validation: ValidationResult) -> dict[str, object]:
    return {
        "ok": not validation.has_errors,
        "errorCount": len(validation.errors),
        "warningCount": len(validation.warnings),
        "errors": [validation_message_to_dict(message) for message in validation.errors],
        "warnings": [
            validation_message_to_dict(message) for message in validation.warnings
        ],
    }
