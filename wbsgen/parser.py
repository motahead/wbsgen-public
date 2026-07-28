"""Input loading and JSON parsing for WBS-GEN."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .models import ANALYSIS_COLUMN_ORDER, STANDARD_COLUMN_ORDER, DisplaySettings, Holiday, Milestone, Project, Task
from .validation import *


__all__ = [
    "DATE_PATTERN",
    "WBS_ID_PATTERN",
    "load_json",
    "parse_date_value",
    "parse_project",
    "is_valid_wbs_id",
    "parse_optional_int",
    "parse_tasks",
    "parse_display",
    "parse_holidays",
    "parse_milestones",
]

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WBS_ID_PATTERN = re.compile(r"^[1-9][0-9]*(\.[1-9][0-9]*)*$")
DISPLAY_COLUMN_KEYS = {"planned", "actual", "progress", "expected", "issue", "comment", "assignee"}
DISPLAY_LAYER_KEYS = {"inazuma", "actual", "highlight", "tooltip", "delayHighlight", "milestone"}
COLUMN_ORDER_KEYS = set(STANDARD_COLUMN_ORDER) | set(ANALYSIS_COLUMN_ORDER)
COLUMN_WIDTH_KEYS = {"name", "assignee", "comment"}
MIN_COLUMN_WIDTH = 40
DISPLAY_UNSET = object()


def load_json(path: Path, *, label: str = "input") -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label} JSON root must be an object")
    return data


def parse_date_value(
    value: Any,
    path: str,
    validation: ValidationResult,
    code: str,
) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        validation.error(code, path, "日付は YYYY-MM-DD 形式の文字列で指定してください")
        return None
    if not DATE_PATTERN.fullmatch(value):
        validation.error(code, path, "日付は YYYY-MM-DD 形式で指定してください")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        validation.error(code, path, "日付は YYYY-MM-DD 形式で指定してください")
        return None


def parse_project(
    raw_project: Any,
    validation: ValidationResult,
    today: date,
) -> Project | None:
    if not isinstance(raw_project, dict):
        validation.error(CODE_PROJECT_REQUIRED, "project", "project はオブジェクトで指定してください")
        return None

    name = raw_project.get("name")
    if not isinstance(name, str) or not name:
        validation.error(CODE_PROJECT_NAME_REQUIRED, "project.name", "project.name は必須です")

    status_date = parse_date_value(
        raw_project.get("statusDate"),
        "project.statusDate",
        validation,
        CODE_PROJECT_DATE_INVALID,
    )
    if status_date is None:
        status_date = today

    start_date = parse_date_value(
        raw_project.get("startDate"),
        "project.startDate",
        validation,
        CODE_PROJECT_DATE_INVALID,
    )
    end_date = parse_date_value(
        raw_project.get("endDate"),
        "project.endDate",
        validation,
        CODE_PROJECT_DATE_INVALID,
    )

    if validation.has_errors:
        project_errors = [
            message
            for message in validation.errors
            if message.path.startswith("project.")
        ]
        if project_errors:
            return None

    assert isinstance(name, str)
    issue_base_url = raw_project.get("issueBaseUrl")
    if not isinstance(issue_base_url, str):
        issue_base_url = None

    return Project(
        name=name,
        status_date=status_date,
        start_date=start_date,
        end_date=end_date,
        issue_base_url=issue_base_url,
    )


def is_valid_wbs_id(value: str) -> bool:
    return bool(WBS_ID_PATTERN.fullmatch(value))


def parse_optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_tasks(raw_tasks: Any, validation: ValidationResult) -> list[Task]:
    if not isinstance(raw_tasks, list):
        validation.error(CODE_TASKS_REQUIRED, "tasks", "tasks は配列で指定してください")
        return []

    tasks: list[Task] = []
    seen_ids: set[str] = set()

    for index, raw_task in enumerate(raw_tasks):
        path = f"tasks[{index}]"
        if not isinstance(raw_task, dict):
            validation.error(CODE_TASK_REQUIRED, path, "task はオブジェクトで指定してください")
            continue

        raw_id = raw_task.get("id")
        if raw_id is None or raw_id == "":
            validation.error(CODE_TASK_ID_REQUIRED, f"{path}.id", "task.id は必須です")
            continue
        if not isinstance(raw_id, str) or not is_valid_wbs_id(raw_id):
            validation.error(CODE_TASK_ID_INVALID, f"{path}.id", "WBS IDの形式が不正です")
            continue
        if raw_id in seen_ids:
            validation.error(CODE_TASK_ID_DUPLICATED, f"{path}.id", "WBS IDが重複しています")
            continue
        seen_ids.add(raw_id)

        name = raw_task.get("name")
        if not isinstance(name, str) or not name:
            validation.error(CODE_TASK_NAME_REQUIRED, f"{path}.name", "task.name は必須です")
            name = ""

        planned_start = parse_date_value(
            raw_task.get("plannedStart"),
            f"{path}.plannedStart",
            validation,
            CODE_TASK_DATE_INVALID,
        )
        actual_start = parse_date_value(
            raw_task.get("actualStart"),
            f"{path}.actualStart",
            validation,
            CODE_TASK_DATE_INVALID,
        )
        actual_end = parse_date_value(
            raw_task.get("actualEnd"),
            f"{path}.actualEnd",
            validation,
            CODE_TASK_DATE_INVALID,
        )

        planned_duration = parse_optional_int(raw_task.get("plannedDuration"))
        if "plannedDuration" in raw_task and (planned_duration is None or planned_duration <= 0):
            validation.error(
                CODE_TASK_PLANNED_DURATION_INVALID,
                f"{path}.plannedDuration",
                "plannedDuration は1以上の整数で指定してください",
            )

        progress = parse_optional_int(raw_task.get("progress"))
        has_progress_input = "progress" in raw_task
        if not has_progress_input:
            progress = 0
        elif progress is None or progress < 0 or progress > 100:
            validation.error(
                CODE_TASK_PROGRESS_INVALID,
                f"{path}.progress",
                "progress は0から100までの整数で指定してください",
            )

        issue = parse_optional_int(raw_task.get("issue"))
        comment = raw_task.get("comment")
        if not isinstance(comment, str):
            comment = None
        assignee = raw_task.get("assignee")
        if not isinstance(assignee, str):
            assignee = None

        if actual_start is not None and actual_end is not None and actual_end < actual_start:
            validation.error(
                CODE_TASK_ACTUAL_END_BEFORE_ACTUAL_START,
                f"{path}.actualEnd",
                "actualEnd は actualStart 以降の日付にしてください",
            )
        if actual_end is not None and actual_start is None:
            validation.error(
                CODE_TASK_ACTUAL_END_WITHOUT_ACTUAL_START,
                f"{path}.actualStart",
                "actualEnd があるタスクには actualStart を指定してください",
            )
        if actual_end is not None and progress != 100:
            validation.error(
                CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH,
                f"{path}.progress",
                "actualEnd があるタスクの progress は100にしてください",
            )
        if actual_end is None and progress == 100:
            validation.error(
                CODE_TASK_PROGRESS_COMPLETE_WITHOUT_ACTUAL_END,
                f"{path}.progress",
                "progress が100のタスクには actualEnd を指定してください",
            )

        tasks.append(
            Task(
                id=raw_id,
                name=name,
                planned_start=planned_start,
                planned_duration=planned_duration,
                actual_start=actual_start,
                actual_end=actual_end,
                progress=progress,
                has_progress_input=has_progress_input,
                issue=issue,
                comment=comment,
                assignee=assignee,
                source_index=index,
            )
        )

    return tasks


def parse_display_list(
    raw_values: Any,
    path: str,
    allowed_keys: set[str],
    validation: ValidationResult,
) -> tuple[str, ...]:
    if raw_values is DISPLAY_UNSET:
        return ("*",)
    if not isinstance(raw_values, list):
        validation.error(CODE_DISPLAY_INVALID, path, f"{path} は文字列配列で指定してください")
        return ("*",)
    if not raw_values:
        validation.error(CODE_DISPLAY_INVALID, path, f"{path} は1件以上の表示キーを指定してください")
        return ("*",)

    values: list[str] = []
    seen: set[str] = set()
    has_star = False
    has_normal_key = False
    has_exclusion = False

    for index, value in enumerate(raw_values):
        item_path = f"{path}[{index}]"
        if not isinstance(value, str) or value == "":
            validation.error(CODE_DISPLAY_INVALID, item_path, "表示キーは空でない文字列で指定してください")
            continue
        if value in seen:
            validation.error(CODE_DISPLAY_INVALID, item_path, "表示キーが重複しています")
            continue
        seen.add(value)

        if value == "*":
            has_star = True
            values.append(value)
            continue
        if value.startswith("-"):
            key = value[1:]
            if key not in allowed_keys:
                validation.error(CODE_DISPLAY_INVALID, item_path, "表示キーが不正です")
                continue
            has_exclusion = True
            values.append(value)
            continue
        if value not in allowed_keys:
            validation.error(CODE_DISPLAY_INVALID, item_path, "表示キーが不正です")
            continue
        has_normal_key = True
        values.append(value)

    if has_exclusion and not has_star:
        validation.error(CODE_DISPLAY_INVALID, path, "除外記法は * と同時に指定してください")
    if has_star and has_normal_key:
        validation.error(CODE_DISPLAY_INVALID, path, "* と通常の表示キーは同時に指定できません")

    return tuple(values) if values else ("*",)


def parse_column_widths(raw_column_widths: Any, path_prefix: str, validation: ValidationResult) -> dict[str, int]:
    if raw_column_widths is DISPLAY_UNSET:
        return {}
    if not isinstance(raw_column_widths, dict):
        validation.error(
            CODE_DISPLAY_INVALID,
            path_prefix,
            f"{path_prefix} はオブジェクトで指定してください",
        )
        return {}

    widths: dict[str, int] = {}
    for key, value in raw_column_widths.items():
        path = f"{path_prefix}.{key}"
        if key not in COLUMN_WIDTH_KEYS:
            validation.error(CODE_DISPLAY_INVALID, path, "列幅のキーが不正です")
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < MIN_COLUMN_WIDTH:
            validation.error(
                CODE_DISPLAY_INVALID,
                path,
                f"{path} は{MIN_COLUMN_WIDTH}以上の整数で指定してください",
            )
            continue
        widths[key] = value
    return widths


def parse_column_order(
    raw_order: Any, path: str, allowed_keys: tuple[str, ...], validation: ValidationResult
) -> tuple[str, ...]:
    if raw_order is DISPLAY_UNSET:
        return allowed_keys
    if not isinstance(raw_order, list):
        validation.error(CODE_DISPLAY_INVALID, path, f"{path} は文字列配列で指定してください")
        return allowed_keys
    values: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_order):
        item_path = f"{path}[{index}]"
        if not isinstance(value, str) or value not in allowed_keys:
            validation.error(CODE_DISPLAY_INVALID, item_path, "列順の列キーが不正です")
            continue
        if value in seen:
            validation.error(CODE_DISPLAY_INVALID, item_path, "列順の列キーが重複しています")
            continue
        seen.add(value)
        values.append(value)
    return tuple(values + [key for key in allowed_keys if key not in seen])


def parse_display_object(raw: Any, path: str, allowed: set[str], validation: ValidationResult) -> dict[str, Any]:
    if raw is DISPLAY_UNSET:
        return {}
    if not isinstance(raw, dict):
        validation.error(CODE_DISPLAY_INVALID, path, f"{path} はオブジェクトで指定してください")
        return {}
    for key in raw:
        if key not in allowed:
            validation.error(CODE_DISPLAY_INVALID, f"{path}.{key}", f"{path} のキーが不正です")
    return raw


def parse_display(raw_display: Any, validation: ValidationResult) -> DisplaySettings:
    if raw_display is None:
        return DisplaySettings()
    if not isinstance(raw_display, dict):
        validation.error(CODE_DISPLAY_INVALID, "display", "display はオブジェクトで指定してください")
        return DisplaySettings()
    for key in raw_display:
        if key not in {"standard", "analysis", "layers"}:
            validation.error(CODE_DISPLAY_INVALID, f"display.{key}", "display のキーが不正です")
    raw_layers = raw_display.get("layers", DISPLAY_UNSET)
    standard = parse_display_object(raw_display.get("standard", DISPLAY_UNSET), "display.standard", {"columns"}, validation)
    standard_columns = parse_display_object(standard.get("columns", DISPLAY_UNSET), "display.standard.columns", {"visible", "width", "order"}, validation)
    analysis = parse_display_object(raw_display.get("analysis", DISPLAY_UNSET), "display.analysis", {"columns"}, validation)
    analysis_columns = parse_display_object(analysis.get("columns", DISPLAY_UNSET), "display.analysis.columns", {"order"}, validation)
    layers = parse_display_object(raw_layers, "display.layers", {"visible"}, validation)
    return DisplaySettings(
        standard_columns=parse_display_list(
            standard_columns.get("visible", DISPLAY_UNSET),
            "display.standard.columns.visible",
            DISPLAY_COLUMN_KEYS,
            validation,
        ),
        standard_column_widths=parse_column_widths(
            standard_columns.get("width", DISPLAY_UNSET), "display.standard.columns.width", validation
        ),
        standard_column_order=parse_column_order(
            standard_columns.get("order", DISPLAY_UNSET), "display.standard.columns.order", STANDARD_COLUMN_ORDER, validation
        ),
        analysis_column_order=parse_column_order(
            analysis_columns.get("order", DISPLAY_UNSET), "display.analysis.columns.order", ANALYSIS_COLUMN_ORDER, validation
        ),
        layers=parse_display_list(
            layers.get("visible", DISPLAY_UNSET),
            "display.layers.visible",
            DISPLAY_LAYER_KEYS,
            validation,
        ),
    )


def parse_holidays(raw_holidays: Any, validation: ValidationResult) -> list[Holiday]:
    if raw_holidays is None:
        return []
    if not isinstance(raw_holidays, list):
        validation.error(CODE_HOLIDAYS_INVALID, "holidays", "holidays は配列で指定してください")
        return []

    holidays: list[Holiday] = []
    seen_dates: set[date] = set()

    for index, raw_holiday in enumerate(raw_holidays):
        path = f"holidays[{index}]"
        if not isinstance(raw_holiday, dict):
            validation.error(CODE_HOLIDAY_REQUIRED, path, "holiday はオブジェクトで指定してください")
            continue

        raw_date = raw_holiday.get("date")
        if raw_date is None:
            validation.error(
                CODE_HOLIDAY_DATE_INVALID,
                f"{path}.date",
                "日付は YYYY-MM-DD 形式の文字列で指定してください",
            )
            date_value = None
        else:
            date_value = parse_date_value(
                raw_date,
                f"{path}.date",
                validation,
                CODE_HOLIDAY_DATE_INVALID,
            )

        raw_name = raw_holiday.get("name")
        if raw_name is None or raw_name == "":
            name = None
        elif not isinstance(raw_name, str):
            validation.error(
                CODE_HOLIDAY_NAME_INVALID,
                f"{path}.name",
                "name は文字列で指定してください",
            )
            name = None
        else:
            name = raw_name

        if date_value is None:
            continue

        if date_value in seen_dates:
            validation.error(
                CODE_HOLIDAY_DATE_DUPLICATED,
                f"{path}.date",
                "date が重複しています",
            )
            continue
        seen_dates.add(date_value)

        holidays.append(Holiday(date=date_value, name=name))

    return holidays


def parse_milestones(raw_milestones: Any, validation: ValidationResult) -> list[Milestone]:
    if raw_milestones is None:
        return []
    if not isinstance(raw_milestones, list):
        validation.error(CODE_MILESTONES_INVALID, "milestones", "milestones は配列で指定してください")
        return []

    milestones: list[Milestone] = []
    seen: set[tuple[date, str]] = set()

    for index, raw_milestone in enumerate(raw_milestones):
        path = f"milestones[{index}]"
        if not isinstance(raw_milestone, dict):
            validation.error(CODE_MILESTONE_REQUIRED, path, "milestone はオブジェクトで指定してください")
            continue

        raw_date = raw_milestone.get("date")
        if raw_date is None:
            validation.error(
                CODE_MILESTONE_DATE_INVALID,
                f"{path}.date",
                "日付は YYYY-MM-DD 形式の文字列で指定してください",
            )
            date_value = None
        else:
            date_value = parse_date_value(
                raw_date,
                f"{path}.date",
                validation,
                CODE_MILESTONE_DATE_INVALID,
            )

        raw_name = raw_milestone.get("name")
        if not isinstance(raw_name, str) or not raw_name:
            validation.error(CODE_MILESTONE_NAME_REQUIRED, f"{path}.name", "milestone.name は必須です")
            continue

        if date_value is None:
            continue

        key = (date_value, raw_name)
        if key in seen:
            validation.warning(CODE_MILESTONE_DUPLICATED, path, "date と name が重複しています")
        seen.add(key)

        milestones.append(Milestone(date=date_value, name=raw_name, source_index=index))

    return milestones
