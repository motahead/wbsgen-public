"""Backward-compatible public facade for source JSON update operations."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from .source import atomic_write_text as _atomic_write_text
from .update_calendar import (
    add_holiday,
    add_milestone,
    merge_holidays,
    remove_holiday,
    remove_milestone,
    show_holidays,
    show_milestones,
    update_holiday,
    update_milestone,
)
from .update_project_display import (
    PROJECT_CLEAR_FIELDS,
    PROJECT_FIELD_OPTIONS,
    show_display,
    show_project,
    update_display_analysis,
    update_display_layers,
    update_display_standard,
    update_project,
)
from .update_tasks import (
    TASK_CLEAR_FIELDS,
    TASK_FIELD_OPTIONS,
    add_task,
    move_task,
    next_task_id,
    remove_task,
    show_task,
    update_task,
)

__all__ = [
    "TASK_FIELD_OPTIONS", "PROJECT_FIELD_OPTIONS", "TASK_CLEAR_FIELDS",
    "PROJECT_CLEAR_FIELDS", "next_task_id", "add_task", "show_task",
    "remove_task", "update_task", "update_project", "show_project",
    "move_task", "add_holiday", "update_holiday", "merge_holidays",
    "remove_holiday", "show_holidays", "update_display_analysis",
    "update_display_layers", "update_display_standard", "show_display",
    "add_milestone", "update_milestone", "remove_milestone", "show_milestones",
    "format_json", "format_diff", "atomic_write_text",
]


def format_json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def format_diff(before: str, after: str, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile=str(path), tofile=str(path), lineterm="\n",
        )
    )


def atomic_write_text(path: Path, content: str) -> None:
    """Write a JSON update through the shared atomic text writer."""

    try:
        _atomic_write_text(path, content)
    except OSError as exc:
        raise ValueError(f"failed to update JSON file: {path}") from exc
