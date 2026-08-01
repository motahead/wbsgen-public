"""Shared private helpers for source JSON update operations."""

from __future__ import annotations


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
            option for option, candidate_key in field_options.items()
            if candidate_key == json_key
        )
        raise ValueError(f"cannot both set and clear: {option_name}")
    if not values and not clear_fields:
        raise ValueError("at least one field must be set or cleared")
    return clear_json_keys


def _holidays(data: dict[str, object], *, create: bool = False) -> list[object]:
    holidays = data.setdefault("holidays", []) if create else data.get("holidays", [])
    if not isinstance(holidays, list):
        raise ValueError("holidays must be an array")
    return holidays


def _display(data: dict[str, object], *, create: bool = False) -> dict[str, object]:
    display = data.setdefault("display", {}) if create else data.get("display", {})
    if not isinstance(display, dict):
        raise ValueError("display must be an object")
    return display


def _milestones(data: dict[str, object], *, create: bool = False) -> list[object]:
    milestones = data.setdefault("milestones", []) if create else data.get("milestones", [])
    if not isinstance(milestones, list):
        raise ValueError("milestones must be an array")
    return milestones
