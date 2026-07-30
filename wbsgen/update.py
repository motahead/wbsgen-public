"""Helpers for safely updating a WBS-GEN source JSON document."""

from __future__ import annotations

import copy
import difflib
import json
from datetime import date
from pathlib import Path

from .models import ComputedTask, Task
from .parser import parse_holidays
from .planner import build_project_model
from .source import atomic_write_text as _atomic_write_text
from .validation import ValidationResult

__all__ = [
    "TASK_FIELD_OPTIONS",
    "PROJECT_FIELD_OPTIONS",
    "TASK_CLEAR_FIELDS",
    "PROJECT_CLEAR_FIELDS",
    "next_task_id",
    "add_task",
    "show_task",
    "remove_task",
    "update_task",
    "update_project",
    "show_project",
    "move_task",
    "add_holiday",
    "update_holiday",
    "merge_holidays",
    "remove_holiday",
    "show_holidays",
    "update_display_analysis",
    "update_display_layers",
    "update_display_standard",
    "show_display",
    "add_milestone",
    "update_milestone",
    "remove_milestone",
    "show_milestones",
    "format_json",
    "format_diff",
    "atomic_write_text",
]

TASK_FIELD_OPTIONS = {
    "name": "name",
    "assignee": "assignee",
    "planned-start": "plannedStart",
    "planned-duration": "plannedDuration",
    "actual-start": "actualStart",
    "actual-end": "actualEnd",
    "progress": "progress",
    "issue": "issue",
    "comment": "comment",
}
PROJECT_FIELD_OPTIONS = {
    "name": "name",
    "start-date": "startDate",
    "end-date": "endDate",
    "status-date": "statusDate",
    "issue-base-url": "issueBaseUrl",
}
TASK_CLEAR_FIELDS = frozenset(TASK_FIELD_OPTIONS) - {"name"}
PROJECT_CLEAR_FIELDS = frozenset(PROJECT_FIELD_OPTIONS) - {"name"}


def _project(data: dict[str, object]) -> dict[str, object]:
    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError("project must be an object")
    return project


def _tasks(data: dict[str, object]) -> list[object]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("tasks must be an array")
    return tasks


def _generated_task_dict(task: Task) -> dict[str, object]:
    return {"id": task.id, "name": task.name, "generated": True}


def _source_tasks_by_id(data: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        task_id: task
        for task in _tasks(data)
        if isinstance(task, dict) and isinstance((task_id := task.get("id")), str)
    }


def _all_model_tasks(data: dict[str, object]) -> dict[str, Task]:
    result = build_project_model(data)
    tasks_by_id = {task.id: task for task in result.tasks}

    def visit(task: Task) -> None:
        tasks_by_id[task.id] = task
        for child in task.children:
            visit(child)

    for root in result.roots:
        visit(root)
    return tasks_by_id


def _all_computed_tasks(data: dict[str, object]) -> dict[str, ComputedTask]:
    result = build_project_model(data)
    tasks_by_id: dict[str, ComputedTask] = {}

    def visit(task: ComputedTask) -> None:
        tasks_by_id[task.id] = task
        for child in task.children:
            visit(child)

    for root in result.computed_roots:
        visit(root)
    return tasks_by_id


_COMPLEMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("plannedStart", "planned_start"),
    ("plannedEnd", "planned_end"),
    ("plannedDuration", "planned_duration"),
    ("actualStart", "actual_start"),
    ("actualEnd", "actual_end"),
    ("progress", "progress"),
)


def _complement_task_dict(base: dict[str, object], computed: ComputedTask) -> dict[str, object]:
    for json_key, attr in _COMPLEMENT_FIELDS:
        if json_key in base:
            continue
        value = getattr(computed, attr)
        if value is None:
            continue
        if isinstance(value, date):
            value = value.isoformat()
        base[json_key] = value
    return base


