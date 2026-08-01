"""Task-specific source JSON update operations."""

from __future__ import annotations

import copy
from datetime import date

from .models import ComputedTask, Task
from .planner import build_project_model
from .update_common import _clear_json_keys, _tasks

TASK_FIELD_OPTIONS = {
    "name": "name", "assignee": "assignee", "planned-start": "plannedStart",
    "planned-duration": "plannedDuration", "actual-start": "actualStart",
    "actual-end": "actualEnd", "progress": "progress", "issue": "issue",
    "comment": "comment",
}
TASK_CLEAR_FIELDS = frozenset(TASK_FIELD_OPTIONS) - {"name"}


def _source_tasks_by_id(data: dict[str, object]) -> dict[str, dict[str, object]]:
    return {task_id: task for task in _tasks(data) if isinstance(task, dict)
            and isinstance((task_id := task.get("id")), str)}


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


_COMPLEMENT_FIELDS = (("plannedStart", "planned_start"), ("plannedEnd", "planned_end"),
                      ("plannedDuration", "planned_duration"), ("actualStart", "actual_start"),
                      ("actualEnd", "actual_end"), ("progress", "progress"))


def _complement_task_dict(base: dict[str, object], computed: ComputedTask) -> dict[str, object]:
    for json_key, attr in _COMPLEMENT_FIELDS:
        if json_key not in base and (value := getattr(computed, attr)) is not None:
            base[json_key] = value.isoformat() if isinstance(value, date) else value
    return base


def show_task(data: dict[str, object], task_id: str, *, direct: bool, complement: bool) -> dict[str, object]:
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
            result_dict = {"id": task.id, "name": task.name, "generated": True} if task.source_index is None else copy.deepcopy(source_tasks[item_id])
            computed = computed_tasks.get(item_id)
            return _complement_task_dict(result_dict, computed) if computed is not None else result_dict
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
                source_index_by_id[task.id] = min(first_source_index(child) for child in task.children)
            return source_index_by_id[task.id]
        child_ids = [child.id for child in sorted(descendants(model_tasks[task_id]), key=lambda child: (first_source_index(child), 0 if child.source_index is None else 1))]
    else:
        child_ids = [task["id"] for task in _tasks(data) if isinstance(task, dict)
                     and isinstance(task.get("id"), str) and task["id"].startswith(f"{task_id}.")
                     and (not direct or task["id"].count(".") == task_id.count(".") + 1)]
    return {"scope": "direct" if direct else "all", "parents": [to_dict(item_id) for item_id in parent_ids],
            "task": to_dict(task_id), "children": [to_dict(item_id) for item_id in child_ids]}


def next_task_id(data: dict[str, object], parent_id: str | None) -> str:
    tasks = _tasks(data)
    if parent_id is not None and parent_id not in _source_tasks_by_id(data):
        raise ValueError(f"parent task id not found: {parent_id}")
    prefix = "" if parent_id is None else f"{parent_id}."
    candidates: list[int] = []
    for task in tasks:
        if not isinstance(task, dict) or not isinstance((task_id := task.get("id")), str):
            continue
        if parent_id is None:
            if "." in task_id:
                continue
            suffix = task_id
        elif task_id.startswith(prefix):
            suffix = task_id.removeprefix(prefix)
        else:
            continue
        if suffix.isascii() and suffix.isdecimal() and not suffix.startswith("0"):
            candidates.append(int(suffix))
    number = max(candidates, default=0) + 1
    return str(number) if parent_id is None else f"{parent_id}.{number}"


def add_task(data: dict[str, object], task_id: str, values: dict[str, object]) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    tasks = _tasks(candidate)
    if any(isinstance(task, dict) and task.get("id") == task_id for task in tasks):
        raise ValueError(f"task id already exists: {task_id}")
    tasks.append({"id": task_id, **values})
    return candidate, f"added task {task_id}"


def update_task(data: dict[str, object], task_id: str, values: dict[str, object], clear_fields: set[str]) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    tasks = _tasks(candidate)
    clear_json_keys = _clear_json_keys(values, clear_fields, TASK_FIELD_OPTIONS)
    task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == task_id), None)
    if task is None:
        raise ValueError(f"task id not found: {task_id}")
    task.update(values)
    for key in clear_json_keys:
        task.pop(key, None)
    return candidate, f"updated task {task_id}"


def remove_task(data: dict[str, object], task_id: str, *, recursive: bool) -> tuple[dict[str, object], list[dict[str, object]]]:
    source_tasks = _source_tasks_by_id(data)
    if task_id not in source_tasks:
        raise ValueError(f"task id not found in source JSON: {task_id}")
    deleted_ids = {item_id for item_id in source_tasks if item_id == task_id or item_id.startswith(f"{task_id}.")}
    if len(deleted_ids) > 1 and not recursive:
        raise ValueError(f"task has descendants; use --recursive: {task_id}")
    candidate = copy.deepcopy(data)
    candidate_tasks = _tasks(candidate)
    candidate_tasks[:] = [task for task in candidate_tasks if not (isinstance(task, dict) and task.get("id") in deleted_ids)]
    deleted = [copy.deepcopy(task) for task in _tasks(data) if isinstance(task, dict) and task.get("id") in deleted_ids]
    return candidate, deleted


def move_task(data: dict[str, object], old_id: str, new_id: str) -> tuple[dict[str, object], str]:
    if old_id == new_id:
        raise ValueError("source and destination task IDs must differ")
    if new_id.startswith(f"{old_id}."):
        raise ValueError("cannot move a task below itself")
    source_tasks = _source_tasks_by_id(data)
    if old_id not in source_tasks:
        raise ValueError(f"task id not found in source JSON: {old_id}")
    moved_ids = {task_id for task_id in source_tasks if task_id == old_id or task_id.startswith(f"{old_id}.")}
    replacements = {task_id: f"{new_id}{task_id[len(old_id):]}" for task_id in moved_ids}
    if any(replacement in source_tasks and replacement not in moved_ids for replacement in replacements.values()):
        raise ValueError(f"task id already exists: {new_id}")
    candidate = copy.deepcopy(data)
    for task in _tasks(candidate):
        if isinstance(task, dict) and isinstance((task_id := task.get("id")), str) and task_id in replacements:
            task["id"] = replacements[task_id]
    return candidate, f"moved task {old_id} to {new_id}"
