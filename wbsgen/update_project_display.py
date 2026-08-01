"""Project and display source JSON update operations."""

from __future__ import annotations

import copy

from .update_common import _clear_json_keys, _display, _project

PROJECT_FIELD_OPTIONS = {
    "name": "name", "start-date": "startDate", "end-date": "endDate",
    "status-date": "statusDate", "issue-base-url": "issueBaseUrl",
}
PROJECT_CLEAR_FIELDS = frozenset(PROJECT_FIELD_OPTIONS) - {"name"}


def update_project(data: dict[str, object], values: dict[str, object], clear_fields: set[str]) -> tuple[dict[str, object], str]:
    candidate = copy.deepcopy(data)
    project = _project(candidate)
    clear_json_keys = _clear_json_keys(values, clear_fields, PROJECT_FIELD_OPTIONS)
    project.update(values)
    for key in clear_json_keys:
        project.pop(key, None)
    return candidate, "updated project"


def show_project(data: dict[str, object]) -> dict[str, object]:
    return copy.deepcopy(_project(data))


def update_display_standard(data: dict[str, object], values: dict[str, object], clear_fields: set[str]) -> tuple[dict[str, object], str]:
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


def update_display_analysis(data: dict[str, object], values: dict[str, object], clear_fields: set[str]) -> tuple[dict[str, object], str]:
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


def update_display_layers(data: dict[str, object], values: dict[str, object], clear_fields: set[str]) -> tuple[dict[str, object], str]:
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