def show_task(
    data: dict[str, object], task_id: str, *, direct: bool, complement: bool
) -> dict[str, object]:
    source_tasks = _source_tasks_by_id(data)
    if not complement:
        if task_id not in source_tasks:
            raise ValueError(f"task id not found: {task_id}")

        def to_dict(item_id: str) -> dict[str, object]:
            return copy.deepcopy(source_tasks[item_id])

        known_ids = set(source_tasks)
    else:
        model_tasks = _all_model_tasks(data)
        if task_id not in model_tasks:
            raise ValueError(f"task id not found: {task_id}")

        computed_tasks = _all_computed_tasks(data)

        def to_dict(item_id: str) -> dict[str, object]:
            task = model_tasks[item_id]
            if task.source_index is None:
                result_dict = _generated_task_dict(task)
            else:
                result_dict = copy.deepcopy(source_tasks[item_id])
            computed = computed_tasks.get(item_id)
            if computed is not None:
                _complement_task_dict(result_dict, computed)
            return result_dict

        known_ids = set(model_tasks)

    parent_ids: list[str] = []
    parent_id = task_id.rsplit(".", 1)[0] if "." in task_id else None
    while parent_id is not None:
        if parent_id in known_ids:
            parent_ids.append(parent_id)
        parent_id = parent_id.rsplit(".", 1)[0] if "." in parent_id else None
    parent_ids.reverse()
    if direct:
        parent_ids = parent_ids[-1:]

    if complement:
        def descendants(task: Task) -> list[Task]:
            result: list[Task] = []
            for child in task.children:
                result.append(child)
                if not direct:
                    result.extend(descendants(child))
            return result

        source_index_by_id: dict[str, int] = {}

        def first_source_index(task: Task) -> int:
            if task.source_index is not None:
                return task.source_index
            if task.id not in source_index_by_id:
                source_index_by_id[task.id] = min(
                    first_source_index(child) for child in task.children
                )
            return source_index_by_id[task.id]

        child_ids = [
            child.id
            for child in sorted(
                descendants(model_tasks[task_id]),
                key=lambda child: (
                    first_source_index(child),
                    0 if child.source_index is None else 1,
                ),
            )
        ]
    else:
        child_ids = [
            task["id"]
            for task in _tasks(data)
            if isinstance(task, dict)
            and isinstance(task.get("id"), str)
            and task["id"].startswith(f"{task_id}.")
            and (not direct or task["id"].count(".") == task_id.count(".") + 1)
        ]

    return {
        "scope": "direct" if direct else "all",
        "parents": [to_dict(item_id) for item_id in parent_ids],
        "task": to_dict(task_id),
        "children": [to_dict(item_id) for item_id in child_ids],
    }


def remove_task(
    data: dict[str, object], task_id: str, *, recursive: bool
) -> tuple[dict[str, object], list[dict[str, object]]]:
    source_tasks = _source_tasks_by_id(data)
    if task_id not in source_tasks:
        raise ValueError(f"task id not found in source JSON: {task_id}")

    deleted_ids = {
        item_id for item_id in source_tasks if item_id == task_id or item_id.startswith(f"{task_id}.")
    }
    if len(deleted_ids) > 1 and not recursive:
        raise ValueError(f"task has descendants; use --recursive: {task_id}")

    candidate = copy.deepcopy(data)
    candidate_tasks = _tasks(candidate)
    candidate_tasks[:] = [
        task
        for task in candidate_tasks
        if not (isinstance(task, dict) and task.get("id") in deleted_ids)
    ]
    deleted = [
        copy.deepcopy(task)
        for task in _tasks(data)
        if isinstance(task, dict) and task.get("id") in deleted_ids
    ]
    return candidate, deleted


def _clear_json_keys(
    values: dict[str, object], clear_fields: set[str], field_options: dict[str, str]
) -> set[str]:
    for field in clear_fields:
        if field not in field_options or field == "name":
            raise ValueError(f"invalid field for --clear: {field}")

    clear_json_keys = {field_options[field] for field in clear_fields}
    conflicts = set(values).intersection(clear_json_keys)
    if conflicts:
        json_key = sorted(conflicts)[0]
        option_name = next(
            option for option, candidate_key in field_options.items() if candidate_key == json_key
        )
        raise ValueError(f"cannot both set and clear: {option_name}")
    if not values and not clear_fields:
        raise ValueError("at least one field must be set or cleared")
    return clear_json_keys


