"""Text-table export rendering for WBS-GEN."""

from __future__ import annotations

import csv
import io
from urllib.parse import urlparse

from ..models import BuildResult, DisplayRow, Project, WorkCalendar
from ..planner import (
    expected_progress_for_task,
    flatten_computed_tasks,
    progress_analysis_for_task,
)

WBS_HEADERS = (
    "ID", "タスク名", "担当者", "計画開始", "計画終了", "実績開始", "実績終了",
    "進捗", "期待進捗", "差分", "遅れ(営業日)", "残り必要ペース", "Issue", "コメント",
)
PACE_UNATTAINABLE_LABEL = "達成不能"


def _format_date(value) -> str:
    return value.isoformat() if value is not None else ""


def _format_percent(value: int | None, *, signed: bool = False) -> str:
    if value is None:
        return ""
    return f"{value:+d}%" if signed else f"{value}%"


def _issue_value(issue: int | None, project: Project) -> str:
    if issue is None:
        return ""
    label = f"#{issue}"
    base_url = project.issue_base_url
    if base_url is None:
        return label
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return label
    return f"{base_url.rstrip('/')}/{issue}"


def _require_project(result: BuildResult) -> Project:
    if result.project is None or result.display_start_date is None or result.display_end_date is None:
        raise ValueError("cannot export WBS table without a valid project and display range")
    return result.project


def _row_for_task(row: DisplayRow, project: Project, calendar: WorkCalendar) -> tuple[str, ...]:
    task = row.task
    expected = expected_progress_for_task(task, project, calendar)
    analysis = progress_analysis_for_task(task, project, calendar)
    if analysis.pace_unattainable:
        pace = PACE_UNATTAINABLE_LABEL
    elif analysis.required_pace is None:
        pace = ""
    else:
        pace = f"{analysis.required_pace:.1f}%/日"
    delay = "" if analysis.delay_business_days is None else f"{analysis.delay_business_days}日"
    return (
        task.id, task.name, task.assignee or "", _format_date(task.planned_start),
        _format_date(task.planned_end), _format_date(task.actual_start),
        _format_date(task.source_task.actual_end), _format_percent(task.progress),
        _format_percent(expected), _format_percent(analysis.delta, signed=True), delay, pace,
        _issue_value(task.issue, project), task.comment or "",
    )


def build_wbs_rows(result: BuildResult) -> list[tuple[str, ...]]:
    """Return display-order WBS rows using the shared export columns."""

    project = _require_project(result)
    calendar = WorkCalendar(holidays=tuple(result.holidays))
    return [_row_for_task(row, project, calendar) for row in flatten_computed_tasks(result.computed_roots)]


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def render_markdown(result: BuildResult) -> str:
    """Render computed WBS rows as a GitHub Flavored Markdown table."""

    rows = [WBS_HEADERS, *build_wbs_rows(result)]
    lines = ["| " + " | ".join(_markdown_cell(value) for value in rows[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in WBS_HEADERS) + " |")
    for row in rows[1:]:
        cells = [_markdown_cell(value) for value in row]
        issue = row[12]
        if issue.startswith(("http://", "https://")):
            cells[12] = f"[#{issue.rsplit('/', 1)[-1]}]({issue})"
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_csv(result: BuildResult) -> str:
    """Render computed WBS rows as UTF-8 text suitable for CSV encoding."""

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(WBS_HEADERS)
    writer.writerows(build_wbs_rows(result))
    return output.getvalue()
