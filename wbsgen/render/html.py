"""HTML rendering for WBS-GEN."""

from __future__ import annotations

import json
import re
from datetime import date
from importlib import resources
from html import escape
from string import Template
from typing import Any
from urllib.parse import urlparse

from ..models import ACTUAL_BAR_HEIGHT, BAR_HEIGHT, DAY_WIDTH, MILESTONE_TIER_HEIGHT, MONTH_LABEL_MIN_DAYS
from ..models import DEFAULT_ASSIGNEE_WIDTH, DEFAULT_COMMENT_WIDTH, DEFAULT_TASK_NAME_WIDTH
from ..models import PROGRESS_BAR_HEIGHT, ROW_HEIGHT
from ..models import BuildResult, ChartScale, ComputedTask, DisplayRow, DisplaySettings, Holiday, Milestone, Project
from ..models import PlacedMilestone, ProgressAnalysis, Task
from ..models import WorkCalendar
from ..planner import clamped_date, expected_progress_for_task, flatten_computed_tasks
from ..planner import is_delayed_task, is_weekend
from ..planner import iter_dates, layout_milestones, parent_id_for, progress_analysis_for_task, progress_point_for_row
from ..planner import progress_x_for_task
from ..planner import status_date_right_x
from ..source import read_generated_at, read_generator_version
from ..validation import *


APP_NAME = "WBS-GEN"

ASSET_PACKAGE = "wbsgen.render.assets"
BOTTOM_FOOTER_HEIGHT = 32
GITHUB_REPO_URL = "https://github.com/motahead/wbsgen-public"
_RELEASE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def read_text_asset(name: str) -> str:
    return resources.files(ASSET_PACKAGE).joinpath(name).read_text(encoding="utf-8")


__all__ = [
    "APP_NAME",
    "read_text_asset",
    "format_date",
    "format_date_short",
    "format_period",
    "format_progress",
    "format_progress_delta",
    "format_delay_business_days",
    "format_required_pace",
    "render_issue",
    "escape_json_for_script",
    "serialize_source_json",
    "serialize_display_settings",
    "source_index_from_path",
    "warning_target_id",
    "warning_target_ids",
    "warning_codes_by_target",
    "render_warning_drawer",
    "render_warning_toggle",
    "render_holiday_window",
    "render_holiday_toggle",
    "task_bar_class",
    "display_row_class",
    "manual_url_for_version",
    "render_left_footer",
    "render_wbs_table",
    "render_inazuma",
    "style_for_rect",
    "render_bar",
    "render_clip_marker",
    "render_gantt_task_bars",
    "render_month_header",
    "render_day_header",
    "gantt_row_class",
    "milestone_band_height",
    "render_milestone_band",
    "render_milestone_lines",
    "render_gantt_chart",
    "render_html",
]


def row_task_attributes(
    row: DisplayRow,
    *,
    project: Project | None = None,
    scale: ChartScale | None = None,
    row_index: int | None = None,
    calendar: WorkCalendar | None = None,
) -> str:
    task = row.task
    attrs = [
        f'data-task-id="{escape(task.id, quote=True)}"',
        f'data-depth="{row.depth}"',
    ]
    parent_id = parent_id_for(task.id)
    if parent_id is not None:
        attrs.append(f'data-parent-id="{escape(parent_id, quote=True)}"')
    if task.children:
        attrs.append('data-has-children="true"')
    if scale is not None and project is not None:
        attrs.append(f'data-status-x="{status_date_right_x(project, scale)}"')
        attrs.append(f'data-row-height="{ROW_HEIGHT}"')
        if row_index is not None:
            point = progress_point_for_row(row, row_index, scale, project, calendar)
            if point is not None:
                progress_x, progress_y, _ = point
                attrs.append(f'data-progress-x="{progress_x}"')
                attrs.append(f'data-progress-y="{progress_y}"')
    return " ".join(attrs)


def render_tree_toggle(task: ComputedTask) -> str:
    if task.children:
        return (
            f'<button class="tree-toggle" type="button" data-task-id="{escape(task.id, quote=True)}" '
            'aria-expanded="true" title="子タスクを折りたたむ">▾</button>'
        )
    return '<span class="tree-toggle-spacer" aria-hidden="true"></span>'