def next_task_id(data: dict[str, object], parent_id: str | None) -> str:
    """Return the next direct child ID, or the next top-level ID."""

    tasks = _tasks(data)
    if parent_id is not None and parent_id not in _source_tasks_by_id(data):
        raise ValueError(f"parent task id not found: {parent_id}")

    prefix = "" if parent_id is None else f"{parent_id}."
    candidates: list[int] = []
    for task in tasks:
        if not isinstance(task, dict) or not isinstance((task_id := task.get("id")), str):
            continue
        if parent_id is None:
            suffix = task_id
            if "." in task_id:
                continue
        else:
            if not task_id.startswith(prefix):
                continue
            suffix = task_id.removeprefix(prefix)
        if suffix.isascii() and suffix.isdecimal() and not suffix.startswith("0"):
            candidates.append(int(suffix))

    number = max(candidates, default=0) + 1
    return str(number) if parent_id is None else f"{parent_id}.{number}"


def add_task(
    data: dict[str, object], task_id: str, values: dict[str, object]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    tasks = _tasks(candidate)
    if any(isinstance(task, dict) and task.get("id") == task_id for task in tasks):
        raise ValueError(f"task id already exists: {task_id}")

    task = {"id": task_id, **values}
    tasks.append(task)
    return candidate, f"added task {task_id}"


def update_task(
    data: dict[str, object], task_id: str, values: dict[str, object], clear_fields: set[str]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    tasks = _tasks(candidate)
    clear_json_keys = _clear_json_keys(values, clear_fields, TASK_FIELD_OPTIONS)
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("id") == task_id),
        None,
    )
    if task is None:
        raise ValueError(f"task id not found: {task_id}")

    task.update(values)
    for key in clear_json_keys:
        task.pop(key, None)
    return candidate, f"updated task {task_id}"


def update_project(
    data: dict[str, object], values: dict[str, object], clear_fields: set[str]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    project = _project(candidate)
    clear_json_keys = _clear_json_keys(values, clear_fields, PROJECT_FIELD_OPTIONS)

    project.update(values)
    for key in clear_json_keys:
        project.pop(key, None)
    return candidate, "updated project"


def show_project(data: dict[str, object]) -> dict[str, object]:
    """Return a copy of stored project fields without derived values."""

    return copy.deepcopy(_project(data))


def move_task(
    data: dict[str, object], old_id: str, new_id: str
) -> tuple[dict[str, object], str]:
    """Move a source task and every source descendant by changing its ID prefix."""

    if old_id == new_id:
        raise ValueError("source and destination task IDs must differ")
    if new_id.startswith(f"{old_id}."):
        raise ValueError("cannot move a task below itself")
    source_tasks = _source_tasks_by_id(data)
    if old_id not in source_tasks:
        raise ValueError(f"task id not found in source JSON: {old_id}")
    moved_ids = {
        task_id for task_id in source_tasks
        if task_id == old_id or task_id.startswith(f"{old_id}.")
    }
    replacements = {
        task_id: f"{new_id}{task_id[len(old_id):]}" for task_id in moved_ids
    }
    if any(
        replacement in source_tasks and replacement not in moved_ids
        for replacement in replacements.values()
    ):
        raise ValueError(f"task id already exists: {new_id}")

    candidate = copy.deepcopy(data)
    for task in _tasks(candidate):
        if isinstance(task, dict) and isinstance((task_id := task.get("id")), str):
            if task_id in replacements:
                task["id"] = replacements[task_id]
    return candidate, f"moved task {old_id} to {new_id}"


def _holidays(data: dict[str, object], *, create: bool = False) -> list[object]:
    if create:
        holidays = data.setdefault("holidays", [])
    else:
        holidays = data.get("holidays", [])
    if not isinstance(holidays, list):
        raise ValueError("holidays must be an array")
    return holidays


def _find_holiday_index(holidays: list[object], date_text: str) -> int:
    for index, item in enumerate(holidays):
        if isinstance(item, dict) and item.get("date") == date_text:
            return index
    raise ValueError(f"holiday not found: {date_text}")


def add_holiday(
    data: dict[str, object], date_text: str, name: str | None
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate, create=True)
    if any(
        isinstance(item, dict) and item.get("date") == date_text
        for item in holidays
    ):
        raise ValueError(f"holiday already exists: {date_text}")
    holiday: dict[str, object] = {"date": date_text}
    if name is not None:
        holiday["name"] = name
    holidays.append(holiday)
    return candidate, f"added holiday {date_text}"


def update_holiday(
    data: dict[str, object],
    date_text: str,
    name: str | None = None,
    clear_name: bool = False,
    *,
    new_date: str | None = None,
) -> tuple[dict[str, object], str]:
    if name is None and not clear_name and new_date is None:
        raise ValueError("must set or clear holiday name, or change the date")
    if name is not None and clear_name:
        raise ValueError("cannot both set and clear: name")
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate)
    target_index = _find_holiday_index(holidays, date_text)
    target = holidays[target_index]
    assert isinstance(target, dict)
    if new_date is not None and new_date != date_text:
        if any(
            index != target_index and isinstance(item, dict) and item.get("date") == new_date
            for index, item in enumerate(holidays)
        ):
            raise ValueError(f"holiday already exists: {new_date}")
        target["date"] = new_date
    if clear_name:
        target.pop("name", None)
    else:
        target["name"] = name
    return candidate, f"updated holiday {date_text}"


