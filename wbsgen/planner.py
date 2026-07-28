"""WBS planning, aggregation, and display calculations for WBS-GEN."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .models import ROW_HEIGHT
from .models import (
    BuildResult,
    ChartScale,
    ComputedTask,
    DisplaySettings,
    DisplayRow,
    Milestone,
    PlacedMilestone,
    Project,
    ProgressAnalysis,
    Task,
    WorkCalendar,
)
from .parser import parse_display, parse_holidays, parse_milestones, parse_project, parse_tasks
from .validation import *


__all__ = [
    "wbs_sort_key",
    "is_weekend",
    "iter_dates",
    "working_dates_between",
    "expected_progress_for_task",
    "progress_analysis_for_task",
    "progress_x_for_task",
    "calculate_planned_end",
    "parent_id_for",
    "task_source_path",
    "build_wbs_tree",
    "leaf_tasks",
    "compute_task",
    "compute_leaf_task",
    "aggregate_parent_task",
    "collect_computed_leaves",
    "compute_roots",
    "determine_display_range",
    "validate_display_range",
    "validate_milestone_range",
    "estimate_milestone_pill_width",
    "layout_milestones",
    "build_project_model",
    "flatten_computed_tasks",
    "is_delayed_task",
    "row_center_y",
    "status_date_right_x",
    "progress_point_for_row",
    "clamped_date",
]


def wbs_sort_key(task_id: str) -> tuple[int, ...]:
    return tuple(int(part) for part in task_id.split("."))


def is_weekend(value: date) -> bool:
    return value.weekday() >= 5


def iter_dates(start_date: date, end_date: date) -> list[date]:
    days = (end_date - start_date).days
    if days < 0:
        return []
    return [start_date + timedelta(days=offset) for offset in range(days + 1)]


def _is_non_working_day(value: date, calendar: WorkCalendar | None) -> bool:
    if calendar is not None:
        return calendar.is_non_working_day(value)
    return is_weekend(value)


def working_dates_between(
    start_date: date,
    end_date: date,
    calendar: WorkCalendar | None = None,
) -> list[date]:
    return [
        current
        for current in iter_dates(start_date, end_date)
        if not _is_non_working_day(current, calendar)
    ]


def expected_progress_for_task(
    task: ComputedTask,
    project: Project,
    calendar: WorkCalendar | None = None,
) -> int | None:
    if task.planned_start is None or task.planned_end is None:
        return None

    working_dates = working_dates_between(task.planned_start, task.planned_end, calendar)
    if not working_dates:
        return None

    status_date = project.status_date
    if status_date <= task.planned_start:
        return 0
    if status_date > task.planned_end:
        return 100

    elapsed = sum(1 for current in working_dates if current < status_date)
    return round(elapsed * 100 / len(working_dates))


def progress_analysis_for_task(
    task: ComputedTask,
    project: Project,
    calendar: WorkCalendar | None = None,
) -> ProgressAnalysis:
    if task.planned_start is None or task.planned_end is None:
        return ProgressAnalysis()

    expected_progress = expected_progress_for_task(task, project, calendar)
    if expected_progress is None:
        return ProgressAnalysis()

    delta = task.progress - expected_progress

    if delta >= 0:
        delay_business_days: int | None = 0
    else:
        planned_business_days = len(
            working_dates_between(task.planned_start, task.planned_end, calendar)
        )
        if planned_business_days == 0:
            delay_business_days = None
        else:
            delay_business_days = math.ceil(
                (expected_progress - task.progress) * planned_business_days / 100
            )

    if task.progress >= 100:
        return ProgressAnalysis(
            delta=delta,
            delay_business_days=delay_business_days,
            required_pace=0.0,
            pace_unattainable=False,
        )

    remaining_business_days = len(
        working_dates_between(project.status_date, task.planned_end, calendar)
    )
    if remaining_business_days <= 0:
        return ProgressAnalysis(
            delta=delta,
            delay_business_days=delay_business_days,
            required_pace=None,
            pace_unattainable=True,
        )

    required_pace = (100 - task.progress) / remaining_business_days
    return ProgressAnalysis(
        delta=delta,
        delay_business_days=delay_business_days,
        required_pace=required_pace,
        pace_unattainable=False,
    )


def progress_x_for_task(
    planned_start: date,
    planned_end: date,
    progress: int,
    status_date: date,
    scale: ChartScale,
    calendar: WorkCalendar | None = None,
) -> int:
    if progress <= 0:
        return scale.x_for_date(planned_start)
    if progress >= 100:
        return scale.x_for_date_end(status_date)

    working_dates = working_dates_between(planned_start, planned_end, calendar)
    if not working_dates:
        return scale.x_for_date(planned_start)

    total_width = len(working_dates) * scale.day_width
    progressed_width = round(total_width * progress / 100)
    remaining_width = progressed_width
    for current in working_dates:
        if remaining_width <= scale.day_width:
            return scale.x_for_date(current) + remaining_width
        remaining_width -= scale.day_width
    return scale.x_for_date_end(working_dates[-1])


def calculate_planned_end(
    planned_start: date,
    planned_duration: int,
    calendar: WorkCalendar | None = None,
) -> date:
    if planned_duration <= 0:
        raise ValueError("planned_duration must be positive")
    remaining_days = planned_duration
    current = planned_start
    while True:
        if not _is_non_working_day(current, calendar):
            remaining_days -= 1
            if remaining_days == 0:
                return current
        current += timedelta(days=1)


def parent_id_for(task_id: str) -> str | None:
    if "." not in task_id:
        return None
    return task_id.rsplit(".", 1)[0]


def task_source_path(task: Task, json_field: str | None = None) -> str:
    if task.source_index is None:
        return "tasks"
    path = f"tasks[{task.source_index}]"
    if json_field is not None:
        return f"{path}.{json_field}"
    return path


def build_wbs_tree(tasks: list[Task], validation: ValidationResult) -> list[Task]:
    tasks_by_id = {task.id: task for task in tasks}

    for task in tasks:
        parts = task.id.split(".")
        for index in range(1, len(parts)):
            ancestor_id = ".".join(parts[:index])
            if ancestor_id in tasks_by_id:
                continue
            tasks_by_id[ancestor_id] = Task(
                id=ancestor_id,
                name="タスクを定義してください",
                source_index=None,
                generated=True,
            )
            warning_path = (
                f"tasks[{task.source_index}].id"
                if task.source_index is not None
                else "tasks"
            )
            validation.warning(
                CODE_MISSING_PARENT_TASK,
                warning_path,
                f"親タスク {ancestor_id} を補完しました",
            )

    all_tasks = list(tasks_by_id.values())
    for task in all_tasks:
        task.children.clear()

    roots: list[Task] = []
    for task in sorted(all_tasks, key=lambda item: wbs_sort_key(item.id)):
        parent_id = parent_id_for(task.id)
        if parent_id is None:
            roots.append(task)
        else:
            tasks_by_id[parent_id].children.append(task)

    parent_fields = [
        ("planned_start", "plannedStart"),
        ("planned_duration", "plannedDuration"),
        ("actual_start", "actualStart"),
        ("actual_end", "actualEnd"),
        ("progress", "progress"),
    ]
    for task in sorted(all_tasks, key=lambda item: wbs_sort_key(item.id)):
        if not task.children or task.generated:
            continue
        for attribute_name, json_field in parent_fields:
            if attribute_name == "progress":
                has_field_value = task.has_progress_input
            else:
                has_field_value = getattr(task, attribute_name) is not None
            if has_field_value:
                validation.warning(
                    CODE_PARENT_FIELD_IGNORED,
                    task_source_path(task, json_field),
                    f"親タスク {task.id} の {json_field} は集計時に無視されます",
                )

    return roots


def leaf_tasks(task: Task) -> list[Task]:
    if not task.children:
        return [task]
    leaves: list[Task] = []
    for child in task.children:
        leaves.extend(leaf_tasks(child))
    return leaves


def compute_task(
    task: Task,
    validation: ValidationResult,
    status_date: date,
    calendar: WorkCalendar | None = None,
) -> ComputedTask:
    computed_children = [
        compute_task(child, validation, status_date, calendar) for child in task.children
    ]
    if computed_children:
        return aggregate_parent_task(task, computed_children)
    return compute_leaf_task(task, validation, status_date, calendar)


def compute_leaf_task(
    task: Task,
    validation: ValidationResult,
    status_date: date,
    calendar: WorkCalendar | None = None,
) -> ComputedTask:
    actual_end = task.actual_end

    planned_start = task.planned_start
    planned_duration = task.planned_duration
    planned_end: date | None = None
    if planned_start is None or planned_duration is None:
        validation.warning(
            CODE_TASK_UNPLANNED,
            task_source_path(task),
            f"タスク {task.id} は plannedStart または plannedDuration が未指定です",
        )
    elif planned_duration <= 0:
        pass
    else:
        if calendar is not None and planned_start in calendar.holiday_dates:
            validation.warning(
                CODE_TASK_PLANNED_START_NON_WORKING_DAY,
                task_source_path(task, "plannedStart"),
                "plannedStart が休日です",
            )
        elif is_weekend(planned_start):
            validation.warning(
                CODE_TASK_PLANNED_START_WEEKEND,
                task_source_path(task, "plannedStart"),
                "plannedStart が土日です",
            )
        planned_end = calculate_planned_end(planned_start, planned_duration, calendar)

    return ComputedTask(
        id=task.id,
        name=task.name,
        source_task=task,
        planned_start=planned_start if planned_end is not None else None,
        planned_end=planned_end,
        planned_duration=planned_duration if planned_end is not None else None,
        actual_start=task.actual_start,
        actual_end=actual_end,
        progress=0 if task.progress is None else task.progress,
        issue=task.issue,
        comment=task.comment,
        assignee=task.assignee,
        generated=task.generated,
    )


def aggregate_parent_task(task: Task, children: list[ComputedTask]) -> ComputedTask:
    leaves = collect_computed_leaves(children)
    planned_children = [
        child
        for child in leaves
        if child.planned_start is not None
        and child.planned_end is not None
        and child.planned_duration is not None
    ]
    actual_start_values = [
        child.actual_start for child in leaves if child.actual_start is not None
    ]
    all_leaves_complete = bool(leaves) and all(
        child.source_task.actual_end is not None for child in leaves
    )
    actual_end_values = [
        child.actual_end for child in leaves if child.actual_end is not None
    ]

    planned_duration = (
        sum(child.planned_duration for child in planned_children)
        if planned_children
        else None
    )
    progress = 0
    if planned_children and planned_duration:
        progress = round(
            sum(child.progress * child.planned_duration for child in planned_children)
            / planned_duration
        )

    return ComputedTask(
        id=task.id,
        name=task.name,
        source_task=task,
        planned_start=min(
            (child.planned_start for child in planned_children),
            default=None,
        ),
        planned_end=max((child.planned_end for child in planned_children), default=None),
        planned_duration=planned_duration,
        actual_start=min(actual_start_values) if actual_start_values else None,
        actual_end=max(actual_end_values)
        if all_leaves_complete and actual_end_values
        else None,
        progress=progress,
        issue=task.issue,
        comment=task.comment,
        assignee=task.assignee,
        generated=task.generated,
        children=children,
    )


def collect_computed_leaves(tasks: list[ComputedTask]) -> list[ComputedTask]:
    leaves: list[ComputedTask] = []
    for task in tasks:
        if not task.children:
            leaves.append(task)
        else:
            leaves.extend(collect_computed_leaves(task.children))
    return leaves


def compute_roots(
    roots: list[Task],
    validation: ValidationResult,
    status_date: date,
    calendar: WorkCalendar | None = None,
) -> list[ComputedTask]:
    return [compute_task(root, validation, status_date, calendar) for root in roots]


def determine_display_range(
    project: Project | None,
    computed_roots: list[ComputedTask],
) -> tuple[date | None, date | None]:
    if project is None:
        return None, None
    if project.start_date is not None and project.end_date is not None:
        return project.start_date, project.end_date

    dates: list[date] = [project.status_date]
    if project.start_date is not None:
        dates.append(project.start_date)
    if project.end_date is not None:
        dates.append(project.end_date)
    for task in collect_computed_leaves(computed_roots):
        for value in (
            task.planned_start,
            task.planned_end,
            task.actual_start,
            task.actual_end,
        ):
            if value is not None:
                dates.append(value)

    return project.start_date or min(dates), project.end_date or max(dates)


def validate_display_range(
    project: Project | None,
    computed_roots: list[ComputedTask],
    display_start_date: date | None,
    display_end_date: date | None,
    validation: ValidationResult,
) -> None:
    if project is None or display_start_date is None or display_end_date is None:
        return

    if project.status_date < display_start_date or project.status_date > display_end_date:
        validation.warning(
            CODE_PROJECT_STATUS_DATE_OUT_OF_RANGE,
            "project.statusDate",
            "statusDate がガント表示範囲外です",
        )

    for task in collect_computed_leaves(computed_roots):
        date_fields = [
            ("plannedStart", task.planned_start),
            ("plannedEnd", task.planned_end),
            ("actualStart", task.actual_start),
            ("actualEnd", task.actual_end),
        ]
        for json_field, value in date_fields:
            if value is None:
                continue
            if value < display_start_date or value > display_end_date:
                validation.warning(
                    CODE_TASK_DATE_OUT_OF_RANGE,
                    task_source_path(task.source_task, json_field),
                    f"タスク {task.id} の日付がガント表示範囲外です",
                )


def validate_milestone_range(
    milestones: list[Milestone],
    display_start_date: date | None,
    display_end_date: date | None,
    validation: ValidationResult,
) -> None:
    if display_start_date is None or display_end_date is None:
        return
    for milestone in milestones:
        if milestone.date < display_start_date or milestone.date > display_end_date:
            path = (
                f"milestones[{milestone.source_index}].date"
                if milestone.source_index is not None
                else "milestones"
            )
            validation.warning(
                CODE_MILESTONE_DATE_OUT_OF_RANGE,
                path,
                f"マイルストーン {milestone.name} の日付がガント表示範囲外です",
            )


# ピル幅の保守的な見積もり（px）。フォント10pxを前提に、全角10px・半角5pxで概算する。
MILESTONE_MARKER_HALF_WIDTH = 8
MILESTONE_PILL_OFFSET = 9
MILESTONE_PILL_SPACING = 8
MILESTONE_PILL_PADDING = 16


def estimate_milestone_pill_width(name: str) -> int:
    text_width = sum(10 if ord(character) > 0xFF else 5 for character in name)
    return text_width + MILESTONE_PILL_PADDING


def layout_milestones(
    milestones: list[Milestone],
    scale: ChartScale,
) -> list[PlacedMilestone]:
    in_range = [
        milestone
        for milestone in milestones
        if scale.start_date <= milestone.date <= scale.end_date
    ]
    ordered = sorted(
        enumerate(in_range),
        key=lambda item: (item[1].date, item[0]),
    )
    tier_ends: list[int] = []
    placed: list[PlacedMilestone] = []
    for _, milestone in ordered:
        x = scale.x_for_date_end(milestone.date)
        start = x - MILESTONE_MARKER_HALF_WIDTH
        end = x + MILESTONE_PILL_OFFSET + estimate_milestone_pill_width(milestone.name) + MILESTONE_PILL_SPACING
        tier = next(
            (index for index, tier_end in enumerate(tier_ends) if start >= tier_end),
            None,
        )
        if tier is None:
            tier = len(tier_ends)
            tier_ends.append(end)
        else:
            tier_ends[tier] = end
        placed.append(PlacedMilestone(milestone=milestone, tier=tier, x=x))
    return placed


def build_project_model(data: dict[str, Any], today: date | None = None) -> BuildResult:
    validation = ValidationResult()
    effective_today = date.today() if today is None else today
    project = parse_project(data.get("project"), validation, effective_today)
    tasks = parse_tasks(data.get("tasks"), validation)
    if "display" in data and data["display"] is None:
        validation.error(CODE_DISPLAY_INVALID, "display", "display はオブジェクトで指定してください")
        display_settings = DisplaySettings()
    else:
        display_settings = parse_display(data.get("display"), validation)
    holidays = parse_holidays(data.get("holidays"), validation)
    milestones = parse_milestones(data.get("milestones"), validation)
    calendar = WorkCalendar(holidays=tuple(holidays))
    roots = build_wbs_tree(tasks, validation)
    computed_roots: list[ComputedTask] = []
    display_start_date: date | None = None
    display_end_date: date | None = None
    if project is not None:
        computed_roots = compute_roots(roots, validation, project.status_date, calendar)
        display_start_date, display_end_date = determine_display_range(
            project,
            computed_roots,
        )
        validate_display_range(
            project,
            computed_roots,
            display_start_date,
            display_end_date,
            validation,
        )
        validate_milestone_range(
            milestones,
            display_start_date,
            display_end_date,
            validation,
        )

    return BuildResult(
        project=project,
        tasks=tasks,
        roots=roots,
        computed_roots=computed_roots,
        display_start_date=display_start_date,
        display_end_date=display_end_date,
        validation=validation,
        holidays=holidays,
        milestones=milestones,
        display_settings=display_settings,
    )


def flatten_computed_tasks(
    tasks: list[ComputedTask],
    depth: int = 0,
) -> list[DisplayRow]:
    rows: list[DisplayRow] = []
    for task in tasks:
        rows.append(DisplayRow(task=task, depth=depth))
        rows.extend(flatten_computed_tasks(task.children, depth + 1))
    return rows


def is_delayed_task(
    task: ComputedTask,
    project: Project,
    scale: ChartScale,
    calendar: WorkCalendar | None = None,
) -> bool:
    if task.planned_start is None or task.planned_end is None:
        return False
    if task.progress >= 100:
        return False
    progress_x = progress_x_for_task(
        task.planned_start,
        task.planned_end,
        task.progress,
        project.status_date,
        scale,
        calendar,
    )
    status_x = scale.x_for_date(
        clamped_date(project.status_date, scale.start_date, scale.end_date)
    )
    return progress_x < status_x


def row_center_y(row_index: int) -> int:
    return row_index * ROW_HEIGHT + ROW_HEIGHT // 2


def status_date_right_x(project: Project, scale: ChartScale) -> int:
    status_date = clamped_date(project.status_date, scale.start_date, scale.end_date)
    return scale.x_for_date_end(status_date)


def clamp_chart_x(value: int, scale: ChartScale) -> int:
    return min(max(value, 0), scale.chart_width)


def progress_point_for_row(
    row: DisplayRow,
    row_index: int,
    scale: ChartScale,
    project: Project,
    calendar: WorkCalendar | None = None,
) -> tuple[int, int, str] | None:
    task = row.task
    if task.planned_start is None or task.planned_end is None:
        return None
    expected_progress = expected_progress_for_task(task, project, calendar)
    if task.progress <= 0 and expected_progress == 0:
        x = status_date_right_x(project, scale)
    else:
        x = progress_x_for_task(
            task.planned_start,
            task.planned_end,
            task.progress,
            project.status_date,
            scale,
            calendar,
        )
    x = clamp_chart_x(x, scale)
    return (x, row_center_y(row_index), task.id)


def clamped_date(
    value: date,
    display_start_date: date,
    display_end_date: date,
) -> date:
    return min(max(value, display_start_date), display_end_date)