def render_view_menu(generator_version: str | None) -> str:
    manual_url = manual_url_for_version(generator_version)
    return f"""<div class="view-controls" aria-label="表示・データ操作">
      <details class="view-menu">
        <summary aria-label="メニュー" title="メニュー">☰</summary>
        <div class="view-menu-panel" role="menu" aria-label="操作メニュー">
          <div class="view-menu-title">表示</div>
          <div class="view-menu-row">
            <span class="control-label">行</span>
            <button class="control-button" type="button" data-action="collapse-all" title="すべての親タスクを折りたたむ">▸ 折りたたむ</button>
            <button class="control-button" type="button" data-action="expand-all" title="すべての親タスクを展開する">▾ 展開</button>
          </div>
          <div class="view-menu-row column-visibility-actions">
            <span class="control-label">列</span>
            <span class="column-bulk-actions"><button class="control-button" type="button" data-column-visibility-action="show-all">すべて表示</button><button class="control-button" type="button" data-column-visibility-action="hide-all">すべて非表示</button></span>
          </div>
          <div class="column-settings column-settings-standard" data-column-settings="standard"></div>
          <div class="column-settings column-settings-analysis" data-column-settings="analysis"></div>
          <div class="column-settings-divider" aria-hidden="true"></div>
          <div class="view-menu-section-title">レイヤー</div>
          <div class="layer-settings-grid">
            <label class="layer-toggle"><input type="checkbox" data-layer-action="toggle" data-layer-target="inazuma" checked>イナズマ線</label>
            <label class="layer-toggle"><input type="checkbox" data-layer-action="toggle" data-layer-target="actual" checked>実績線</label>
            <label class="layer-toggle"><input type="checkbox" data-layer-action="toggle" data-layer-target="milestone" checked>マイルストーン</label>
            <label class="layer-toggle"><input type="checkbox" data-highlight-toggle checked>ハイライト</label>
            <label class="layer-toggle"><input type="checkbox" data-tooltip-toggle checked>ツールチップ</label>
            <label class="layer-toggle"><input type="checkbox" data-delay-highlight-toggle checked>遅延強調</label>
          </div>
          <div class="view-menu-data">
            <div class="view-menu-title">データ</div>
            <div class="view-menu-row layer-row">
              <span class="control-label">JSON</span>
              <button class="control-button" type="button" data-source-download>エクスポート</button>
            </div>
            <div class="view-menu-row layer-row">
              <span class="control-label">共有リンク</span>
              <button class="control-button" type="button" data-share-link-copy>クリップボードにコピー</button>
            </div>
          </div>
          <div class="view-menu-data">
            <div class="view-menu-title">WBS-GENについて</div>
            <div class="view-menu-links">
              <a class="footer-link" href="{GITHUB_REPO_URL}" target="_blank" rel="noopener noreferrer">GitHubリポジトリ</a>
              <a class="footer-link" href="{manual_url}" target="_blank" rel="noopener noreferrer">マニュアル</a>
            </div>
          </div>
        </div>
      </details>
      <div class="wbs-view-control" aria-label="WBS表示切り替え">
        <div class="wbs-view-tabs" role="tablist" aria-label="WBS表示">
          <button class="wbs-view-tab is-active" type="button" role="tab" aria-selected="true" data-wbs-view-target="standard">標準</button>
          <button class="wbs-view-tab" type="button" role="tab" aria-selected="false" data-wbs-view-target="analysis">分析</button>
        </div>
      </div>
    </div>"""


def format_date(value: date | None) -> str:
    return "-" if value is None else value.isoformat()


def format_date_short(value: date | None) -> str:
    return "-" if value is None else f"{value.month}/{value.day}"


def format_period(start: date | None, end: date | None) -> str:
    if start is None:
        return "-"
    start_text = format_date_short(start)
    if end is None:
        return f"{start_text} -"
    return f"{start_text} - {format_date_short(end)}"


def format_progress(value: int) -> str:
    return f"{value}%"


def format_optional_progress(value: int | None) -> str:
    if value is None:
        return "-"
    return format_progress(value)


def format_progress_delta(analysis: ProgressAnalysis) -> str:
    if analysis.delta is None:
        return "-"
    if analysis.delta == 0:
        return "0pt"
    sign = "+" if analysis.delta > 0 else ""
    return f"{sign}{analysis.delta}pt"


def format_delay_business_days(analysis: ProgressAnalysis) -> str:
    if analysis.delay_business_days is None:
        return "-"
    return f"{analysis.delay_business_days}日"


def format_required_pace(analysis: ProgressAnalysis) -> str:
    if analysis.pace_unattainable:
        return "未達"
    if analysis.required_pace is None:
        return "-"
    value = analysis.required_pace
    text = f"{int(value)}" if value == int(value) else f"{value:.1f}"
    return f"{text}%/日"