def remove_holiday(
    data: dict[str, object], date_text: str
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate)
    holidays.pop(_find_holiday_index(holidays, date_text))
    return candidate, f"removed holiday {date_text}"


def show_holidays(data: dict[str, object]) -> list[dict[str, object]]:
    holidays = [item for item in _holidays(data) if isinstance(item, dict)]
    return sorted(
        copy.deepcopy(holidays),
        key=lambda item: str(item.get("date", "")),
    )


def merge_holidays(
    data: dict[str, object], supplemental: dict[str, object]
) -> tuple[dict[str, object], str]:
    """Merge validated supplemental holidays, preferring its entry per date."""

    if not isinstance(supplemental, dict):
        raise ValueError("invalid supplemental holidays: root must be an object")

    validation = ValidationResult()
    supplemental_holidays = parse_holidays(supplemental.get("holidays"), validation)
    if validation.has_errors:
        raise ValueError("invalid supplemental holidays")

    candidate = copy.deepcopy(data)
    holidays = _holidays(candidate, create=True)
    by_date = {
        item["date"]: index
        for index, item in enumerate(holidays)
        if isinstance(item, dict) and isinstance(item.get("date"), str)
    }
    for holiday in supplemental_holidays:
        item: dict[str, object] = {"date": holiday.date.isoformat()}
        if holiday.name is not None:
            item["name"] = holiday.name
        index = by_date.get(item["date"])
        if index is None:
            by_date[item["date"]] = len(holidays)
            holidays.append(item)
        else:
            holidays[index] = item
    return candidate, "merged holidays"


def _display(data: dict[str, object], *, create: bool = False) -> dict[str, object]:
    if create:
        display = data.setdefault("display", {})
    else:
        display = data.get("display", {})
    if not isinstance(display, dict):
        raise ValueError("display must be an object")
    return display