def render_issue(issue: int | None, issue_base_url: str | None) -> str:
    if issue is None:
        return "-"
    label = f"#{issue}"
    escaped_label = escape(label)
    if issue_base_url is None:
        return escaped_label
    parsed_url = urlparse(issue_base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return escaped_label
    href = f"{issue_base_url.rstrip('/')}/{issue}"
    return f'<a href="{escape(href, quote=True)}">{escaped_label}</a>'


def escape_json_for_script(value: str) -> str:
    return (
        value.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def serialize_source_json(data: dict[str, Any]) -> str:
    return escape_json_for_script(json.dumps(data, ensure_ascii=False, indent=2))


def serialize_display_settings(settings: DisplaySettings) -> str:
    return escape_json_for_script(
        json.dumps(
            {
                "standard": {
                    "columns": {
                        "visible": list(settings.standard_columns),
                        "width": settings.standard_column_widths,
                        "order": list(settings.standard_column_order),
                    }
                },
                "analysis": {"columns": {"order": list(settings.analysis_column_order)}},
                "layers": {"visible": list(settings.layers)},
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def source_index_from_path(path: str) -> int | None:
    match = re.match(r"^tasks\[(\d+)\]", path)
    return int(match.group(1)) if match is not None else None


def warning_target_id(message: ValidationMessage, tasks: list[Task]) -> str:
    source_index = source_index_from_path(message.path)
    source_task = next(
        (task for task in tasks if task.source_index == source_index),
        None,
    )
    if message.code == CODE_MISSING_PARENT_TASK:
        match = re.search(r"親タスク ([^ ]+) を補完しました", message.message)
        if match is not None:
            return match.group(1)
        if source_task is not None:
            return parent_id_for(source_task.id) or source_task.id
    if source_task is not None:
        return source_task.id
    return "-"


def warning_target_ids(
    warnings: list[ValidationMessage],
    tasks: list[Task],
) -> set[str]:
    return {
        target_id
        for target_id in (warning_target_id(message, tasks) for message in warnings)
        if target_id != "-"
    }


def warning_codes_by_target(
    warnings: list[ValidationMessage],
    tasks: list[Task],
) -> dict[str, list[str]]:
    codes: dict[str, list[str]] = {}
    for message in warnings:
        target_id = warning_target_id(message, tasks)
        if target_id == "-":
            continue
        codes.setdefault(target_id, []).append(message.code)
    return codes


def render_warning_drawer(
    warnings: list[ValidationMessage],
    tasks: list[Task],
) -> str:
    if not warnings:
        return ""
    items = "\n".join(
        "        <li>"
        f'<span class="warning-task-id">ID: {escape(warning_target_id(message, tasks))}</span>'
        f"<code>{escape(message.code)}</code>"
        f'<span class="warning-path">{escape(message.path)}</span>'
        f'<span class="warning-message">{escape(message.message)}</span>'
        "</li>"
        for message in warnings
    )
    return f"""    <aside class="warning-window" id="warning-window" data-dock-window aria-labelledby="warnings-title">
      <div class="warning-window-head">
        <h2 id="warnings-title" class="warning-window-title">警告 {len(warnings)}件</h2>
        <label class="warning-window-close" for="warning-toggle" aria-label="警告を閉じる">×</label>
      </div>
      <div class="warning-window-body">
        <ul class="warning-list">
{items}
        </ul>
      </div>
    </aside>
"""


def render_warning_toggle(warnings: list[ValidationMessage]) -> str:
    if not warnings:
        return ""
    return (
        '<label class="warning-toggle" for="warning-toggle" aria-controls="warning-window">'
        f"警告 {len(warnings)}件"
        "</label>"
    )


def render_holiday_window(holidays: list[Holiday]) -> str:
    if not holidays:
        return ""
    items = "\n".join(
        "        <li>"
        f'<span class="holiday-date">{escape(holiday.date.isoformat())}</span>'
        + (
            f'<span class="holiday-name">{escape(holiday.name)}</span>'
            if holiday.name
            else ""
        )
        + "</li>"
        for holiday in holidays
    )
    return f"""    <aside class="holiday-window" id="holiday-window" data-dock-window aria-labelledby="holidays-title">
      <div class="holiday-window-head">
        <h2 id="holidays-title" class="holiday-window-title">休日 {len(holidays)}件</h2>
        <label class="holiday-window-close" for="holiday-toggle" aria-label="休日を閉じる">×</label>
      </div>
      <div class="holiday-window-body">
        <ul class="holiday-list">
{items}
        </ul>
      </div>
    </aside>
"""


def render_holiday_toggle(holidays: list[Holiday]) -> str:
    if not holidays:
        return ""
    return (
        '<label class="holiday-toggle" for="holiday-toggle" aria-controls="holiday-window">'
        f"休日 {len(holidays)}件"
        "</label>"
    )


def task_bar_class(task: ComputedTask) -> str:
    return "parent-bar" if task.children else "task-bar"


def display_row_class(row: DisplayRow, warning_ids: set[str]) -> str:
    classes = ["wbs-row"]
    if row.task.children and row.depth == 0:
        classes.append("row-project")
    elif row.task.children:
        classes.append("row-parent-2")
    if row.task.progress == 100:
        classes.append("row-done")
    if row.task.generated:
        classes.append("generated-row")
    if row.task.id in warning_ids:
        classes.append("warning-row")
    return " ".join(classes)


def search_task_attributes(task: ComputedTask) -> str:
    values = {
        "name": task.name,
        "comment": task.comment or "",
        "assignee": task.assignee or "",
        "issue": str(task.issue) if task.issue is not None else "",
    }
    return " ".join(
        f'data-search-{key}="{escape(value, quote=True)}"'
        for key, value in values.items()
    )


def manual_url_for_version(generator_version: str | None) -> str:
    if generator_version and _RELEASE_VERSION_PATTERN.match(generator_version):
        return f"{GITHUB_REPO_URL}/releases/download/v{generator_version}/wbsgen-manual.html"
    return f"{GITHUB_REPO_URL}/releases/latest/download/wbsgen-manual.html"


def render_left_footer(generated_at: str | None, generator_version: str | None) -> str:
    generated_at_text = escape(generated_at) if generated_at else "-"
    if generator_version and _RELEASE_VERSION_PATTERN.match(generator_version):
        version_text = f"v{escape(generator_version)}"
    else:
        version_text = escape(generator_version) if generator_version else "-"
    return (
        '        <div class="left-footer">\n'
        f'          <div class="footer-line">生成日時 {generated_at_text}'
        f'<span class="footer-sep">・</span>{version_text}</div>\n'
        "        </div>"
    )


def render_wbs_table(
    rows: list[DisplayRow],
    project: Project | None,
    display_start_date: date | None,
    display_end_date: date | None,
    issue_base_url: str | None,
    warnings: list[ValidationMessage],
    tasks: list[Task],
    calendar: WorkCalendar | None = None,
    has_milestones: bool = False,
    generated_at: str | None = None,
    generator_version: str | None = None,
    task_name_width: int = DEFAULT_TASK_NAME_WIDTH,
    assignee_width: int = DEFAULT_ASSIGNEE_WIDTH,
    comment_width: int = DEFAULT_COMMENT_WIDTH,
) -> str:
    scale = (
        ChartScale(display_start_date, display_end_date)
        if project is not None and display_start_date is not None and display_end_date is not None
        else None
    )
    warning_ids = warning_target_ids(warnings, tasks)
    warning_codes = warning_codes_by_target(warnings, tasks)
    body_rows = []
    for row in rows:
        task = row.task
        warning_title = " / ".join(warning_codes.get(task.id, []))
        warning_title_attr = (
            f' title="{escape(warning_title, quote=True)}"' if warning_title else ""
        )
        task_name_tooltip = escape(task.name, quote=True).replace("\n", "&#10;")
        task_name_class = "wbs-cell"
        if task.id in warning_ids:
            task_name_class += " warn-name"
        delayed_class = (
            " delayed"
            if project is not None
            and scale is not None
            and is_delayed_task(task, project, scale, calendar)
            else ""
        )
        if task.progress == 100:
            delayed_class = " done"
        expected_progress = (
            expected_progress_for_task(task, project, calendar)
            if project is not None
            else None
        )
        row_class = display_row_class(row, warning_ids)
        if task.comment:
            comment = escape(task.comment)
            comment_tooltip = escape(task.comment, quote=True).replace("\n", "&#10;")
        elif task.generated:
            comment = "自動補完された親タスクです"
            comment_tooltip = escape("自動補完された親タスクです", quote=True)
        else:
            comment = "-"
            comment_tooltip = escape("-", quote=True)
        if task.assignee:
            assignee = escape(task.assignee)
            assignee_tooltip = escape(task.assignee, quote=True).replace("\n", "&#10;")
        else:
            assignee = "-"
            assignee_tooltip = escape("-", quote=True)
        task_name_padding = 8 + row.depth * 16
        row_attrs = f"{row_task_attributes(row)} {search_task_attributes(task)}"
        analysis = (
            progress_analysis_for_task(task, project, calendar)
            if project is not None
            else ProgressAnalysis()
        )
        analysis_delayed_class = " analysis-negative" if (
            analysis.delta is not None and analysis.delta < 0
        ) else ""
        pace_text = format_required_pace(analysis)
        pace_class = " analysis-neutral" if pace_text == "-" else ""
        body_rows.append(
            f'        <div class="{row_class}" {row_attrs}>'
            f'<div class="wbs-cell right" style="width: 58px;">{escape(task.id)}</div>'
            f'<div class="{task_name_class}" style="width: 220px; padding-left: {task_name_padding}px;"{warning_title_attr}>'
            f'{render_tree_toggle(task)}<span class="task-label" data-tooltip-role="task-name" data-tooltip-text="{task_name_tooltip}">{escape(task.name)}</span></div>'
            f'<div class="wbs-cell assignee" data-column="assignee" style="width: 56px;">'
            f'<span class="assignee-label" data-tooltip-text="{assignee_tooltip}" data-tooltip-role="assignee">{assignee}</span></div>'
            f'<div class="wbs-cell dates" data-column="planned-period" style="width: 76px;">'
            f"{format_period(task.planned_start, task.planned_end)}</div>"
            f'<div class="wbs-cell dates" data-column="actual-period" style="width: 76px;">'
            f"{format_period(task.actual_start, task.source_task.actual_end)}</div>"
            f'<div class="wbs-cell right" data-column="progress" style="width: 52px;"><span class="progress-pill{delayed_class}">'
            f"{format_progress(task.progress)}</span></div>"
            f'<div class="wbs-cell right" data-column="expected-progress" style="width: 52px;"><span class="progress-pill">'
            f"{format_optional_progress(expected_progress)}</span></div>"
            f'<div class="wbs-cell right" data-column="issue" style="width: 58px;">{render_issue(task.issue, issue_base_url)}</div>'
            f'<div class="wbs-cell note" data-column="comment">'
            f'<span class="comment-label" data-tooltip-text="{comment_tooltip}" data-tooltip-role="comment">{comment}</span></div>'
            f'<div class="wbs-cell right analysis-only{analysis_delayed_class}" data-column="delta" style="width: 56px;">'
            f"{format_progress_delta(analysis)}</div>"
            f'<div class="wbs-cell right analysis-only{analysis_delayed_class}" data-column="delay" style="width: 76px;">'
            f"{format_delay_business_days(analysis)}</div>"
            f'<div class="wbs-cell right analysis-only{pace_class}" data-column="pace" style="width: 80px;">'
            f"{pace_text}</div>"
            "</div>"
        )
    body = "\n".join(body_rows)
    footer = render_left_footer(generated_at, generator_version)
    milestone_cell = (
        '\n          <div class="milestone-cell">マイルストーン</div>'
        if has_milestones
        else ""
    )
    return f"""    <section class="left-pane" aria-labelledby="wbs-title">
      <button class="resize-handle pane-resize-handle" type="button" aria-label="左右ペイン幅を変更する" title="左右ペイン幅を変更する"></button>
      <h2 id="wbs-title" class="sr-only">WBS</h2>
      <div class="left-content">
        <div class="left-head" data-task-name-width="{task_name_width}" data-assignee-width="{assignee_width}" data-comment-width="{comment_width}">
          <div class="head-cell" style="width: 58px;">ID</div>
          <div class="head-cell task-name-head"><span class="column-label">タスク名</span><button class="resize-handle task-name-resize-handle" type="button" aria-label="タスク名列幅を変更する" title="タスク名列幅を変更する"></button></div>
          <div class="head-cell column-head assignee-head" data-column="assignee"><span class="column-label">担当者</span><button class="resize-handle assignee-resize-handle" type="button" aria-label="担当者列幅を変更する" title="担当者列幅を変更する"></button></div>
          <div class="head-cell column-head period-head" data-column="planned-period" style="width: 76px;"><span class="column-label">計画</span></div>
          <div class="head-cell column-head period-head" data-column="actual-period" style="width: 76px;"><span class="column-label">実績</span></div>
          <div class="head-cell column-head" data-column="progress" style="width: 52px;"><span class="column-label">進捗</span></div>
          <div class="head-cell column-head" data-column="expected-progress" style="width: 52px;"><span class="column-label">期待</span></div>
          <div class="head-cell column-head" data-column="issue" style="width: 58px;"><span class="column-label">Issue</span></div>
          <div class="head-cell column-head comment-head" data-column="comment"><span class="column-label">コメント</span></div>
          <div class="head-cell column-head analysis-only" data-column="delta" style="width: 56px;"><span class="column-label">差分</span></div>
          <div class="head-cell column-head analysis-only" data-column="delay" style="width: 76px;"><span class="column-label">遅れ営業日</span></div>
          <div class="head-cell column-head analysis-only" data-column="pace" style="width: 80px;"><span class="column-label">必要ペース</span></div>{milestone_cell}
        </div>
        <div class="left-rows">
{body}
{footer}
        </div>
      </div>
    </section>
"""


def render_inazuma(
    rows: list[DisplayRow],
    scale: ChartScale,
    project: Project,
    calendar: WorkCalendar | None = None,
) -> list[str]:
    if not rows:
        return []

    status_x = status_date_right_x(project, scale)
    points: list[tuple[int, int]] = [(status_x, 0)]
    point_elements: list[str] = []

    for row_index, row in enumerate(rows):
        point = progress_point_for_row(row, row_index, scale, project, calendar)
        if point is None:
            continue
        x, y, task_id = point
        points.append((x, y))
        point_elements.append(
            f'      <circle class="gantt-progress-point" cx="{x}" cy="{y}" r="3" '
            f'data-task-id="{escape(task_id, quote=True)}" />'
        )

    points.append((status_x, len(rows) * ROW_HEIGHT))
    point_text = " ".join(f"{x},{y}" for x, y in points)
    return [
        f'          <polyline class="gantt-inazuma" points="{point_text}" '
        f'data-kind="inazuma" />',
        *point_elements,
    ]


def style_for_rect(left: int, top: int, width: int, height: int) -> str:
    return f"left:{left}px;top:{top}px;width:{width}px;height:{height}px;"


def render_bar(
    class_name: str,
    left: int,
    right: int,
    top: int,
    height: int,
    attributes: str,
) -> str | None:
    width = max(0, right - left)
    if width <= 0:
        return None
    style = style_for_rect(left, top, width, height)
    return f'          <div class="{class_name}" style="{style}" {attributes}></div>'


def render_clip_marker(
    task_id: str,
    side: str,
    outside_only: bool = False,
) -> str:
    marker_class = f"clip-marker {side}"
    if outside_only:
        marker_class += " outside-only"
    clip_kind = "start" if side == "left" else "end"
    label = (
        "表示範囲より前に計画期間があります"
        if side == "left"
        else "表示範囲より後に計画期間があります"
    )
    symbol = "&lt;" if side == "left" else "&gt;"
    return (
        f'          <div class="{marker_class}" data-kind="planned-clip" '
        f'data-task-id="{escape(task_id, quote=True)}" data-clip="{clip_kind}" '
        f'aria-label="{label}">{symbol}</div>'
    )


def render_gantt_task_bars(
    row: DisplayRow,
    row_index: int,
    scale: ChartScale,
    project: Project,
    calendar: WorkCalendar | None = None,
) -> tuple[list[str], list[str], list[str]]:
    task = row.task
    bar_class = task_bar_class(task)
    delayed = is_delayed_task(task, project, scale, calendar)
    expected_progress = expected_progress_for_task(task, project, calendar)
    planned_elements: list[str] = []
    progress_elements: list[str] = []
    actual_elements: list[str] = []

    if task.planned_start is not None and task.planned_end is not None:
        clips_left = task.planned_start < scale.start_date
        clips_right = task.planned_end > scale.end_date
        outside_before = task.planned_end < scale.start_date
        outside_after = task.planned_start > scale.end_date
        intersects_display_range = not outside_before and not outside_after

        if outside_before:
            planned_elements.append(render_clip_marker(task.id, "left", outside_only=True))
        elif outside_after:
            planned_elements.append(render_clip_marker(task.id, "right", outside_only=True))

        if intersects_display_range:
            if clips_left:
                planned_elements.append(render_clip_marker(task.id, "left"))
            if clips_right:
                planned_elements.append(render_clip_marker(task.id, "right"))
            planned_x1 = scale.x_for_date(task.planned_start)
            planned_x2 = scale.x_for_date_end(task.planned_end)
            task_name_tooltip = escape(task.name, quote=True).replace("\n", "&#10;")
            actual_start_attr = task.actual_start.isoformat() if task.actual_start else ""
            actual_end_attr = task.actual_end.isoformat() if task.actual_end else ""
            planned_bar_class = f"bar plan {bar_class}"
            planned_bar_attrs = [
                'data-kind="planned"',
                f'data-task-id="{escape(task.id, quote=True)}"',
                'data-tooltip-role="plan-bar"',
                f'data-task-name="{task_name_tooltip}"',
                f'data-planned-end="{task.planned_end.isoformat()}"',
                f'data-progress-label="{format_progress(task.progress)}"',
                f'data-actual-start="{actual_start_attr}"',
                f'data-actual-end="{actual_end_attr}"',
            ]
            if delayed:
                planned_bar_class += " delayed"
                planned_bar_attrs.append('data-delay-state="delayed"')
                if expected_progress is not None:
                    planned_bar_attrs.append(
                        f'data-expected-progress-label="{format_progress(expected_progress)}"'
                    )
            planned_bar = render_bar(
                planned_bar_class,
                planned_x1,
                planned_x2,
                (ROW_HEIGHT - BAR_HEIGHT) // 2,
                BAR_HEIGHT,
                " ".join(planned_bar_attrs),
            )
            if planned_bar is not None:
                planned_elements.append(planned_bar)
            visible_planned_x1 = max(planned_x1, 0)
            visible_planned_x2 = min(planned_x2, scale.chart_width)
            progress_x = progress_x_for_task(
                task.planned_start,
                task.planned_end,
                task.progress,
                project.status_date,
                scale,
                calendar,
            )
            progress_x = min(max(progress_x, visible_planned_x1), visible_planned_x2)
            progress_bar = render_bar(
                f"bar progress {bar_class}",
                visible_planned_x1,
                progress_x,
                (ROW_HEIGHT - PROGRESS_BAR_HEIGHT) // 2,
                PROGRESS_BAR_HEIGHT,
                f'data-task-id="{escape(task.id, quote=True)}" '
                f'data-kind="progress" data-progress="{task.progress}"',
            )
            if progress_bar is not None:
                progress_elements.append(progress_bar)

    if task.actual_start is not None:
        actual_end = task.actual_end
        actual_class = f"bar actual actual-complete {bar_class}"
        if actual_end is None:
            actual_end = project.status_date
            actual_class = f"bar actual actual-ongoing {bar_class}"
        actual_start = clamped_date(task.actual_start, scale.start_date, scale.end_date)
        actual_end = clamped_date(actual_end, scale.start_date, scale.end_date)
        if actual_start <= actual_end:
            actual_bar = render_bar(
                actual_class,
                scale.x_for_date(actual_start),
                scale.x_for_date_end(actual_end),
                ROW_HEIGHT // 2 - ACTUAL_BAR_HEIGHT // 2,
                ACTUAL_BAR_HEIGHT,
                f'data-kind="actual" data-task-id="{escape(task.id, quote=True)}" '
                f'data-actual-end="{actual_end.isoformat()}"',
            )
            if actual_bar is not None:
                actual_elements.append(actual_bar)

    return planned_elements, progress_elements, actual_elements


def render_month_header(scale: ChartScale) -> str:
    segments: list[str] = []
    dates = iter_dates(scale.start_date, scale.end_date)
    index = 0
    while index < len(dates):
        current = dates[index]
        month_dates = [current]
        index += 1
        while index < len(dates) and dates[index].month == current.month:
            month_dates.append(dates[index])
            index += 1
        label = (
            f"{current.year}年{current.month}月"
            if len(month_dates) >= MONTH_LABEL_MIN_DAYS
            else ""
        )
        blank_class = " blank" if not label else ""
        width = len(month_dates) * scale.day_width
        segments.append(
            f'          <div class="month-seg{blank_class}" style="width:{width}px;">'
            f"{escape(label)}</div>"
        )
    return "\n".join(segments)


def render_day_header(
    scale: ChartScale,
    holiday_map: dict[date, Holiday] | None = None,
) -> str:
    holiday_map = holiday_map or {}
    weekday_labels = ["月", "火", "水", "木", "金", "土", "日"]
    cells = []
    for current in iter_dates(scale.start_date, scale.end_date):
        day_class = "date-cell"
        if current.weekday() == 5:
            day_class += " sat"
        elif current.weekday() == 6:
            day_class += " sun"
        holiday = holiday_map.get(current)
        # Weekday holidays reuse the Sunday styling to read as non-working days.
        if holiday is not None and current.weekday() < 5:
            day_class += " sun"
        holiday_attr = (
            f' data-holiday-name="{escape(holiday.name, quote=True)}"'
            if holiday is not None and holiday.name
            else ""
        )
        cells.append(
            f'          <div class="{day_class}" data-date="{current.isoformat()}"{holiday_attr}>'
            f"{current.day}<span class=\"dow\">{weekday_labels[current.weekday()]}</span>"
            "</div>"
        )
    return "\n".join(cells)


def gantt_row_class(row: DisplayRow) -> str:
    classes = ["gantt-row"]
    if row.task.children and row.depth == 0:
        classes.append("project")
    elif row.task.children:
        classes.append("parent-2")
    if row.task.progress == 100:
        classes.append("done")
    return " ".join(classes)


def milestone_band_height(placed: list[PlacedMilestone]) -> int:
    if not placed:
        return 0
    return (max(item.tier for item in placed) + 1) * MILESTONE_TIER_HEIGHT


def render_milestone_band(placed: list[PlacedMilestone]) -> str:
    if not placed:
        return ""
    parts: list[str] = []
    for item in placed:
        tier_top = item.tier * MILESTONE_TIER_HEIGHT
        name = escape(item.milestone.name)
        date_attr = item.milestone.date.isoformat()
        parts.append(
            f'            <div class="milestone-marker" data-kind="milestone" '
            f'data-date="{date_attr}" style="left:{item.x}px;top:{tier_top + 6}px;"></div>'
        )
        parts.append(
            f'            <div class="milestone-pill" '
            f'style="left:{item.x + 9}px;top:{tier_top + 4}px;">{name}</div>'
        )
        parts.append(
            f'            <div class="milestone-band-vline" '
            f'style="left:{item.x - 1}px;top:{tier_top + 12}px;"></div>'
        )
    content = "\n".join(parts)
    height = milestone_band_height(placed)
    return (
        f'          <div class="milestone-band" style="height:{height}px;" aria-label="マイルストーン">\n'
        f"{content}\n"
        "          </div>\n"
    )


def render_milestone_lines(placed: list[PlacedMilestone], body_height: int) -> str:
    return "\n".join(
        f'            <line class="milestone-line" x1="{item.x}" y1="0" '
        f'x2="{item.x}" y2="{body_height}" data-kind="milestone-line" '
        f'data-date="{item.milestone.date.isoformat()}" />'
        for item in placed
    )


def render_gantt_chart(
    rows: list[DisplayRow],
    project: Project | None,
    display_start_date: date | None,
    display_end_date: date | None,
    holidays: list[Holiday] | None = None,
    calendar: WorkCalendar | None = None,
    milestones: list[Milestone] | None = None,
) -> str:
    if project is None or display_start_date is None or display_end_date is None:
        return ""

    holiday_map: dict[date, Holiday] = {holiday.date: holiday for holiday in (holidays or [])}
    scale = ChartScale(display_start_date, display_end_date)
    placed_milestones = layout_milestones(milestones or [], scale)
    rows_height = max(len(rows), 1) * ROW_HEIGHT
    body_height = rows_height + BOTTOM_FOOTER_HEIGHT
    status_line_x = status_date_right_x(project, scale)
    weekend_elements: list[str] = []
    for current in iter_dates(display_start_date, display_end_date):
        x = scale.x_for_date(current)
        holiday = holiday_map.get(current)
        # Weekday holidays reuse the weekend background treatment.
        if is_weekend(current) or holiday is not None:
            holiday_attr = (
                f' data-holiday-name="{escape(holiday.name, quote=True)}"'
                if holiday is not None and holiday.name
                else ""
            )
            weekend_elements.append(
                f'            <div class="weekend-bg" data-date="{current.isoformat()}"{holiday_attr} '
                f'style="{style_for_rect(x, 0, scale.day_width, body_height)}"></div>'
            )

    status_date = clamped_date(project.status_date, scale.start_date, scale.end_date)
    status_cell_left_x = scale.x_for_date(status_date)
    row_elements: list[str] = []
    for row_index, row in enumerate(rows):
        planned_elements, progress_elements, actual_elements = render_gantt_task_bars(
            row,
            row_index,
            scale,
            project,
            calendar,
        )
        row_content = "\n".join(planned_elements + progress_elements + actual_elements)
        row_status_background = (
            f'            <div class="status-date-bg" '
            f'data-status-date="{project.status_date.isoformat()}" '
            f'style="{style_for_rect(status_cell_left_x, 0, scale.day_width, ROW_HEIGHT)}"></div>'
        )
        row_attrs = row_task_attributes(
            row, project=project, scale=scale, row_index=row_index, calendar=calendar
        )
        row_attrs = f"{row_attrs} {search_task_attributes(row.task)}"
        row_elements.append(
            f'          <div class="{gantt_row_class(row)}" {row_attrs}>\n'
            f"{row_status_background}\n"
            f"{row_content}\n"
            "          </div>"
        )
    weekends = "\n".join(weekend_elements)
    row_content = "\n".join(row_elements)
    inazuma_content = "\n".join(render_inazuma(rows, scale, project, calendar))
    milestone_band = render_milestone_band(placed_milestones)
    milestone_lines = render_milestone_lines(placed_milestones, body_height)
    milestone_lines_block = f"{milestone_lines}\n" if milestone_lines else ""
    return f"""    <section class="right-pane" style="--chart-w:{scale.chart_width}px;--gantt-right-gutter:24px;" aria-labelledby="gantt-title">
      <h2 id="gantt-title" class="sr-only">ガントチャート</h2>
      <div class="chart-scroll">
        <div class="right-head" style="width:{scale.chart_width}px;">
          <div class="ym-row">
{render_month_header(scale)}
          </div>
          <div class="date-row">
{render_day_header(scale, holiday_map)}
          </div>
{milestone_band}        </div>
        <div class="chart-body" style="width:{scale.chart_width}px;height:{body_height}px;" data-chart-width="{scale.chart_width}" data-status-x="{status_line_x}" data-row-height="{ROW_HEIGHT}" data-footer-height="{BOTTOM_FOOTER_HEIGHT}" data-day-width="{scale.day_width}" data-chart-start-date="{scale.start_date.isoformat()}">
          <div class="interaction-layer" aria-hidden="true"></div>
          <div class="chart-bg">
{weekends}
          </div>
          <div class="chart-grid" style="width:{scale.chart_width}px;height:{body_height}px;"></div>
          <div class="chart-rows">
{row_content}
          </div>
          <svg class="chart-overlay gantt-overlay" width="{scale.chart_width}" height="{body_height}" viewBox="0 0 {scale.chart_width} {body_height}" aria-hidden="true">
{milestone_lines_block}{inazuma_content}
          </svg>
          <div class="chart-footer-space" aria-hidden="true"></div>
        </div>
      </div>
    </section>
"""


def render_html(
    data: dict[str, Any],
    result: BuildResult,
) -> str:
    project = result.project
    project_name = project.name if project is not None else APP_NAME
    issue_base_url = project.issue_base_url if project is not None else None
    status_date = format_date_short(project.status_date if project is not None else None)
    display_range = (
        f"{format_date(result.display_start_date)} - {format_date(result.display_end_date)}"
    )
    rows = flatten_computed_tasks(result.computed_roots)
    generator_version = read_generator_version(data)
    generated_at = read_generated_at(data)
    warning_toggle_input = (
        '  <input class="warning-checkbox" type="checkbox" id="warning-toggle" checked>\n'
        if result.validation.warnings
        else ""
    )
    warning_toggle = render_warning_toggle(result.validation.warnings)
    warnings = render_warning_drawer(result.validation.warnings, result.tasks)
    holiday_toggle_input = (
        '  <input class="holiday-checkbox" type="checkbox" id="holiday-toggle">\n'
        if result.holidays
        else ""
    )
    holiday_toggle = render_holiday_toggle(result.holidays)
    holidays = render_holiday_window(result.holidays)
    calendar = WorkCalendar(holidays=tuple(result.holidays))
    placed_milestones: list[PlacedMilestone] = []
    if (
        project is not None
        and result.display_start_date is not None
        and result.display_end_date is not None
        and result.milestones
    ):
        placed_milestones = layout_milestones(
            result.milestones,
            ChartScale(result.display_start_date, result.display_end_date),
        )
    band_height = milestone_band_height(placed_milestones)
    band_total = band_height + 2
    app_style = (
        f' style="--milestone-band-total:{band_total}px;" data-milestone-band-total="{band_total}px"'
        if band_height
        else ""
    )
    column_widths = result.display_settings.standard_column_widths
    task_name_width = column_widths.get("name", DEFAULT_TASK_NAME_WIDTH)
    assignee_width = column_widths.get("assignee", DEFAULT_ASSIGNEE_WIDTH)
    comment_width = column_widths.get("comment", DEFAULT_COMMENT_WIDTH)
    table = render_wbs_table(
        rows,
        project,
        result.display_start_date,
        result.display_end_date,
        issue_base_url,
        result.validation.warnings,
        result.tasks,
        calendar,
        has_milestones=bool(placed_milestones),
        generated_at=generated_at,
        generator_version=generator_version,
        task_name_width=task_name_width,
        assignee_width=assignee_width,
        comment_width=comment_width,
    )
    gantt = render_gantt_chart(
        rows,
        project,
        result.display_start_date,
        result.display_end_date,
        result.holidays,
        calendar,
        milestones=result.milestones,
    )
    source_json = serialize_source_json(data)
    display_settings_json = serialize_display_settings(result.display_settings)
    escaped_project_name = escape(project_name)
    escaped_app_name = escape(APP_NAME)
    view_menu = render_view_menu(generator_version)
    width_model_script = read_text_asset("width-model.js").rstrip("\n")
    app_script = read_text_asset("app.js").rstrip("\n")

    template = Template(read_text_asset("page.html"))
    style = read_text_asset("style.css").rstrip("\n")
    return template.substitute(
        app_name=escaped_app_name,
        app_style=app_style,
        display_range=display_range,
        gantt=gantt,
        project_name=escaped_project_name,
        display_settings_json=display_settings_json,
        source_json=source_json,
        status_date=status_date,
        style=style,
        table=table,
        view_menu=view_menu,
        width_model_script=width_model_script,
        app_script=app_script,
        warning_toggle=warning_toggle,
        warning_toggle_input=warning_toggle_input,
        warnings=warnings,
        holiday_toggle=holiday_toggle,
        holiday_toggle_input=holiday_toggle_input,
        holidays=holidays,
    )