def update_display_standard(
    data: dict[str, object], values: dict[str, object], clear_fields: set[str]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    display = _display(candidate, create=True)
    fields = ("visible", "width", "order")
    if any(field in values or field in clear_fields for field in fields):
        standard = display.setdefault("standard", {})
        if not isinstance(standard, dict):
            raise ValueError("display.standard must be an object")
        columns = standard.setdefault("columns", {})
        if not isinstance(columns, dict):
            raise ValueError("display.standard.columns must be an object")
        for field in fields:
            if field in values:
                columns[field] = values[field]
            if field in clear_fields:
                columns.pop(field, None)
        if not columns:
            standard.pop("columns", None)
        if not standard:
            display.pop("standard", None)
    if not display:
        candidate.pop("display", None)
    return candidate, "updated display.standard"


def update_display_analysis(
    data: dict[str, object], values: dict[str, object], clear_fields: set[str]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    display = _display(candidate, create=True)
    if "order" in values or "order" in clear_fields:
        analysis = display.setdefault("analysis", {})
        if not isinstance(analysis, dict):
            raise ValueError("display.analysis must be an object")
        columns = analysis.setdefault("columns", {})
        if not isinstance(columns, dict):
            raise ValueError("display.analysis.columns must be an object")
        if "order" in values:
            columns["order"] = values["order"]
        if "order" in clear_fields:
            columns.pop("order", None)
        if not columns:
            analysis.pop("columns", None)
        if not analysis:
            display.pop("analysis", None)
    if not display:
        candidate.pop("display", None)
    return candidate, "updated display.analysis"


def update_display_layers(
    data: dict[str, object], values: dict[str, object], clear_fields: set[str]
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    display = _display(candidate, create=True)
    if "visible" in values or "visible" in clear_fields:
        layers = display.setdefault("layers", {})
        if not isinstance(layers, dict):
            raise ValueError("display.layers must be an object")
        if "visible" in values:
            layers["visible"] = values["visible"]
        if "visible" in clear_fields:
            layers.pop("visible", None)
        if not layers:
            display.pop("layers", None)
    if not display:
        candidate.pop("display", None)
    return candidate, "updated display.layers"


def show_display(data: dict[str, object]) -> dict[str, object]:
    return copy.deepcopy(_display(data))


def _milestones(data: dict[str, object], *, create: bool = False) -> list[object]:
    if create:
        milestones = data.setdefault("milestones", [])
    else:
        milestones = data.get("milestones", [])
    if not isinstance(milestones, list):
        raise ValueError("milestones must be an array")
    return milestones


def _find_milestone_index(
    milestones: list[object], name: str, date_text: str | None
) -> int:
    matches = [
        index
        for index, item in enumerate(milestones)
        if isinstance(item, dict)
        and item.get("name") == name
        and (date_text is None or item.get("date") == date_text)
    ]
    if not matches:
        raise ValueError(f"milestone not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"multiple milestones match: {name}; use --date to disambiguate")
    return matches[0]


def add_milestone(
    data: dict[str, object], date_text: str, name: str
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate, create=True)
    if any(
        isinstance(item, dict) and item.get("date") == date_text and item.get("name") == name
        for item in milestones
    ):
        raise ValueError(f"milestone already exists: {date_text} {name}")
    milestones.append({"date": date_text, "name": name})
    return candidate, f"added milestone {name}"


def update_milestone(
    data: dict[str, object],
    name: str,
    date_text: str | None,
    new_date: str | None,
    new_name: str | None,
) -> tuple[dict[str, object], str]:
    if new_date is None and new_name is None:
        raise ValueError("at least one of --new-date or --new-name must be set")
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate)
    index = _find_milestone_index(milestones, name, date_text)
    target = milestones[index]
    assert isinstance(target, dict)
    if new_date is not None:
        target["date"] = new_date
    if new_name is not None:
        target["name"] = new_name
    return candidate, f"updated milestone {name}"


def remove_milestone(
    data: dict[str, object], name: str, date_text: str | None
) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    milestones = _milestones(candidate)
    index = _find_milestone_index(milestones, name, date_text)
    milestones.pop(index)
    return candidate, f"removed milestone {name}"


def show_milestones(data: dict[str, object]) -> list[dict[str, object]]:
    milestones = [
        item for item in _milestones(data) if isinstance(item, dict)
    ]
    return sorted(
        copy.deepcopy(milestones),
        key=lambda item: str(item.get("date", "")),
    )


def format_json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def format_diff(before: str, after: str, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
            lineterm="\n",
        )
    )


def atomic_write_text(path: Path, content: str) -> None:
    """Write a JSON update through the shared atomic text writer."""

    try:
        _atomic_write_text(path, content)
    except OSError as exc:
        raise ValueError(f"failed to update JSON file: {path}") from exc
