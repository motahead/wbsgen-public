from contextlib import nullcontext
import pytest
import io
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import zipfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import wbsgen

class TestGanttChartGuardTests:

    def test_render_gantt_chart_returns_empty_without_complete_project_range(self):
        from wbsgen.render.html import render_gantt_chart
        assert render_gantt_chart([], None, None, None) == ''

    def test_gantt_bar_helper_handles_suppressed_bars_and_missing_expected_progress(self):
        from wbsgen.models import ChartScale, ComputedTask, DisplayRow, Project, Task
        from wbsgen.render import html
        task = ComputedTask(id='1', name='T', source_task=Task(id='1', name='T'), planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 2), actual_start=date(2026, 6, 1), actual_end=date(2026, 6, 2), progress=50)
        row = DisplayRow(task=task, depth=0)
        project = Project(name='P', status_date=date(2026, 6, 2))
        scale = ChartScale(date(2026, 6, 1), date(2026, 6, 3))
        with mock.patch.object(html, 'render_bar', return_value=None), mock.patch.object(html, 'is_delayed_task', return_value=True), mock.patch.object(html, 'expected_progress_for_task', return_value=None):
            planned, progress, actual = html.render_gantt_task_bars(row, 0, scale, project)
        assert (planned, progress, actual) == ([], [], [])

    def test_row_attributes_allow_omitting_row_index(self):
        from wbsgen.models import ChartScale, ComputedTask, DisplayRow, Project, Task
        from wbsgen.render.html import row_task_attributes
        row = DisplayRow(task=ComputedTask(id='1', name='T', source_task=Task(id='1', name='T')), depth=0)
        result = row_task_attributes(row, row_index=None, scale=ChartScale(date(2026, 6, 1), date(2026, 6, 2)), project=Project(name='P', status_date=date(2026, 6, 1)))
        assert 'data-status-x="32"' in result

    def test_missing_parent_warning_falls_back_to_source_task_parent_id(self):
        from wbsgen.render.html import warning_target_id
        from wbsgen.validation import CODE_MISSING_PARENT_TASK, ValidationMessage
        from wbsgen.models import Task
        message = ValidationMessage(level='warning', code=CODE_MISSING_PARENT_TASK, path='tasks[0].id', message='補完メッセージなし')
        assert warning_target_id(message, [Task(id='1.2', name='T', source_index=0)]) == '1'

    def test_missing_parent_warning_without_source_task_uses_unknown_target(self):
        from wbsgen.render.html import warning_target_id
        from wbsgen.validation import CODE_MISSING_PARENT_TASK, ValidationMessage
        message = ValidationMessage(level='warning', code=CODE_MISSING_PARENT_TASK, path='tasks[9].id', message='補完メッセージなし')
        assert warning_target_id(message, []) == '-'

class TestLeftFooterMetaInfoTests:

    def test_manual_url_for_version_pins_release_download_url(self):
        from wbsgen.render.html import manual_url_for_version
        assert manual_url_for_version('2.0.1') == 'https://github.com/motahead/wbsgen-public/releases/download/v2.0.1/wbsgen-manual.html'

    def test_manual_url_for_version_falls_back_to_latest_for_non_release_version(self):
        from wbsgen.render.html import manual_url_for_version
        for version in ('development', '2.0', 'v2.0.1', None):
            with nullcontext():
                assert manual_url_for_version(version) == 'https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-manual.html'

    def test_render_left_footer_outputs_generated_at_and_version_without_links(self):
        from wbsgen.render.html import render_left_footer
        footer = render_left_footer('2026-07-20 15:30', '2.0.1')
        assert 'class="left-footer"' in footer
        assert '生成日時 2026-07-20 15:30' in footer
        assert 'v2.0.1' in footer
        assert 'WBS-GEN' not in footer
        assert 'footer-link' not in footer
        assert 'GitHubリポジトリ' not in footer
        assert 'マニュアル' not in footer

    def test_render_left_footer_uses_bare_version_text_for_non_release_version(self):
        from wbsgen.render.html import render_left_footer
        footer = render_left_footer('2026-07-20 15:30', 'development')
        assert '<span class="footer-sep">・</span>development</div>' in footer
        assert 'vdevelopment' not in footer
        assert 'wbsgen-manual.html' not in footer

    def test_render_left_footer_falls_back_to_placeholder_text_when_metadata_missing(self):
        from wbsgen.render.html import render_left_footer
        footer = render_left_footer(None, None)
        assert '生成日時 -' in footer
        assert '<span class="footer-sep">・</span>-</div>' in footer

    def test_render_left_footer_escapes_html_in_generated_at_and_version(self):
        from wbsgen.render.html import render_left_footer
        footer = render_left_footer('<script>', '<b>1.0.0</b>')
        assert '<script>' not in footer
        assert '&lt;script&gt;' in footer
        assert '<b>1.0.0</b>' not in footer

    def test_render_html_embeds_left_footer_using_source_metadata(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}], '_wbsgen': {'generatorVersion': '2.0.1', 'generatedAt': '2026-07-20 15:30'}}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '生成日時 2026-07-20 15:30' in html
        assert '<span class="footer-sep">・</span>v2.0.1</div>' in html
        assert 'https://github.com/motahead/wbsgen-public/releases/download/v2.0.1/wbsgen-manual.html' in html

    def test_render_html_left_footer_omits_metadata_gracefully_when_absent(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '生成日時 -' in html
        assert '<span class="footer-sep">・</span>-</div>' in html

class TestViewMenuAboutLinksTests:

    def test_render_view_menu_outputs_share_link_copy_control(self):
        from wbsgen.render.html import render_view_menu

        menu = render_view_menu('2.0.1')

        assert '<div class="view-menu-title">データ</div>' in menu
        assert '<span class="control-label">共有リンク</span>' in menu
        assert 'data-share-link-copy>クリップボードにコピー</button>' in menu

    def test_render_view_menu_outputs_about_section_with_github_and_manual_links(self):
        from wbsgen.render.html import render_view_menu
        menu = render_view_menu('2.0.1')
        assert '<div class="view-menu-title">WBS-GENについて</div>' in menu
        assert '<div class="view-menu-links">' in menu
        assert '<a class="footer-link" href="https://github.com/motahead/wbsgen-public" target="_blank" rel="noopener noreferrer">GitHubリポジトリ</a>' in menu
        assert '<a class="footer-link" href="https://github.com/motahead/wbsgen-public/releases/download/v2.0.1/wbsgen-manual.html" target="_blank" rel="noopener noreferrer">マニュアル</a>' in menu
        assert '<span class="control-label">GitHub</span>' not in menu

    def test_render_view_menu_falls_back_to_latest_manual_url_for_non_release_version(self):
        from wbsgen.render.html import render_view_menu
        menu = render_view_menu('development')
        assert 'https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-manual.html' in menu

    def test_render_html_embeds_about_links_in_view_menu(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}], '_wbsgen': {'generatorVersion': '2.0.1', 'generatedAt': '2026-07-20 15:30'}}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '<div class="view-menu-title">WBS-GENについて</div>' in html
        assert 'https://github.com/motahead/wbsgen-public/releases/download/v2.0.1/wbsgen-manual.html' in html

class TestRenderModuleTests:

    def test_render_html_module_exports_existing_renderer(self):
        from wbsgen.render import html
        assert html.render_html is wbsgen.render_html
        assert html.render_issue is wbsgen.render_issue
        assert html.render_bar is wbsgen.render_bar

class TestRenderAssetTests:

    def test_render_html_reads_page_template_and_css_assets(self):
        from wbsgen.render import html
        assert '$style' in html.read_text_asset('page.html')
        assert ':root' in html.read_text_asset('style.css')

    def test_render_html_css_defines_print_layout(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '@media print {' in css
        print_block = css.split('@media print {', 1)[1]
        for selector in (
            '.search-drawer', '.app-tooltip', '.warning-window',
            '.holiday-window', '.view-controls', '.wbs-view-control',
            '.search-summary', '.warning-toggle', '.holiday-toggle',
            '.resize-handle', '.interaction-layer',
        ):
            assert selector in print_block
        assert '.topbar {' in print_block
        assert '.workspace {' in print_block
        assert '.left-head {' in print_block
        assert 'break-inside: avoid-page;' in print_block
        assert 'page-break-inside: avoid;' in print_block
        assert '.chart-body {' not in print_block
        assert '.chart-grid {' in print_block
        assert 'background: none;' in print_block
        assert '.print-grid {' in print_block
        assert '.print-grid-line {' in print_block

    def test_render_html_css_defines_wbs_view_tabs_and_analysis_column_styles(self):
        from wbsgen import render
        css = render.html.read_text_asset('style.css')
        assert '.wbs-view-tab {' in css
        assert '.wbs-view-tab.is-active {' in css
        assert '.analysis-only { display: none; }' in css
        assert 'html[data-wbs-view="analysis"] .analysis-only { display: flex; }' in css
        assert 'html[data-wbs-view="analysis"] [data-column="planned-period"]' in css
        assert 'html[data-wbs-view="analysis"] [data-column="issue"]' in css
        assert 'html[data-wbs-view="analysis"] .comment-head' in css
        assert '.wbs-cell.analysis-negative {' in css
        assert '.control-button:disabled {' in css

    def test_format_progress_delta_formats_sign_and_dash(self):
        from wbsgen.render import html
        from wbsgen.models import ProgressAnalysis
        assert html.format_progress_delta(ProgressAnalysis(delta=10)) == '+10pt'
        assert html.format_progress_delta(ProgressAnalysis(delta=-20)) == '-20pt'
        assert html.format_progress_delta(ProgressAnalysis(delta=0)) == '0pt'
        assert html.format_progress_delta(ProgressAnalysis(delta=None)) == '-'

    def test_format_delay_business_days_formats_days_and_dash(self):
        from wbsgen.render import html
        from wbsgen.models import ProgressAnalysis
        assert html.format_delay_business_days(ProgressAnalysis(delay_business_days=2)) == '2日'
        assert html.format_delay_business_days(ProgressAnalysis(delay_business_days=0)) == '0日'
        assert html.format_delay_business_days(ProgressAnalysis(delay_business_days=None)) == '-'

    def test_format_required_pace_formats_integer_decimal_unattainable_and_dash(self):
        from wbsgen.render import html
        from wbsgen.models import ProgressAnalysis
        assert html.format_required_pace(ProgressAnalysis(required_pace=10.0)) == '10%/日'
        assert html.format_required_pace(ProgressAnalysis(required_pace=12.5)) == '12.5%/日'
        assert html.format_required_pace(ProgressAnalysis(required_pace=None, pace_unattainable=True)) == '未達'
        assert html.format_required_pace(ProgressAnalysis(required_pace=None)) == '-'

    def test_render_html_css_uses_issue_52_visual_tokens(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        expected_tokens = ['--row-h: 32px;', '--text: #202735;', '--page: #f6f7f9;', '--head: #eef2f6;', '--border: #d6dce5;', '--line: #d1d8e2;', '--grid: #eceff4;', '--weekend: #f2f5f8;', '--project: #e2ecf8;', '--parent-2: #f0f6ff;', '--plan: #92c8a6;', '--progress: #4f936e;', '--actual: #2f3a4a;', '--actual-done: #566171;', '--parent-plan: #a8bfd7;', '--parent-progress: #6689ad;', '--parent-actual: #3f4a5a;', '--inazuma: #ff00ff;', '--warning: #a9470a;', '--delay-plan-line: #c56f09;', '--delay-plan-shadow: rgba(197, 111, 9, 0.10);', '--delay-parent-line: #a45f13;', '--delay-parent-shadow: rgba(164, 95, 19, 0.10);']
        for token in expected_tokens:
            assert token in css

    def test_render_html_css_compacts_topbar_legend_and_warning_styles(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        legend_block = re.search('\\.legend \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        warning_toggle_block = re.search('\\.warning-toggle \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        warn_name_block = re.search('\\.wbs-cell\\.warn-name \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert legend_block is not None
        assert warning_toggle_block is not None
        assert warn_name_block is not None
        assert 'gap: 10px;' in css
        assert '.summary span:first-child {' in css
        assert 'font-size: 11px;' in legend_block.group('body')
        assert 'gap: 8px;' in legend_block.group('body')
        assert 'background: #fffaf0;' in warning_toggle_block.group('body')
        assert 'border: 1px solid #f1c27d;' in warning_toggle_block.group('body')
        assert 'min-height: 20px;' in warning_toggle_block.group('body')
        assert 'padding: 0 6px;' in warning_toggle_block.group('body')
        assert 'background: #fffaf0;' in warn_name_block.group('body')
        assert 'box-shadow: inset 3px 0 0 #d97706;' in warn_name_block.group('body')

    def test_render_html_css_defines_topbar_identity_and_actions_clusters(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        topbar_block = re.search('\\.topbar \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        legend_block = re.search('\\.legend \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert topbar_block is not None
        assert legend_block is not None
        assert 'flex-wrap: wrap;' in topbar_block.group('body')
        assert 'margin-left: auto;' not in legend_block.group('body')
        assert (
            '.topbar-identity,\n'
            '    .topbar-actions {\n'
            '      align-items: center;\n'
            '      display: flex;\n'
            '      flex-wrap: wrap;\n'
            '      gap: 10px;\n'
            '    }\n'
        ) in css
        assert (
            '.topbar-actions {\n'
            '      justify-content: flex-end;\n'
            '      margin-left: auto;\n'
            '    }\n'
        ) in css
        assert (
            '@media (max-width: 1024px) {\n'
            '      .topbar-identity,\n'
            '      .topbar-actions {\n'
            '        flex: 1 1 100%;\n'
            '      }\n'
            '    }\n'
        ) in css

    def test_render_html_css_uses_compact_gantt_bar_styles(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        plan_block = re.search('\\.gantt-row \\.bar\\.plan \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        progress_block = re.search('\\.gantt-row \\.bar\\.progress \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        actual_block = re.search('\\.gantt-row \\.bar\\.actual \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        clip_block = re.search('\\.clip-marker \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        inazuma_block = re.search('\\.gantt-inazuma \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        point_block = re.search('\\.gantt-progress-point \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert plan_block is not None
        assert progress_block is not None
        assert actual_block is not None
        assert clip_block is not None
        assert inazuma_block is not None
        assert point_block is not None
        assert 'height: 12px;' in plan_block.group('body')
        assert 'top: 10px;' in plan_block.group('body')
        assert 'height: 8px;' in progress_block.group('body')
        assert 'top: 12px;' in progress_block.group('body')
        assert 'top: 15px;' in actual_block.group('body')
        assert 'height: 18px;' in clip_block.group('body')
        assert 'top: 7px;' in clip_block.group('body')
        assert 'stroke: var(--inazuma);' in inazuma_block.group('body')
        assert 'stroke-width: 1.7;' in inazuma_block.group('body')
        assert 'stroke-width: 1.7;' in point_block.group('body')

    def test_render_html_reads_app_js_asset_and_embeds_it(self):
        from wbsgen.render import html
        app_js = html.read_text_asset('app.js')
        assert 'const rowHeight' in app_js
        assert 'const chartFooterHeight' in app_js
        assert '* rowHeight + chartFooterHeight' in app_js
        assert 'points.push(`${statusX},${rows.length * rowHeight}`);' in app_js
        assert 'function updateRowVisibility()' in app_js
        assert '<script' not in app_js
        data, result = TestTestRenderGanttChartTests().build_result_for_gantt()
        rendered = wbsgen.render_html(data, result)
        assert '<script>' in rendered
        assert 'const chartFooterHeight' in rendered
        assert 'function updateRowVisibility()' in rendered

    def test_render_html_reads_width_model_js_asset_and_embeds_it_before_app_js(self):
        from wbsgen.render import html
        width_model_js = html.read_text_asset('width-model.js')
        assert 'window.WbsWidthModel = (() => {' in width_model_js
        assert '<script' not in width_model_js
        data, result = TestTestRenderGanttChartTests().build_result_for_gantt()
        rendered = wbsgen.render_html(data, result)
        assert 'window.WbsWidthModel = (() => {' in rendered
        width_model_script_index = rendered.index('window.WbsWidthModel = (() => {')
        app_script_index = rendered.index("const chartBody = document.querySelector('.chart-body');")
        assert width_model_script_index < app_script_index

    def test_render_html_css_supports_workspace_scroll_and_chart_width_boundaries(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        app_block = re.search('\\.app \\{(?P<body>.*?)\\n    \\}\\n    \\.sr-only \\{', css, re.DOTALL)
        assert app_block is not None
        assert re.search('(?<!-)height: 100vh;', app_block.group('body'))
        assert '.workspace {' in css
        assert 'align-items: flex-start;' in css
        assert 'overflow-x: scroll;' in css
        assert 'overflow-y: auto;' in css
        assert 'scrollbar-gutter: stable;' in css
        assert '.workspace::-webkit-scrollbar {' in css
        assert 'height: 12px;' in css
        assert '.left-pane {' in css
        assert 'left: 0;' in css
        assert 'position: sticky;' in css
        assert 'z-index: 7;' in css
        assert '.right-pane {' in css
        assert 'flex: 0 0 auto;' in css
        assert 'overflow: visible;' in css
        assert '--gantt-right-gutter: 24px;' in css
        assert 'width: calc(var(--chart-w) + var(--gantt-right-gutter));' in css
        assert '.left-head,' in css
        assert '.right-head {' in css
        assert 'position: sticky;' in css
        assert 'top: 0;' in css
        assert 'z-index: 6;' in css
        assert '.chart-body {' in css
        assert 'min-width: 100%;' not in css

    def test_render_html_css_defines_out_of_range_clip_markers(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '.clip-marker {' in css
        assert '.clip-marker.left' in css
        assert '.clip-marker.right' in css
        assert '.clip-marker.outside-only' in css
        assert 'overflow: hidden' in css

    def test_render_html_css_defines_left_footer_and_matching_gantt_footer_space(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '--footer-h: 32px;' in css
        assert '.left-rows {' in css
        assert 'padding-bottom: var(--footer-h);' in css
        assert '.left-footer {' in css
        assert 'height: var(--footer-h);' in css
        assert '.chart-footer-space {' in css
        assert '.view-menu-links {' in css

    def test_render_html_css_defines_non_modal_warning_window(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        window_block = re.search('\\.warning-window \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        open_block = re.search('\\.warning-checkbox:checked ~ \\.app \\.warning-window \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        body_block = re.search('\\.warning-window-body \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        list_item_block = re.search('\\.warning-list li \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert window_block is not None
        assert open_block is not None
        assert body_block is not None
        assert list_item_block is not None
        assert 'display: none;' in window_block.group('body')
        assert 'position: fixed;' in window_block.group('body')
        assert 'right: 16px;' in window_block.group('body')
        assert 'bottom: 24px;' in window_block.group('body')
        assert 'border: 1px solid #f1c27d;' in window_block.group('body')
        assert 'box-shadow: 0 14px 34px rgba(15, 23, 42, 0.18);' in window_block.group('body')
        assert 'width: min(420px, calc(100vw - 24px));' in window_block.group('body')
        assert 'max-height: min(50vh, 420px);' in window_block.group('body')
        assert 'left: 0;' not in window_block.group('body')
        assert 'right: 0;' not in window_block.group('body')
        assert 'transform: translateY' not in window_block.group('body')
        assert 'display: flex;' in open_block.group('body')
        assert 'overflow: auto;' in body_block.group('body')
        assert 'grid-template-columns: 64px 1fr;' in list_item_block.group('body')

    def test_render_html_css_defines_interaction_highlight_layers(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        progress_bar_block = re.search('\\.gantt-row \\.bar\\.progress \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        actual_bar_block = re.search('\\.gantt-row \\.bar\\.actual \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert '--hover-row: rgba(250, 204, 21, 0.18);' in css
        assert '--hover-date: rgba(250, 204, 21, 0.18);' in css
        assert '--pinned-row: rgba(250, 204, 21, 0.30);' in css
        assert '--pinned-date: rgba(250, 204, 21, 0.30);' in css
        assert '.interaction-layer {' in css
        assert 'z-index: 3;' in css
        assert '.wbs-row.is-hovered-task' in css
        assert '.wbs-row.is-pinned-task' in css
        assert '.gantt-row.is-hovered-task' in css
        assert '.gantt-row.is-pinned-task' in css
        assert '.date-cell.is-hovered-date' in css
        assert '.date-cell.is-pinned-date' in css
        assert '.highlight-cross.is-pinned' in css
        assert '.app-tooltip {' in css
        assert 'position: fixed;' in css
        assert '.app.is-tooltip-hidden .app-tooltip {' in css
        assert progress_bar_block is not None
        assert 'pointer-events: none;' in progress_bar_block.group('body')
        assert actual_bar_block is not None
        assert 'pointer-events: none;' in actual_bar_block.group('body')

    def test_app_js_supports_hover_pinning_escape_and_highlight_toggle(self):
        from wbsgen.render import html
        app_js = html.read_text_asset('app.js')
        plan_bar_tooltip_block = re.search('function planBarTooltipText\\(bar\\) \\{(?P<body>.*?)\\n  \\}', app_js, re.DOTALL)
        assert "const interactionLayer = document.querySelector('.interaction-layer');" in app_js
        assert "const highlightToggle = document.querySelector('[data-highlight-toggle]');" in app_js
        assert 'const pinnedTaskIds = new Set();' in app_js
        assert 'const pinnedDateIndexes = new Set();' in app_js
        assert 'let hoveredTaskId = null;' in app_js
        assert 'let hoveredDateIndex = null;' in app_js
        assert 'let highlightsEnabled = highlightToggle ? highlightToggle.checked : true;' in app_js
        assert 'function togglePinnedScheduleCell(taskId, dateIndex)' in app_js
        assert 'if (taskPinned || datePinned)' in app_js
        assert 'function renderHighlights()' in app_js
        assert 'function positionFromChartEvent(event)' in app_js
        assert "const displayLayerKeys = ['inazuma', 'actual', 'highlight', 'tooltip', 'delayHighlight', 'milestone'];" in app_js
        assert 'function initializeDisplaySettings()' in app_js
        assert "queryList(params, 'hideLayers').forEach((layer) => hideDisplayLayer(layer));" in app_js
        assert 'highlightToggle.checked = false;' in app_js
        assert "chartBody.addEventListener('mousemove'" in app_js
        assert "chartBody.addEventListener('click'" in app_js
        assert 'if (!event.metaKey && !event.ctrlKey)' in app_js
        assert "if (event.key !== 'Escape')" in app_js
        assert 'pinnedTaskIds.clear();' in app_js
        assert 'pinnedDateIndexes.clear();' in app_js
        assert 'warningWindow' not in app_js
        assert 'warning-toggle' not in app_js
        assert "highlightToggle.addEventListener('change'" in app_js
        assert "const tooltipToggle = document.querySelector('[data-tooltip-toggle]');" in app_js
        assert "const delayHighlightToggle = document.querySelector('[data-delay-highlight-toggle]');" in app_js
        assert "const tooltip = document.querySelector('.app-tooltip');" in app_js
        assert 'let tooltipsEnabled = tooltipToggle ? tooltipToggle.checked : true;' in app_js
        assert 'let delayHighlightEnabled = delayHighlightToggle ? delayHighlightToggle.checked : true;' in app_js
        assert 'function setDelayHighlightEnabled(enabled)' in app_js
        assert 'function normalizeTooltipText(value)' in app_js
        assert 'function isOverflowing(element)' in app_js
        assert 'function showTooltip(event, text)' in app_js
        assert 'function bindCellTooltips()' in app_js
        assert 'function bindPlanBarTooltips()' in app_js
        assert 'function setTooltipsEnabled(enabled)' in app_js
        assert 'function formatActualPeriod(actualStart, actualEnd)' in app_js
        assert "tooltipToggle.addEventListener('change'" in app_js
        assert "delayHighlightToggle.addEventListener('change'" in app_js
        assert "const sourceDownload = document.querySelector('[data-source-download]');" in app_js
        assert 'function downloadSourceJson(event)' in app_js
        assert "document.getElementById('wbsgen-source')" in app_js
        assert "new Blob([jsonText], {type: 'application/json'})" in app_js
        assert 'URL.createObjectURL(blob)' in app_js
        assert 'URL.revokeObjectURL(url)' in app_js
        assert "sourceDownload.addEventListener('click'" in app_js
        assert plan_bar_tooltip_block is not None
        assert 'const taskName = normalizeTooltipText(bar.dataset.taskName);' in plan_bar_tooltip_block.group('body')
        assert "bar.dataset.delayState === 'delayed'" in plan_bar_tooltip_block.group('body')
        assert 'bar.dataset.expectedProgressLabel' in plan_bar_tooltip_block.group('body')
        assert '進捗: ${progressLabel}（遅延 / 期待 ${expectedProgressLabel}）' in plan_bar_tooltip_block.group('body')
        assert 'taskName,' in plan_bar_tooltip_block.group('body')

    def test_render_html_js_defines_column_visibility_state(self):
        from wbsgen.render import html
        script = html.read_text_asset('app.js')
        assert 'function setColumnHidden(column, hidden)' in script
        assert 'function updateColumnVisibilityUI(column)' in script
        assert "cell.classList.toggle('is-hidden-column', hidden);" in script
        assert 'checkbox.checked = !hidden;' in script
        assert "const columnKeyMap = {assignee: 'assignee', planned: 'planned-period', actual: 'actual-period', progress: 'progress', expected: 'expected-progress', issue: 'issue', comment: 'comment'};" in script
        assert 'function initializeColumnVisibility(displaySettings, params)' in script
        assert "queryList(params, 'hideColumns').forEach((key) => {" in script
        assert 'if (!Array.isArray(values)) {' in script
        assert 'if (!Array.isArray(values) || values.length === 0)' not in script
        assert 'hidePlannedPeriodColumn' not in script
        assert 'hideActualPeriodColumn' not in script
        assert "const columnVisibilityToggle = event.target.closest('[data-column-visibility-toggle]');" in script
        assert "const columnVisibilityAction = event.target.closest('[data-column-visibility-action]');" in script
        assert 'function applyColumnOrder(view)' in script
        assert 'function normalizeColumnOrder(order, defaults)' in script
        assert "const columnOrderButton = event.target.closest('[data-column-order][data-direction]');" in script

    def test_render_html_js_supports_standard_and_analysis_order_query(self):
        from wbsgen.render import html
        script = html.read_text_asset('app.js')
        assert "const standardQueryOrder = queryList(params, 'standardOrder');" in script
        assert "const analysisQueryOrder = queryList(params, 'analysisOrder');" in script
        assert 'columnOrders.standard = standardQueryOrder.length ? normalizeColumnOrder(standardQueryOrder, standardBase) : standardBase;' in script
        assert 'columnOrders.analysis = analysisQueryOrder.length ? normalizeColumnOrder(analysisQueryOrder, analysisBase) : analysisBase;' in script

    def test_render_html_js_supports_column_widths_query(self):
        from wbsgen.render import html
        script = html.read_text_asset('app.js')
        assert 'function queryColumnWidths(params)' in script
        assert "defaultTaskNameWidth: columnWidthOverrides.name ?? Number(leftHead?.dataset.taskNameWidth || '220')," in script
        assert "defaultAssigneeWidth: columnWidthOverrides.assignee ?? Number(leftHead?.dataset.assigneeWidth || '56')," in script
        assert "defaultCommentWidth: columnWidthOverrides.comment ?? Number(leftHead?.dataset.commentWidth || '220')," in script

class TestTestRenderGanttChartTests:

    def test_render_bar_uses_date_boundary_edges_as_outer_edges(self):
        html = wbsgen.render_bar('bar plan task-bar', left=32, right=544, top=10, height=12, attributes='data-kind="planned"')
        assert 'style="left:32px;top:10px;width:512px;height:12px;"' in html

    def build_result_for_gantt(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        return (data, wbsgen.build_project_model(data, today=date(2026, 6, 18)))

    def test_render_wbs_table_outputs_analysis_columns_and_tabs(self):
        data = {'project': {'name': '分析タブ確認', 'statusDate': '2026-06-09'}, 'tasks': [{'id': '1', 'name': '対象タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 10, 'progress': 40}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 9))
        rendered = wbsgen.render_html(data, result)
        assert 'data-wbs-view-target="standard"' in rendered
        assert 'data-wbs-view-target="analysis"' in rendered
        assert 'data-column="delta"' in rendered
        assert 'data-column="delay"' in rendered
        assert 'data-column="pace"' in rendered
        assert '>差分<' in rendered
        assert '>遅れ営業日<' in rendered
        assert '>必要ペース<' in rendered
        assert '>-20pt<' in rendered
        assert '>2日<' in rendered

    def test_render_html_outputs_split_gantt_header_weekends_and_status_date_background(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'class="workspace"' in html
        assert 'class="left-pane"' in html
        assert 'class="left-head"' in html
        assert 'class="wbs-row' in html
        assert 'class="right-pane"' in html
        assert 'class="right-pane" style="--chart-w:160px;--gantt-right-gutter:24px;"' in html
        assert 'class="right-head"' in html
        assert 'class="right-head" style="width:160px;"' in html
        assert 'class="chart-body" style="width:160px;height:64px;"' in html
        assert 'class="chart-grid" style="width:160px;height:64px;"' in html
        assert 'class="print-grid" width="160" height="64" viewBox="0 0 160 64"' in html
        assert html.count('class="print-grid-line"') == 6
        assert '<line class="print-grid-line" x1="160" y1="0" x2="160" y2="64" />' in html
        assert 'width="160" height="64" viewBox="0 0 160 64"' in html
        assert 'class="chart-grid"' in html
        assert 'data-date="2026-06-05"' in html
        assert 'data-date="2026-06-09"' in html
        assert 'class="weekend-bg"' in html
        assert 'data-date="2026-06-06"' in html
        assert 'data-date="2026-06-07"' in html
        assert 'class="status-date-bg"' in html
        assert 'data-status-date="2026-06-08"' in html
        assert 'class="gantt-status-date"' not in html
        assert "const workspace = document.querySelector('.workspace');" in html
        assert "document.querySelectorAll('.left-pane, .right-pane')" in html
        assert 'workspace.scrollTop += event.deltaY;' in html

    def test_render_html_outputs_planned_and_actual_lines_by_display_row(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-12', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '完了', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-01', 'actualEnd': '2026-06-05', 'progress': 100}, {'id': '1.2', 'name': '進行中', 'plannedStart': '2026-06-08', 'plannedDuration': 5, 'actualStart': '2026-06-09', 'actualEnd': None, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert re.search('class="bar plan parent-bar(?: delayed)?"', html)
        assert 'class="bar plan task-bar"' in html
        assert 'class="bar progress parent-bar"' in html
        assert 'class="bar progress task-bar"' in html
        assert 'class="bar actual actual-complete task-bar"' in html
        assert 'class="bar actual actual-ongoing task-bar"' in html
        assert 'data-kind="planned"' in html
        assert 'data-kind="progress"' in html
        assert 'data-kind="actual"' in html
        assert 'data-progress="50"' in html
        assert 'data-task-id="1.1"' in html
        assert 'data-task-id="1.2"' in html
        assert 'data-actual-end="2026-06-05"' in html
        assert 'data-actual-end="2026-06-10"' in html
        assert html.index('data-kind="planned"') < html.index('data-kind="progress"')
        assert html.index('data-kind="progress"') < html.index('data-kind="actual"')

    def test_render_html_includes_clipped_plans_in_inazuma_progress_points(self):
        data = {'project': {'name': 'クリップ確認', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '範囲内', 'plannedStart': '2026-06-02', 'plannedDuration': 3, 'progress': 50}, {'id': '2', 'name': '左クリップ', 'plannedStart': '2026-05-28', 'plannedDuration': 7, 'progress': 50}, {'id': '3', 'name': '右クリップ', 'plannedStart': '2026-06-08', 'plannedDuration': 5, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker left"' in html
        assert 'class="clip-marker right"' in html
        assert re.search('<circle class="gantt-progress-point"[^>]*data-task-id="1"', html)
        assert re.search('<circle class="gantt-progress-point"[^>]*data-task-id="2"', html)
        assert re.search('<circle class="gantt-progress-point"[^>]*data-task-id="3"', html)
        assert 'points="160,0 80,16 48,48 304,80 160,96"' in html

    def test_render_html_outputs_left_clip_marker_for_plan_start_before_display_range(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '左クリップ', 'plannedStart': '2026-05-28', 'plannedDuration': 7, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker left"' in html
        assert 'data-clip="start"' in html
        assert 'data-task-id="1"' in html

    def test_render_html_outputs_right_clip_marker_for_plan_end_after_display_range(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '右クリップ', 'plannedStart': '2026-06-08', 'plannedDuration': 5, 'progress': 20}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker right"' in html
        assert 'data-clip="end"' in html
        assert 'data-task-id="1"' in html

    def test_render_html_outputs_both_clip_markers_for_plan_spanning_display_range(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '左右クリップ', 'plannedStart': '2026-05-28', 'plannedDuration': 12, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker left"' in html
        assert 'class="clip-marker right"' in html

    def test_render_html_uses_unclamped_planned_bar_coordinates_for_partial_clip(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '左クリップ', 'plannedStart': '2026-05-28', 'plannedDuration': 7, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="bar plan task-bar delayed" style="left:-128px;' in html

    def test_render_html_outputs_left_outside_only_clip_without_plan_bar(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '完全に範囲前', 'plannedStart': '2026-05-20', 'plannedDuration': 3, 'progress': 0}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker left outside-only"' in html
        assert 'class="bar plan task-bar"' not in html

    def test_render_html_outputs_right_outside_only_clip_without_plan_bar(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '完全に範囲後', 'plannedStart': '2026-06-15', 'plannedDuration': 3, 'progress': 0}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="clip-marker right outside-only"' in html
        assert 'class="bar plan task-bar"' not in html

    def test_render_html_does_not_output_clip_marker_for_in_range_plan(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '範囲内', 'plannedStart': '2026-06-02', 'plannedDuration': 3, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'data-kind="planned-clip"' not in html
        assert 'class="bar plan task-bar' in html

    def test_render_html_outputs_footer_space_sized_for_meta_info(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-03', 'statusDate': '2026-06-02'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'class="chart-body" style="width:96px;height:64px;"' in html
        assert 'class="chart-grid" style="width:96px;height:64px;"' in html
        assert '<div class="chart-footer-space" aria-hidden="true"></div>' in html
        assert 'height="64" viewBox="0 0 96 64"' in html

    def test_render_html_outputs_highlight_toggle_in_view_menu(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'class="view-menu-section-title">レイヤー</div>' in html
        assert 'data-highlight-toggle checked>ハイライト</label>' in html

    def test_render_html_outputs_tooltip_toggle_in_view_menu(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'data-tooltip-toggle checked>ツールチップ</label>' in html

    def test_render_html_outputs_delay_highlight_toggle_and_css(self):
        from wbsgen.render import html as render_html_module
        data = {'project': {'name': '個人開発', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '遅延タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 10, 'progress': 20}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        rendered = wbsgen.render_html(data, result)
        css = render_html_module.read_text_asset('style.css')
        assert '遅延強調' in rendered
        assert 'data-delay-highlight-toggle checked' in rendered
        assert '--delay-plan-line: #c56f09;' in css
        assert '--delay-parent-line: #a45f13;' in css
        assert '.gantt-row .bar.plan.delayed' in css
        assert '.gantt-row.project .bar.plan.delayed' in css
        assert '.app.is-delay-highlight-hidden .bar.plan.delayed' in css

    def test_render_html_outputs_interaction_layer_and_position_metadata(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'class="interaction-layer"' in html
        assert 'aria-hidden="true"' in html
        assert 'data-chart-start-date="2026-06-05"' in html
        assert 'data-day-width="32"' in html
        assert 'data-row-height="32"' in html
        assert html.index('class="interaction-layer"') < html.index('class="chart-bg"')

    def test_render_html_uses_compact_plan_and_progress_bar_heights(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-05', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '進捗あり', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 40}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        assert 'data-row-height="32"' in html
        assert re.search('class="bar plan task-bar(?: delayed)?" style="left:0px;top:10px;width:160px;height:12px;"', html)
        assert 'class="bar progress task-bar" style="left:0px;top:12px;width:64px;height:8px;"' in html

    def test_render_html_outputs_inazuma_polyline_after_task_bars(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-16', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '未着手', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 0}, {'id': '1.2', 'name': '進行中', 'plannedStart': '2026-06-01', 'plannedDuration': 8, 'actualStart': '2026-06-03', 'actualEnd': None, 'progress': 50}, {'id': '1.3', 'name': '完了', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-01', 'actualEnd': '2026-06-05', 'progress': 100}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'class="gantt-inazuma"' in html
        assert 'data-kind="inazuma"' in html
        assert 'class="gantt-progress-point"' in html
        assert 'data-task-id="1.1"' in html
        assert 'data-task-id="1.2"' in html
        assert 'data-task-id="1.3"' in html
        assert html.index('data-kind="actual"') < html.index('data-kind="inazuma"')

    def test_render_html_outputs_month_labels_only_for_three_or_more_displayed_days(self):
        data = {'project': {'name': '月跨ぎ', 'startDate': '2026-05-31', 'endDate': '2026-07-03', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '月跨ぎタスク', 'plannedStart': '2026-06-01', 'plannedDuration': 5}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '>2026年5月<' not in html
        assert '>2026年6月<' in html
        assert '>2026年7月<' in html

    def test_render_html_covers_issue_6_visual_conditions(self):
        data = {'project': {'name': 'Issue 6網羅', 'startDate': '2026-06-01', 'endDate': '2026-06-16', 'statusDate': '2026-06-10', 'issueBaseUrl': 'https://github.com/your_account/your_repo/issues/'}, 'tasks': [{'id': '1', 'name': '進捗可視化'}, {'id': '1.1', 'name': '0%ケース', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 0, 'issue': 611}, {'id': '1.2', 'name': '土日を挟む50%', 'plannedStart': '2026-06-01', 'plannedDuration': 6, 'actualStart': '2026-06-03', 'actualEnd': None, 'progress': 50, 'issue': 612}, {'id': '1.3', 'name': '完了100%', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-01', 'actualEnd': '2026-06-06', 'progress': 100, 'issue': 613}, {'id': '1.4', 'name': '実績開始が後ろ', 'plannedStart': '2026-06-01', 'plannedDuration': 8, 'actualStart': '2026-06-10', 'actualEnd': None, 'progress': 30, 'issue': 614}, {'id': '1.5', 'name': '未計画', 'actualStart': '2026-06-03', 'actualEnd': None, 'progress': 40, 'issue': 615}, {'id': '1.6', 'name': '土日開始警告', 'plannedStart': '2026-06-06', 'plannedDuration': 3, 'progress': 50, 'issue': 616}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'Issue 6網羅' in html
        assert 'TASK_UNPLANNED' in html
        assert 'TASK_PLANNED_START_WEEKEND' in html
        assert 'class="status-date-bg"' in html
        assert 'class="weekend-bg"' in html
        assert re.search('class="bar plan parent-bar(?: delayed)?"', html)
        assert 'class="bar progress parent-bar"' in html
        assert 'class="bar actual actual-ongoing task-bar"' in html
        assert 'class="gantt-inazuma"' in html
        assert '<a href="https://github.com/your_account/your_repo/issues/611">#611</a>' in html
        assert 'data-kind="actual" data-task-id="1.5"' in html
        assert 'data-task-id="1.5" data-kind="progress"' not in html
        assert 'data-task-id="1.5" />' not in html
        assert 'class="warning-window"' in html
        assert 'class="warning-window-head"' in html
        assert 'class="warning-window-body"' in html
        assert 'class="warning-window-close"' in html
        assert 'id="warnings-title"' in html
        assert 'aria-labelledby="warnings-title"' in html
        assert 'class="warning-drawer"' not in html
        assert 'ID: 1.5' in html

    def test_render_html_outputs_warning_window_open_by_default(self):
        data = {'project': {'name': '警告ウィンドウ', 'startDate': '2026-06-01', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '未計画'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 3))
        html = wbsgen.render_html(data, result)
        assert '<input class="warning-checkbox" type="checkbox" id="warning-toggle" checked>' in html
        assert '<label class="warning-toggle" for="warning-toggle"' in html
        assert 'aria-controls="warning-window"' in html
        assert 'class="warning-window"' in html
        assert 'id="warning-window"' in html
        assert 'aria-labelledby="warnings-title"' in html

    def test_render_html_omits_warning_window_when_there_are_no_warnings(self):
        data = {'project': {'name': '警告なし', 'startDate': '2026-06-01', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '計画済み', 'plannedStart': '2026-06-01', 'plannedDuration': 2, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 3))
        html = wbsgen.render_html(data, result)
        assert 'id="warning-window"' not in html
        assert 'class="warning-window"' not in html
        assert 'id="warning-toggle"' not in html
        assert 'class="warning-toggle"' not in html

class TestHolidayRenderingTests:
    """Issue #61 Task 7: HTML表示の失敗テスト (RED phase).

    render_html() does not yet receive/consult holiday information at all,
    so every test in this class is expected to fail until Task 8 implements
    holiday-aware rendering.
    """

    def test_render_html_outputs_holiday_background_on_gantt_chart(self):
        data = {'project': {'name': '休日背景', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}], 'holidays': [{'date': '2026-06-08', 'name': '会社設立記念日'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        holiday_bg = re.search('<div class="weekend-bg"[^>]*data-date="2026-06-08"[^>]*>', html)
        assert holiday_bg is not None
        assert 'data-holiday-name="会社設立記念日"' in holiday_bg.group(0) or 'title="会社設立記念日"' in holiday_bg.group(0)

    def test_render_html_outputs_holiday_class_in_day_header(self):
        data = {'project': {'name': '休日ヘッダー', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}], 'holidays': [{'date': '2026-06-08', 'name': '会社設立記念日'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        day_header_cell = re.search('<div class="(?P<cls>[^"]*)"[^>]*data-date="2026-06-08"[^>]*>', html)
        assert day_header_cell is not None
        assert 'sun' in day_header_cell.group('cls')
        assert 'data-holiday-name="会社設立記念日"' in day_header_cell.group(0) or 'title="会社設立記念日"' in day_header_cell.group(0)
        assert 'data-layer="holiday"' not in html
        assert 'class="legend-item" data-holiday-legend' not in html

    def test_render_html_does_not_mark_ordinary_weekday_as_holiday(self):
        data = {'project': {'name': '休日なし', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        day_header_cell = re.search('<div class="(?P<cls>[^"]*)"[^>]*data-date="2026-06-08"[^>]*>', html)
        assert day_header_cell is not None
        assert 'sun' not in day_header_cell.group('cls')

    def build_holiday_result(self, *, include_warning_trigger=False):
        tasks = [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 20}]
        if include_warning_trigger:
            tasks.append({'id': '2', 'name': '未計画'})
        data = {'project': {'name': '休日一覧', 'startDate': '2026-06-01', 'endDate': '2026-06-25', 'statusDate': '2026-06-10'}, 'tasks': tasks, 'holidays': [{'date': '2026-06-08', 'name': '会社設立記念日'}, {'date': '2026-06-15'}, {'date': '2026-06-22', 'name': '特別休暇'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        return (data, result)

    def test_render_html_outputs_holiday_toggle_and_window_when_holidays_present(self):
        data, result = self.build_holiday_result()
        html = wbsgen.render_html(data, result)
        assert 'class="holiday-toggle"' in html
        assert '休日 3件' in html
        assert 'aria-controls="holiday-window"' in html
        assert 'class="holiday-window"' in html
        assert 'id="holiday-window"' in html
        assert 'aria-labelledby="holidays-title"' in html
        assert '<li><span class="holiday-date">2026-06-08</span><span class="holiday-name">会社設立記念日</span></li>' in html
        assert '<li><span class="holiday-date">2026-06-15</span></li>' in html
        assert 'class="holiday-name"></span>' not in html
        assert '<li><span class="holiday-date">2026-06-22</span><span class="holiday-name">特別休暇</span></li>' in html

    def test_render_html_omits_holiday_toggle_and_window_when_no_holidays(self):
        data = {'project': {'name': '休日なし一覧', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 2, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 3))
        html = wbsgen.render_html(data, result)
        assert 'id="holiday-window"' not in html
        assert 'class="holiday-window"' not in html
        assert 'id="holiday-toggle"' not in html
        assert 'class="holiday-toggle"' not in html

    def test_render_html_holiday_window_starts_closed_even_with_warnings(self):
        data, result = self.build_holiday_result(include_warning_trigger=True)
        assert result.validation.warnings
        html = wbsgen.render_html(data, result)
        assert '<input class="holiday-checkbox" type="checkbox" id="holiday-toggle">' in html
        assert 'id="holiday-toggle" checked>' not in html
        assert '<input class="warning-checkbox" type="checkbox" id="warning-toggle" checked>' in html

    def test_render_html_dock_window_attributes_present_for_both_windows(self):
        data, result = self.build_holiday_result(include_warning_trigger=True)
        assert result.validation.warnings
        html = wbsgen.render_html(data, result)
        warning_aside = re.search('<aside class="warning-window"[^>]*>', html)
        holiday_aside = re.search('<aside class="holiday-window"[^>]*>', html)
        assert warning_aside is not None
        assert holiday_aside is not None
        assert 'data-dock-window' in warning_aside.group(0)
        assert 'data-dock-window' in holiday_aside.group(0)

    def test_app_js_contains_dock_window_management_hooks(self):
        from wbsgen.render import html as render_html_module
        app_js = render_html_module.read_text_asset('app.js')
        assert 'data-dock-window' in app_js
        assert 'function initializeDockWindows()' in app_js

    def test_render_html_embeds_holidays_in_reference_source_json(self):
        data, result = self.build_holiday_result()
        html = wbsgen.render_html(data, result)
        script_match = re.search('<script type="application/json" id="wbsgen-source">\\n(?P<json>.*?)\\n\\s*</script>', html, re.DOTALL)
        assert script_match is not None
        embedded = script_match.group('json')
        assert '"holidays"' in embedded
        assert '"date": "2026-06-08"' in embedded
        assert '"name": "会社設立記念日"' in embedded
        assert '"date": "2026-06-15"' in embedded
        assert '"date": "2026-06-22"' in embedded
        assert '"name": "特別休暇"' in embedded

    def test_render_html_expected_progress_column_is_holiday_aware(self):
        data = {'project': {'name': '期待進捗', 'startDate': '2026-06-01', 'endDate': '2026-06-30', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 20}], 'holidays': [{'date': '2026-06-03', 'name': '会社設立記念日'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        html = wbsgen.render_html(data, result)
        expected_cell = re.search('<div class="wbs-cell right" data-column="expected-progress"[^>]*><span class="progress-pill">(?P<value>[^<]*)</span>', html)
        assert expected_cell is not None
        assert expected_cell.group('value') == '60%', 'expected-progress must use holiday-aware business-day math (60%), not weekend-only math (67%)'

    def test_render_html_progress_point_x_is_holiday_aware(self):
        data = {'project': {'name': '進捗点', 'startDate': '2026-06-01', 'endDate': '2026-06-30', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 60}], 'holidays': [{'date': '2026-06-03', 'name': '会社設立記念日'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 5))
        rows = wbsgen.flatten_computed_tasks(result.computed_roots)
        scale = wbsgen.ChartScale(result.display_start_date, result.display_end_date)
        calendar = wbsgen.WorkCalendar(holidays=tuple(result.holidays))
        holiday_point = wbsgen.progress_point_for_row(rows[0], 0, scale, result.project, calendar)
        weekend_point = wbsgen.progress_point_for_row(rows[0], 0, scale, result.project)
        assert holiday_point[0] != weekend_point[0]
        html = wbsgen.render_html(data, result)
        progress_x_match = re.search('data-progress-x="(?P<x>-?\\d+)"', html)
        assert progress_x_match is not None
        assert int(progress_x_match.group('x')) == holiday_point[0]

class TestRenderHtmlTests:

    def test_render_html_groups_topbar_into_identity_and_actions_clusters(self):
        data = {'project': {'name': 'クラスタ確認', 'statusDate': '2026-06-10'}, 'tasks': []}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        html = wbsgen.render_html(data, result)
        identity_idx = html.index('<div class="topbar-identity">')
        summary_idx = html.index('<div class="summary">')
        actions_idx = html.index('<div class="topbar-actions">')
        search_idx = html.index('class="search-summary"')
        legend_idx = html.index('class="legend"')
        assert identity_idx < summary_idx < actions_idx < search_idx < legend_idx

    def evaluate_search_state(self, data, *, query=''):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'search-state.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json, sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nhtml_path = Path(sys.argv[1]).resolve()\nquery = sys.argv[2]\nwith sync_playwright() as p:\n    browser = p.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    try:\n        page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n        page.goto(f\'{html_path.as_uri()}{query}\')\n        page.wait_for_timeout(150)\n        print(json.dumps(page.evaluate("""() => ({\n          summary: document.querySelector(\'[data-search-summary]\')?.textContent,\n          visibleTaskIds: Array.from(document.querySelectorAll(\'.wbs-row[data-task-id]\')).filter((row) => getComputedStyle(row).display !== \'none\').map((row) => row.dataset.taskId),\n          visibleGanttTaskIds: Array.from(document.querySelectorAll(\'.gantt-row[data-task-id]\')).filter((row) => getComputedStyle(row).display !== \'none\').map((row) => row.dataset.taskId),\n          chartHeight: document.querySelector(\'.chart-body\')?.style.height,\n          highlightedTaskIds: Array.from(document.querySelectorAll(\'.wbs-row.is-search-match\')).map((row) => row.dataset.taskId),\n          ganttHighlightedTaskIds: Array.from(document.querySelectorAll(\'.gantt-row.is-search-match\')).map((row) => row.dataset.taskId),\n        })""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path), query], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def test_browser_filters_direct_matches_and_ancestors(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '対象タスク', 'plannedStart': '2026-06-09', 'plannedDuration': 1}, {'id': '1.2', 'name': '対象外', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=%E5%AF%BE%E8%B1%A1%E3%82%BF%E3%82%B9%E3%82%AF&fields=name&mode=filter')
        assert state['visibleTaskIds'] == ['1', '1.1']
        assert state['visibleGanttTaskIds'] == ['1', '1.1']
        assert state['chartHeight'] == '96px'
        assert state['highlightedTaskIds'] == []
        assert state['summary'] == '検索 1件'

    def test_browser_filters_tasks_matching_all_terms_across_selected_fields(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '設計', 'comment': 'レビュー対象', 'plannedStart': '2026-06-09', 'plannedDuration': 1}, {'id': '1.2', 'name': '設計だけ', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=%E8%A8%AD%E8%A8%88%20%E3%83%AC%E3%83%93%E3%83%A5%E3%83%BC&fields=name,comment&mode=filter')
        assert state['visibleTaskIds'] == ['1', '1.1']
        assert state['visibleGanttTaskIds'] == ['1', '1.1']
        assert state['summary'] == '検索 1件'

    def test_browser_excludes_tasks_matching_exclusion_term(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '設計レビュー', 'comment': '進行中', 'plannedStart': '2026-06-09', 'plannedDuration': 1}, {'id': '1.2', 'name': '設計レビュー', 'comment': '完了', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=%E8%A8%AD%E8%A8%88%20-%E5%AE%8C%E4%BA%86&fields=name,comment&mode=highlight')
        assert state['visibleTaskIds'] == ['1', '1.1', '1.2']
        assert state['highlightedTaskIds'] == ['1.1']
        assert state['ganttHighlightedTaskIds'] == ['1.1']
        assert state['summary'] == '検索 1件'

    def test_browser_filters_with_exclusion_terms_only(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '進行中', 'plannedStart': '2026-06-09', 'plannedDuration': 1}, {'id': '1.2', 'name': '完了', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=-完了&fields=name&mode=filter')
        assert state['visibleTaskIds'] == ['1', '1.1']
        assert state['visibleGanttTaskIds'] == ['1', '1.1']
        assert state['summary'] == '検索 2件'

    def test_browser_treats_dash_only_as_no_search_condition(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '子', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=-&fields=name&mode=filter')
        assert state['visibleTaskIds'] == ['1', '1.1']
        assert state['visibleGanttTaskIds'] == ['1', '1.1']
        assert state['summary'] == '検索 0件'

    def test_browser_highlights_issue_with_or_without_hash_without_filtering(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '対象', 'issue': 138, 'plannedStart': '2026-06-09', 'plannedDuration': 1}, {'id': '1.2', 'name': '対象外', 'issue': 139, 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        state = self.evaluate_search_state(data, query='?keyword=%23138&fields=issue&mode=highlight')
        assert state['visibleTaskIds'] == ['1', '1.1', '1.2']
        assert state['highlightedTaskIds'] == ['1.1']
        assert state['ganttHighlightedTaskIds'] == ['1.1']
        assert state['summary'] == '検索 1件'

    def test_browser_uses_defaults_for_invalid_search_query_values(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': 'リリース準備'}, {'id': '2', 'name': '対象外'}]}
        state = self.evaluate_search_state(data, query='?keyword=%20%E3%83%AA%E3%83%AA%E3%83%BC%E3%82%B9%20&fields=unknown&mode=unknown')
        assert state['visibleTaskIds'] == ['1']
        assert state['highlightedTaskIds'] == []
        assert state['summary'] == '検索 1件'

    def test_browser_hides_all_rows_for_zero_filter_results(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': 'リリース準備'}, {'id': '2', 'name': '対象外'}]}
        state = self.evaluate_search_state(data, query='?keyword=%E8%A9%B2%E5%BD%93%E3%81%AA%E3%81%97&fields=name&mode=filter')
        assert state['visibleTaskIds'] == []
        assert state['visibleGanttTaskIds'] == []
        assert state['chartHeight'] == '32px'
        assert state['summary'] == '検索 0件'

    def test_browser_search_controls_preserve_mode_and_location(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '対象', 'assignee': '担当者A'}, {'id': '2', 'name': '対象外', 'assignee': '担当者B'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'search-controls.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json, sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nhtml_path = Path(sys.argv[1]).resolve()\nwith sync_playwright() as p:\n    browser = p.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    try:\n        page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n        page.goto(f\'{html_path.as_uri()}?keyword=%E5%AF%BE%E8%B1%A1&fields=name&mode=filter\')\n        page.locator(\'[data-search-summary]\').click()\n        page.locator(\'[data-search-field="all"]\').uncheck()\n        page.locator(\'[data-search-field="assignee"]\').check()\n        page.locator(\'[data-search-mode="highlight"]\').check()\n        page.locator(\'[data-search-clear]\').click()\n        after_clear = page.evaluate(\'\'\'() => ({\n          drawerOpen: !document.querySelector(\'[data-search-drawer]\').hidden,\n          keyword: document.querySelector(\'[data-search-keyword]\').value,\n          allChecked: document.querySelector(\'[data-search-field="all"]\').checked,\n          mode: document.querySelector(\'[data-search-mode="highlight"]\').checked ? \'highlight\' : \'filter\',\n          location: window.location.search,\n        })\'\'\')\n        page.keyboard.press(\'Escape\')\n        after_escape = page.evaluate(\'\'\'() => !document.querySelector(\'[data-search-drawer]\').hidden\'\'\')\n        page.locator(\'[data-search-close]\').click()\n        drawer_closed = page.evaluate(\'\'\'() => document.querySelector(\'[data-search-drawer]\').hidden\'\'\')\n        print(json.dumps({\n          \'afterClear\': after_clear,\n          \'afterEscapeDrawerOpen\': after_escape,\n          \'drawerClosed\': drawer_closed,\n        }))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            state = json.loads(proc.stdout)
        assert state['afterClear'] == {'drawerOpen': True, 'keyword': '', 'allChecked': True, 'mode': 'highlight', 'location': '?keyword=%E5%AF%BE%E8%B1%A1&fields=name&mode=filter'}
        assert state['afterEscapeDrawerOpen']
        assert state['drawerClosed']

    def test_topbar_wraps_into_two_rows_below_1024px(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = {'project': {'name': 'WBS-GEN 視覚確認サンプル', 'startDate': '2026-05-31', 'endDate': '2026-08-03', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-01', 'plannedDuration': 2, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'topbar-wrap.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json, sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nhtml_path = Path(sys.argv[1]).resolve()\nwith sync_playwright() as p:\n    browser = p.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    try:\n        results = {}\n        for width in (1280, 1024, 980):\n            page = browser.new_page(viewport={\'width\': width, \'height\': 400})\n            page.goto(html_path.as_uri())\n            results[str(width)] = page.evaluate("""() => {\n              function rect(sel) {\n                const el = document.querySelector(sel);\n                const r = el.getBoundingClientRect();\n                return {top: Math.round(r.top), height: Math.round(r.height)};\n              }\n              return {\n                topbar: rect(\'.topbar\'),\n                identity: rect(\'.topbar-identity\'),\n                actions: rect(\'.topbar-actions\'),\n                summary: rect(\'.summary\'),\n                legend: rect(\'.legend\'),\n              };\n            }""")\n            page.close()\n        print(json.dumps(results))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            results = json.loads(proc.stdout)
        assert results['1280']['topbar']['height'] == 48
        assert abs(results['1280']['identity']['top'] - results['1280']['actions']['top']) < 20, '1280px: 同じ行にあるはずのアイデンティティ系/アクション系のtopが乖離している'
        for width in ('1024', '980'):
            assert results[width]['actions']['top'] - results[width]['identity']['top'] >= 20, f'{width}px: アクション系がアイデンティティ系と別行に段組みされていない'
            assert results[width]['summary']['height'] == results['1280']['summary']['height'], f'{width}px: .summaryが折返している'
            assert results[width]['legend']['height'] == results['1280']['legend']['height'], f'{width}px: .legendが折返している'

    def evaluate_source_download(self, source_text):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = {'project': {'name': 'ダウンロード確認', 'statusDate': '2026-06-18'}, 'tasks': []}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'source-download.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = 'import json,sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nhtml_path = Path(sys.argv[1]).resolve()\nsource_text = json.loads(sys.argv[2])\nwith sync_playwright() as p:\n b=p.chromium.launch(headless=True,args=[\'--disable-gpu\',\'--disable-dev-shm-usage\']);q=b.new_page()\n q.goto(html_path.as_uri());q.wait_for_timeout(150)\n if source_text is None: q.locator(\'#wbsgen-source\').evaluate(\'(element) => element.remove()\')\n else: q.locator(\'#wbsgen-source\').evaluate(\'(element, value) => { element.textContent = value; }\', source_text)\n q.evaluate("""() => {\n   const capture = {}; window.__sourceDownloadCapture = capture;\n   URL.createObjectURL = (blob) => { capture.blob = blob; return \'blob:source-download\'; };\n   URL.revokeObjectURL = () => {};\n   HTMLAnchorElement.prototype.click = function() { capture.filename = this.download; };\n }""")\n q.locator(\'[data-source-download]\').evaluate(\'(element) => element.click()\')\n print(json.dumps(q.evaluate("""async () => {\n   const capture = window.__sourceDownloadCapture;\n   return {filename: capture.filename, text: await capture.blob.text(), dialog: Boolean(document.querySelector(\'dialog\')), notification: Boolean(document.querySelector(\'[role="status"], [role="alert"]\'))};\n }"""), ensure_ascii=False));b.close()'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path), json.dumps(source_text)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def test_source_download_exports_normalized_source_or_fixed_error_json(self):
        source_data = {'project': {'name': 'ダウンロード確認'}, 'tasks': []}
        normal = self.evaluate_source_download(json.dumps(source_data, ensure_ascii=False))
        assert normal['filename'] == 'wbsgen-source.json'
        assert normal['text'] == '{\n  "project": {\n    "name": "ダウンロード確認"\n  },\n  "tasks": []\n}\n'
        assert not normal['dialog']
        assert not normal['notification']
        expected_error = '{\n  "error": "埋め込みJSONが不正なため、正本データをダウンロードできません。"\n}\n'
        for label, source_text in {'marker missing': None, 'invalid JSON': '{', 'non-object': '[]', 'empty object': '{}'}.items():
            with nullcontext():
                downloaded = self.evaluate_source_download(source_text)
                assert downloaded['filename'] == 'wbsgen-source-error.json'
                assert downloaded['text'] == expected_error
                assert not downloaded['dialog']
                assert not downloaded['notification']

    def evaluate_wbs_view_tab_switch(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'wbs-view-tabs.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = 'import json,sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n b=p.chromium.launch(headless=True,args=[\'--disable-gpu\',\'--disable-dev-shm-usage\']); q=b.new_page()\n q.goto(Path(sys.argv[1]).resolve().as_uri()); q.wait_for_timeout(150)\n def s(): return q.evaluate("""() => ({view:document.documentElement.dataset.wbsView,planned:getComputedStyle(document.querySelector(\'[data-column=\\"planned-period\\"]\')).display,delta:getComputedStyle(document.querySelector(\'[data-column=\\"delta\\"]\')).display,disabled:document.querySelector(\'[data-column-visibility-toggle=\\"planned-period\\"]\').disabled})""")\n a=s(); q.click(\'[data-wbs-view-target=\\"analysis\\"]\'); q.wait_for_timeout(100); b1=s(); q.click(\'[data-wbs-view-target=\\"standard\\"]\'); q.wait_for_timeout(100); c=s(); print(json.dumps({\'a\':a,\'b\':b1,\'c\':c})); b.close()'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_display_state(self, data, *, query=''):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'display-state.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\nquery = sys.argv[2]\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(f"{html_path.as_uri()}{query}")\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => ({\n          commentHidden: document.querySelector(\'[data-column="comment"]\')?.classList.contains(\'is-hidden-column\') ?? null,\n          issueHidden: document.querySelector(\'[data-column="issue"]\')?.classList.contains(\'is-hidden-column\') ?? null,\n          assigneeHidden: document.querySelector(\'[data-column="assignee"]\')?.classList.contains(\'is-hidden-column\') ?? null,\n          actualLayerHidden: document.querySelector(\'.app\')?.classList.contains(\'is-layer-actual-hidden\') ?? null,\n          tooltipHidden: document.querySelector(\'.app\')?.classList.contains(\'is-tooltip-hidden\') ?? null,\n          commentToggleChecked: document.querySelector(\'[data-column-visibility-toggle="comment"]\')?.checked ?? null,\n          issueToggleChecked: document.querySelector(\'[data-column-visibility-toggle="issue"]\')?.checked ?? null,\n          assigneeToggleChecked: document.querySelector(\'[data-column-visibility-toggle="assignee"]\')?.checked ?? null,\n          actualToggleChecked: document.querySelector(\'[data-layer-target="actual"]\')?.checked ?? null,\n          tooltipToggleChecked: document.querySelector(\'[data-tooltip-toggle]\')?.checked ?? null\n        })""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path), query], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_column_layout_state(self, data, *, query=''):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'column-layout-state.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\nquery = sys.argv[2]\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(f"{html_path.as_uri()}{query}")\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => ({\n          standardOrder: Array.from(document.querySelectorAll(\'.left-head [data-column]\'))\n            .map((el) => el.dataset.column)\n            .filter((key) => [\'assignee\', \'planned-period\', \'actual-period\', \'progress\', \'expected-progress\', \'issue\'].includes(key)),\n          taskNameWidth: document.querySelector(\'.task-name-head\')?.getBoundingClientRect().width ?? null,\n          assigneeWidth: document.querySelector(\'.assignee-head\')?.getBoundingClientRect().width ?? null,\n          commentWidth: document.querySelector(\'.comment-head\')?.getBoundingClientRect().width ?? null\n        })""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path), query], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_sticky_resize_positions(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        data['display'] = {'standard': {'columns': {'visible': ['assignee', 'progress', 'issue']}}}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'sticky-resize.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 900, \'height\': 560}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => {\n          const workspace = document.querySelector(\'.workspace\');\n          const handle = document.querySelector(\'.pane-resize-handle\');\n          const leftHead = document.querySelector(\'.left-head\');\n          const before = {\n            handleLeft: handle.getBoundingClientRect().left,\n            leftHeadTop: leftHead.getBoundingClientRect().top\n          };\n          workspace.scrollLeft = 240;\n          workspace.scrollTop = 260;\n          return new Promise((resolve) => requestAnimationFrame(() => {\n            resolve({\n              before,\n              after: {\n                handleLeft: handle.getBoundingClientRect().left,\n                leftHeadTop: leftHead.getBoundingClientRect().top,\n                scrollLeft: workspace.scrollLeft,\n                scrollTop: workspace.scrollTop\n              }\n            });\n          }));\n        }""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_left_pane_stacking_during_horizontal_scroll(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'left-pane-stacking-scroll.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 900, \'height\': 560}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        page.evaluate("""() => {\n          const workspace = document.querySelector(\'.workspace\');\n          workspace.scrollLeft = 400;\n          workspace.scrollTop = 200;\n        }""")\n        page.wait_for_timeout(150)\n        print(json.dumps(page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const rect = leftPane.getBoundingClientRect();\n          const point = {x: rect.right - 50, y: 150};\n          const hit = document.elementFromPoint(point.x, point.y);\n          return {\n            hitIsInLeftPane: Boolean(hit && leftPane.contains(hit)),\n            hitClass: hit ? hit.className : null\n          };\n        }""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_pane_resize_after_task_name_expand(self, *, viewport_width=1000):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'pane-resize-after-task-name.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\nviewport_width = int(sys.argv[2])\n\ndef drag(page, selector, dx):\n    box = page.locator(selector).bounding_box()\n    x = box[\'x\'] + box[\'width\'] / 2\n    y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n    page.mouse.move(x, y)\n    page.mouse.down()\n    page.mouse.move(x + dx, y, steps=8)\n    page.mouse.up()\n    page.wait_for_timeout(100)\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': viewport_width, \'height\': 620}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const taskHead = document.querySelector(\'.task-name-head\');\n          return {\n            initialLeftWidth: leftPane.getBoundingClientRect().width,\n            initialTaskWidth: taskHead.getBoundingClientRect().width\n          };\n        }""")), flush=True)\n        drag(page, \'.task-name-resize-handle\', 180)\n        afterTask = page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const handle = document.querySelector(\'.pane-resize-handle\');\n          const taskHead = document.querySelector(\'.task-name-head\');\n          const handleRect = handle.getBoundingClientRect();\n          const hit = document.elementFromPoint(\n            handleRect.left + handleRect.width / 2,\n            handleRect.top + Math.min(handleRect.height / 2, 24)\n          );\n          return {\n            leftWidth: leftPane.getBoundingClientRect().width,\n            taskWidth: taskHead.getBoundingClientRect().width,\n            handleLeft: handleRect.left,\n            handleRight: handleRect.right,\n            viewportWidth: window.innerWidth,\n            hitClass: hit ? hit.className : null\n          };\n        }""")\n        drag(page, \'.pane-resize-handle\', -140)\n        afterPane = page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const taskHead = document.querySelector(\'.task-name-head\');\n          const commentHead = document.querySelector(\'.comment-head\');\n          return {\n            leftWidth: leftPane.getBoundingClientRect().width,\n            taskWidth: taskHead.getBoundingClientRect().width,\n            commentWidth: commentHead.getBoundingClientRect().width\n          };\n        }""")\n        print(json.dumps({ \'afterTask\': afterTask, \'afterPane\': afterPane }))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path), str(viewport_width)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            lines = [line for line in proc.stdout.splitlines() if line.strip()]
            return json.loads(lines[-1])

    def evaluate_pane_resize_overlap_stacking(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'pane-resize-overlap-stacking.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1200, \'height\': 700}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(200)\n        handle = page.locator(\'.pane-resize-handle\')\n        box = handle.bounding_box()\n        x = box[\'x\'] + box[\'width\'] / 2\n        y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n        page.mouse.move(x, y)\n        page.mouse.down()\n        page.mouse.move(x - 400, y, steps=10)\n        page.mouse.up()\n        page.wait_for_timeout(150)\n        print(json.dumps(page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const rightPane = document.querySelector(\'.right-pane\');\n          const leftPaneRect = leftPane.getBoundingClientRect();\n          const rightPaneRect = rightPane.getBoundingClientRect();\n          const overlapPoint = {x: leftPaneRect.right + 50, y: 120};\n          const hit = document.elementFromPoint(overlapPoint.x, overlapPoint.y);\n          const handleRect = document.querySelector(\'.pane-resize-handle\').getBoundingClientRect();\n          const handleHit = document.elementFromPoint(\n            handleRect.left + 2,\n            handleRect.top + 100\n          );\n          return {\n            leftPaneWidth: leftPaneRect.width,\n            rightPaneLeft: rightPaneRect.left,\n            hitInOverlapIsInRightPane: Boolean(hit && rightPane.contains(hit)),\n            handleStillHittable: Boolean(handleHit && handleHit.classList.contains(\'pane-resize-handle\'))\n          };\n        }""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_stacking_invariants_after_combined_scroll_and_resize(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'combined-scroll-resize-stacking.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1200, \'height\': 700}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(200)\n\n        handle = page.locator(\'.pane-resize-handle\')\n        box = handle.bounding_box()\n        x = box[\'x\'] + box[\'width\'] / 2\n        y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n        page.mouse.move(x, y)\n        page.mouse.down()\n        page.mouse.move(x - 400, y, steps=10)\n        page.mouse.up()\n        page.wait_for_timeout(150)\n\n        page.evaluate("""() => {\n          const workspace = document.querySelector(\'.workspace\');\n          workspace.scrollLeft = 300;\n          workspace.scrollTop = 200;\n        }""")\n        page.wait_for_timeout(150)\n\n        print(json.dumps(page.evaluate("""() => {\n          const leftPane = document.querySelector(\'.left-pane\');\n          const rightPane = document.querySelector(\'.right-pane\');\n          const leftPaneRect = leftPane.getBoundingClientRect();\n          const rightPaneRect = rightPane.getBoundingClientRect();\n\n          const scrollOverlapExists = rightPaneRect.left < leftPaneRect.right;\n          const frozenColumnPoint = {\n            x: (Math.max(rightPaneRect.left, 0) + leftPaneRect.right) / 2,\n            y: 150\n          };\n          const frozenHit = document.elementFromPoint(frozenColumnPoint.x, frozenColumnPoint.y);\n\n          const shrinkOverlapPoint = {x: leftPaneRect.right + 50, y: 150};\n          const shrinkHit = document.elementFromPoint(shrinkOverlapPoint.x, shrinkOverlapPoint.y);\n\n          const handleRect = document.querySelector(\'.pane-resize-handle\').getBoundingClientRect();\n          const handleHit = document.elementFromPoint(handleRect.left + 2, 150);\n\n          return {\n            scrollOverlapExists,\n            leftPaneWidth: leftPaneRect.width,\n            frozenColumnIsInLeftPane: Boolean(frozenHit && leftPane.contains(frozenHit)),\n            shrinkOverlapIsInRightPane: Boolean(shrinkHit && rightPane.contains(shrinkHit)),\n            handleStillHittable: Boolean(handleHit && handleHit.classList.contains(\'pane-resize-handle\'))\n          };\n        }""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_pane_resize_comment_follow(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'pane-resize-comment-follow.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n\n        def read_widths():\n            return page.evaluate("""() => ({\n              leftW: getComputedStyle(document.documentElement).getPropertyValue(\'--left-w\'),\n              commentW: getComputedStyle(document.documentElement).getPropertyValue(\'--comment-w\')\n            })""")\n\n        before = read_widths()\n        handle = page.locator(\'.pane-resize-handle\')\n        box = handle.bounding_box()\n        x = box[\'x\'] + box[\'width\'] / 2\n        y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n        page.mouse.move(x, y)\n        page.mouse.down()\n        page.mouse.move(x + 100, y, steps=10)\n        page.mouse.up()\n        page.wait_for_timeout(150)\n        after = read_widths()\n        print(json.dumps({\'before\': before, \'after\': after}))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_initial_column_widths(self, data):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'initial-column-widths.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => ({\n          taskNameW: getComputedStyle(document.documentElement).getPropertyValue(\'--task-name-w\'),\n          assigneeW: getComputedStyle(document.documentElement).getPropertyValue(\'--assignee-w\'),\n          commentW: getComputedStyle(document.documentElement).getPropertyValue(\'--comment-w\')\n        })""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def test_browser_applies_json_column_widths_on_initial_load(self):
        data = {'project': {'name': 'P', 'statusDate': '2026-06-18'}, 'display': {'standard': {'columns': {'width': {'name': 260, 'assignee': 70, 'comment': 200}}}}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        state = self.evaluate_initial_column_widths(data)
        assert state['taskNameW'].strip() == '260px'
        assert state['assigneeW'].strip() == '70px'
        assert state['commentW'].strip() == '200px'

    def test_browser_applies_default_column_widths_when_unspecified(self):
        data = {'project': {'name': 'P', 'statusDate': '2026-06-18'}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        state = self.evaluate_initial_column_widths(data)
        assert state['taskNameW'].strip() == '220px'
        assert state['assigneeW'].strip() == '56px'
        assert state['commentW'].strip() == '220px'

    def test_browser_narrow_headers_show_ellipsis_and_stay_centered(self):
        data = {'project': {'name': 'P', 'statusDate': '2026-06-18'}, 'display': {'standard': {'columns': {'width': {'name': 40, 'assignee': 40, 'comment': 40}}}}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        with tempfile.TemporaryDirectory() as tmp:
            browser_python = Path('.venv/bin/python')
            if not browser_python.is_file():
                pytest.skip('Playwright runtime is not available')
            if not Path('.cache/ms-playwright').exists():
                pytest.skip('Playwright browser cache is not available')
            html_path = Path(tmp) / 'narrow-headers.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        print(json.dumps(page.evaluate("""() => {\n          const assigneeHead = document.querySelector(\'.assignee-head\');\n          const assigneeRect = assigneeHead.getBoundingClientRect();\n          const assigneeLabelRect = assigneeHead.querySelector(\'.column-label\').getBoundingClientRect();\n          return {\n            assigneeHeadWidth: assigneeRect.width,\n            assigneeLabelWidth: assigneeLabelRect.width,\n            assigneeTextAlign: getComputedStyle(assigneeHead.querySelector(\'.column-label\')).textAlign,\n            commentTextAlign: getComputedStyle(document.querySelector(\'.comment-head .column-label\')).textAlign,\n          };\n        }""")))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            state = json.loads(proc.stdout)
        assert state['assigneeLabelWidth'] <= state['assigneeHeadWidth']
        assert state['assigneeTextAlign'] == 'center'
        assert state['commentTextAlign'] == 'left'

    def evaluate_task_name_resize_widths(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'task-name-resize-widths.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n\n        def read_widths():\n            return page.evaluate("""() => ({\n              taskNameW: getComputedStyle(document.documentElement).getPropertyValue(\'--task-name-w\'),\n              leftW: getComputedStyle(document.documentElement).getPropertyValue(\'--left-w\')\n            })""")\n\n        before = read_widths()\n        handle = page.locator(\'.task-name-resize-handle\')\n        box = handle.bounding_box()\n        x = box[\'x\'] + box[\'width\'] / 2\n        y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n        page.mouse.move(x, y)\n        page.mouse.down()\n        page.mouse.move(x + 60, y, steps=10)\n        page.mouse.up()\n        page.wait_for_timeout(150)\n        after = read_widths()\n        print(json.dumps({\'before\': before, \'after\': after}))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def evaluate_pane_resize_scroll_independence(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'pane-resize-scroll-independence.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nhtml_path = Path(sys.argv[1]).resolve()\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=[\'--disable-gpu\', \'--disable-dev-shm-usage\'])\n    page = browser.new_page(viewport={\'width\': 1360, \'height\': 900}, device_scale_factor=1)\n    try:\n        def drag_pane(dx):\n            handle = page.locator(\'.pane-resize-handle\')\n            box = handle.bounding_box()\n            x = box[\'x\'] + box[\'width\'] / 2\n            y = box[\'y\'] + min(box[\'height\'] / 2, 24)\n            page.mouse.move(x, y)\n            page.mouse.down()\n            page.mouse.move(x + dx, y, steps=10)\n            page.mouse.up()\n            page.wait_for_timeout(150)\n\n        def read_widths():\n            return page.evaluate("""() => ({\n              leftW: getComputedStyle(document.documentElement).getPropertyValue(\'--left-w\'),\n              commentW: getComputedStyle(document.documentElement).getPropertyValue(\'--comment-w\')\n            })""")\n\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        drag_pane(80)\n        without_scroll = read_widths()\n\n        page.goto(html_path.as_uri())\n        page.wait_for_timeout(250)\n        page.evaluate("""() => { document.querySelector(\'.workspace\').scrollLeft = 300; }""")\n        page.wait_for_timeout(150)\n        drag_pane(80)\n        with_scroll = read_widths()\n\n        print(json.dumps({\'withoutScroll\': without_scroll, \'withScroll\': with_scroll}))\n    finally:\n        browser.close()\n'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            return json.loads(proc.stdout)

    def test_render_html_embeds_display_settings_json(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*', '-comment']}}, 'layers': {'visible': ['*', '-tooltip']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        rendered = wbsgen.render_html(data, result)
        assert '<script type="application/json" id="wbsgen-display-settings">' in rendered
        assert '"standard": {' in rendered
        assert '"columns": {' in rendered
        assert '"visible": [' in rendered
        assert '"*"' in rendered
        assert '"-comment"' in rendered
        assert '"layers": {' in rendered
        assert '"-tooltip"' in rendered

    def test_browser_applies_display_defaults_to_dom_state(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*', '-comment']}}, 'layers': {'visible': ['*', '-tooltip']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'issue': 1}]}
        state = self.evaluate_display_state(data)
        assert state['commentHidden']
        assert not state['issueHidden']
        assert not state['actualLayerHidden']
        assert state['tooltipHidden']
        assert not state['commentToggleChecked']
        assert state['issueToggleChecked']
        assert state['actualToggleChecked']
        assert not state['tooltipToggleChecked']

    def test_browser_query_overrides_hide_additional_targets_and_ignore_legacy_flags(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*']}}, 'layers': {'visible': ['*']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'issue': 1}]}
        state = self.evaluate_display_state(data, query='?hideColumns=issue,unknown&hideLayers=actual,unknown&hideActual=1&hideCommentColumn=1')
        assert not state['commentHidden']
        assert state['issueHidden']
        assert state['actualLayerHidden']
        assert not state['tooltipHidden']
        assert state['commentToggleChecked']
        assert not state['issueToggleChecked']
        assert not state['actualToggleChecked']
        assert state['tooltipToggleChecked']

    def test_browser_query_hides_assignee_column(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*']}}, 'layers': {'visible': ['*']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'assignee': '担当者A'}]}
        state = self.evaluate_display_state(data, query='?hideColumns=assignee')
        assert state['assigneeHidden']
        assert not state['assigneeToggleChecked']

    def test_browser_shows_assignee_column_by_default(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*']}}, 'layers': {'visible': ['*']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'assignee': '担当者A'}]}
        state = self.evaluate_display_state(data)
        assert not state['assigneeHidden']
        assert state['assigneeToggleChecked']

    def test_browser_column_order_query_overrides_json_order_partially(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'order': ['issue', 'assignee', 'planned-period', 'actual-period', 'progress', 'expected-progress']}}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'issue': 1, 'assignee': '担当者A'}]}
        state = self.evaluate_column_layout_state(data, query='?standardOrder=progress,unknown-key')
        assert state['standardOrder'] == ['progress', 'issue', 'assignee', 'planned-period', 'actual-period', 'expected-progress']

    def test_browser_column_widths_query_overrides_initial_widths(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'assignee': '担当者A'}]}
        state = self.evaluate_column_layout_state(data, query='?columnWidths=name:300,comment:39,unknown:999')
        assert abs(state['taskNameWidth'] - 300) <= 1
        assert abs(state['commentWidth'] - 220) <= 1

    def test_browser_keeps_pane_resize_handle_and_wbs_header_sticky_when_scrolling(self):
        state = self.evaluate_sticky_resize_positions()
        assert state['after']['scrollLeft'] > 0
        assert state['after']['scrollTop'] > 0
        assert abs(state['before']['handleLeft'] - state['after']['handleLeft']) <= 1
        assert abs(state['before']['leftHeadTop'] - state['after']['leftHeadTop']) <= 1

    def test_browser_allows_pane_resize_left_after_task_name_column_expands(self):
        state = self.evaluate_pane_resize_after_task_name_expand(viewport_width=1360)
        assert state['afterPane']['leftWidth'] < state['afterTask']['leftWidth'] - 40, state

    def test_browser_keeps_pane_resize_handle_reachable_after_task_name_column_expands(self):
        state = self.evaluate_pane_resize_after_task_name_expand(viewport_width=1000)
        assert state['afterTask']['handleRight'] <= state['afterTask']['viewportWidth'], state

    def test_browser_left_pane_content_is_clipped_and_does_not_overlay_gantt_when_pane_shrinks_below_content(self):
        state = self.evaluate_pane_resize_overlap_stacking()
        assert state['hitInOverlapIsInRightPane']
        assert state['handleStillHittable']

    def test_browser_left_pane_stays_above_gantt_content_during_horizontal_scroll(self):
        state = self.evaluate_left_pane_stacking_during_horizontal_scroll()
        assert state['hitIsInLeftPane']

    def test_browser_stacking_invariants_hold_when_scroll_and_pane_resize_combine(self):
        state = self.evaluate_stacking_invariants_after_combined_scroll_and_resize()
        assert state['scrollOverlapExists']
        assert state['frozenColumnIsInLeftPane']
        assert state['shrinkOverlapIsInRightPane']
        assert state['handleStillHittable']

    def test_browser_pane_resize_grows_comment_column_and_left_width(self):
        state = self.evaluate_pane_resize_comment_follow()
        before_left = float(state['before']['leftW'].strip().rstrip('px'))
        after_left = float(state['after']['leftW'].strip().rstrip('px'))
        before_comment = float(state['before']['commentW'].strip().rstrip('px'))
        after_comment = float(state['after']['commentW'].strip().rstrip('px'))
        assert after_left > before_left
        assert after_comment > before_comment
        assert abs(after_left - before_left - 100) <= 1

    def test_browser_task_name_resize_grows_task_name_and_left_width(self):
        state = self.evaluate_task_name_resize_widths()
        before_task = float(state['before']['taskNameW'].strip().rstrip('px'))
        after_task = float(state['after']['taskNameW'].strip().rstrip('px'))
        before_left = float(state['before']['leftW'].strip().rstrip('px'))
        after_left = float(state['after']['leftW'].strip().rstrip('px'))
        assert abs(after_task - before_task - 60) <= 1
        assert abs(after_left - before_left - 60) <= 1

    def test_browser_pane_resize_result_is_independent_of_horizontal_scroll(self):
        state = self.evaluate_pane_resize_scroll_independence()
        without_left = float(state['withoutScroll']['leftW'].strip().rstrip('px'))
        with_left = float(state['withScroll']['leftW'].strip().rstrip('px'))
        without_comment = float(state['withoutScroll']['commentW'].strip().rstrip('px'))
        with_comment = float(state['withScroll']['commentW'].strip().rstrip('px'))
        assert abs(without_left - with_left) <= 1
        assert abs(without_comment - with_comment) <= 1

    def test_browser_wbs_view_tab_switch_toggles_columns_and_menu_state(self):
        state = self.evaluate_wbs_view_tab_switch()
        assert state['a'] == {'view': 'standard', 'planned': 'flex', 'delta': 'none', 'disabled': False}
        assert state['b'] == {'view': 'analysis', 'planned': 'none', 'delta': 'flex', 'disabled': False}
        assert state['c'] == {'view': 'standard', 'planned': 'flex', 'delta': 'none', 'disabled': False}

    def test_browser_keeps_pane_boundary_contiguous_through_tab_resize_transitions(self, tmp_path):
        from tools.workflow_verification import (
            assert_pane_boundary_states,
            capture_pane_boundary_states,
        )

        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        html_path = tmp_path / 'pane-boundary.html'
        html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')

        states = capture_pane_boundary_states(html_path)

        assert_pane_boundary_states(states)
        assert states['analysis-after-standard-resize']['activeView'] == 'analysis'
        assert states['standard-after-analysis-resize']['activeView'] == 'standard'

    def test_browser_applies_and_updates_column_order_in_menu_and_wbs(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = {'project': {'name': '列順', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'order': ['progress']}}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'column-order.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = 'import json,sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n b=p.chromium.launch(headless=True,args=[\'--disable-gpu\',\'--disable-dev-shm-usage\']); q=b.new_page()\n q.goto(Path(sys.argv[1]).resolve().as_uri()); q.wait_for_timeout(100)\n def s(): return q.evaluate("""() => ({headers:Array.from(document.querySelectorAll(\'.left-head > [data-column]\')).filter((cell) => getComputedStyle(cell).display !== \'none\').map((cell) => cell.dataset.column),menu:Array.from(document.querySelectorAll(\'[data-column-settings=\\"standard\\"] .column-settings-row\')).map((row) => row.firstElementChild.textContent),commentOrder:document.querySelector(\'[data-column-order=\\"comment\\"]\') !== null})""")\n a=s(); q.click(\'.view-menu summary\'); q.click(\'[data-column-order=\\"assignee\\"][data-direction=\\"up\\"]\'); q.wait_for_timeout(50); b1=s(); print(json.dumps({\'a\':a,\'b\':b1})); b.close()'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
        state = json.loads(proc.stdout)
        assert state['a']['headers'][:3] == ['progress', 'assignee', 'planned-period']
        assert state['a']['menu'][:3] == ['進捗', '担当者', '計画']
        assert not state['a']['commentOrder']
        assert state['b']['headers'][:3] == ['assignee', 'progress', 'planned-period']
        assert state['b']['menu'][:3] == ['担当者', '進捗', '計画']

    def test_browser_analysis_pane_resize_caps_at_natural_width(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'analysis-cap.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = 'import json,sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n b=p.chromium.launch(headless=True,args=[\'--disable-gpu\',\'--disable-dev-shm-usage\']);q=b.new_page(viewport={\'width\':1360,\'height\':900});q.goto(Path(sys.argv[1]).resolve().as_uri());q.click(\'[data-wbs-view-target="analysis"]\');q.wait_for_timeout(100);n=q.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue(\'--left-w\')");h=q.locator(\'.pane-resize-handle\').bounding_box();x=h[\'x\']+h[\'width\']/2;y=h[\'y\']+24;q.mouse.move(x,y);q.mouse.down();q.mouse.move(x+300,y,steps=8);q.mouse.up();q.wait_for_timeout(100);o=q.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue(\'--left-w\')");print(json.dumps([n,o]));b.close()'
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                pytest.fail(proc.stderr)
            natural, over = (float(value.rstrip('px')) for value in json.loads(proc.stdout))
            assert abs(natural - over) <= 1

    def test_flatten_computed_tasks_preserves_tree_order_and_depth(self):
        child = wbsgen.ComputedTask(id='1.1', name='子', source_task=wbsgen.Task(id='1.1', name='子'))
        root = wbsgen.ComputedTask(id='1', name='親', source_task=wbsgen.Task(id='1', name='親'), children=[child])
        rows = wbsgen.flatten_computed_tasks([root])
        assert [(row.task.id, row.depth) for row in rows] == [('1', 0), ('1.1', 1)]

    def test_render_html_outputs_tooltip_metadata_for_cells_and_plan_bars(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-16', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '長い&"<タスク>\n名の確認用タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-02', 'progress': 40, 'comment': '<a&"b>\n2行目'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'class="task-label" data-tooltip-role="task-name"' in html
        assert '長い&amp;&quot;&lt;タスク&gt;' in html
        assert '名の確認用タスク</span>' in html
        assert 'data-tooltip-text="長い&amp;&quot;&lt;タスク&gt;&#10;名の確認用タスク"' in html
        assert 'class="wbs-cell note" data-column="comment"' in html
        assert '&lt;a&amp;&quot;b&gt;\n2行目</span></div>' in html
        assert 'data-tooltip-role="comment"' in html
        assert 'data-tooltip-text="&lt;a&amp;&quot;b&gt;&#10;2行目"' in html
        assert 'class="bar plan task-bar"' in html
        assert 'data-tooltip-role="plan-bar"' in html
        assert 'data-task-name="長い&amp;&quot;&lt;タスク&gt;&#10;名の確認用タスク"' in html
        assert 'data-planned-end="2026-06-05"' in html
        assert 'data-progress-label="40%"' in html
        assert 'data-actual-start="2026-06-02"' in html
        assert 'data-actual-end=""' in html
        assert 'data-delay-state="delayed"' not in html
        assert 'data-expected-progress-label=' not in html
        assert 'title="長い&"<タスク>\n名の確認用タスク"' not in html
        assert 'data-tooltip-text="&amp;lt;a&amp;amp;&quot;b&amp;gt;&#10;2行目"' not in html

    def test_render_html_outputs_delay_metadata_for_delayed_plan_bars(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-01', 'endDate': '2026-06-16', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '遅延タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 10, 'progress': 40}, {'id': '2', 'name': '順調タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 10, 'progress': 80}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        delayed_plan_bar = re.search('<div class="(?P<class_name>[^"]*)"[^>]*data-kind="planned"[^>]*data-task-id="1"(?P<attrs>[^>]*)></div>', html)
        non_delayed_plan_bar = re.search('<div class="(?P<class_name>[^"]*)"[^>]*data-kind="planned"[^>]*data-task-id="2"(?P<attrs>[^>]*)></div>', html)
        assert delayed_plan_bar is not None
        assert 'delayed' in delayed_plan_bar.group('class_name')
        assert 'data-delay-state="delayed"' in delayed_plan_bar.group('attrs')
        assert 'data-expected-progress-label="70%"' in delayed_plan_bar.group('attrs')
        assert 'data-tooltip-role="plan-bar"' in delayed_plan_bar.group('attrs')
        assert 'data-task-name="遅延タスク"' in delayed_plan_bar.group('attrs')
        assert non_delayed_plan_bar is not None
        assert 'delayed' not in non_delayed_plan_bar.group('class_name')
        assert 'data-tooltip-role="plan-bar"' in non_delayed_plan_bar.group('attrs')
        assert 'data-task-name="順調タスク"' in non_delayed_plan_bar.group('attrs')
        assert 'data-delay-state="delayed"' not in non_delayed_plan_bar.group('attrs')
        assert 'data-expected-progress-label="70%"' not in non_delayed_plan_bar.group('attrs')

    def test_render_html_outputs_project_header_wbs_table_warnings_and_source_json(self):
        data = {'project': {'name': '<個人開発>', 'statusDate': '2026-06-17', 'issueBaseUrl': 'https://github.com/your_account/your_repo/issues/'}, 'tasks': [{'id': '1', 'name': '親<script>', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'comment': '親コメント'}, {'id': '1.1', 'name': '子A', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-01', 'actualEnd': '2026-06-05', 'progress': 100, 'issue': 123, 'comment': '完了'}, {'id': '1.2', 'name': '子B', 'plannedStart': '2026-06-08', 'plannedDuration': 5, 'actualStart': '2026-06-09', 'actualEnd': None, 'progress': 50, 'issue': 124, 'comment': '</script>を含む'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '&lt;個人開発&gt;' in html
        assert '基準日' in html
        assert 'Status Date' not in html
        assert '2026-06-17' in html
        assert '表示範囲' in html
        assert '2026-06-01 - 2026-06-17' in html
        assert 'class="legend-group"' in html
        assert 'class="legend-label">子</span>' in html
        assert 'class="swatch parent-progress"' in html
        assert 'class="left-head"' in html
        assert 'class="right-pane"' in html
        assert html.index('class="left-pane"') < html.index('class="right-pane"')
        assert html.index('>1</div>') < html.index('>1.1</div>')
        assert '親&lt;script&gt;' in html
        assert 'padding-left: 24px;' in html
        assert '6/1 - 6/5' in html
        assert '6/9 -' in html
        assert '50%' in html
        assert '<a href="https://github.com/your_account/your_repo/issues/123">#123</a>' in html
        assert 'PARENT_FIELD_IGNORED' in html
        assert 'type="application/json" id="wbsgen-source"' in html
        assert '\\u003c/script\\u003eを含む' in html
        assert '</script>を含む' not in html
        assert '参照JSON' not in html
        assert 'input.json' not in html
        assert 'data-source-download' in html

    def test_render_html_outputs_row_collapse_menu_and_row_metadata(self):
        data = {'project': {'name': '折りたたみ', 'statusDate': '2026-06-17'}, 'tasks': [{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '子', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 50}, {'id': '1.1.1', 'name': '孫', 'plannedStart': '2026-06-03', 'plannedDuration': 3, 'progress': 30}, {'id': '2', 'name': '単独', 'plannedStart': '2026-06-08', 'plannedDuration': 3, 'progress': 0}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'class="view-menu"' in html
        assert '<details class="view-menu">' in html
        assert '<details class="view-menu" open>' not in html
        assert 'data-action="collapse-all"' in html
        assert 'data-action="expand-all"' in html
        assert '>▸ 折りたたむ</button>' in html
        assert '>▾ 展開</button>' in html
        assert '<div class="view-menu-title">表示</div>' in html
        assert '>表示操作<' not in html
        assert '<div class="view-menu-data">' in html
        assert '<div class="view-menu-title">データ</div>' in html
        assert '<span class="control-label">JSON</span>' in html
        assert 'data-source-download>エクスポート</button>' in html
        assert 'class="control-label">列</span>' in html
        assert 'data-column-visibility-action="show-all"' in html
        assert 'data-column-visibility-action="hide-all"' in html
        assert 'class="column-settings column-settings-standard" data-column-settings="standard"' in html
        assert 'class="column-settings column-settings-analysis" data-column-settings="analysis"' in html
        assert 'data-column-order="${column}"' in html
        assert 'data-column-visibility-toggle="${column}"' in html
        assert 'data-column-visibility-toggle="comment"' in html
        assert 'data-column-action' not in html
        assert 'class="column-toggle"' not in html
        assert 'class="tree-toggle"' in html
        assert 'class="tree-toggle-spacer"' in html
        assert 'data-depth="0"' in html
        assert 'data-depth="1"' in html
        assert 'data-depth="2"' in html
        assert 'data-parent-id="1"' in html
        assert 'data-parent-id="1.1"' in html
        assert 'data-has-children="true"' in html
        assert 'function updateRowVisibility()' in html
        assert 'function updateInazuma()' in html
        assert 'function setCollapsed(taskId, collapsed)' in html
        assert "const viewMenu = document.querySelector('.view-menu');" in html
        assert 'if (viewMenu && viewMenu.open && !viewMenu.contains(event.target))' in html
        assert 'viewMenu.open = false;' in html
        assert 'data-status-x="' in html
        assert 'data-row-height="32"' in html
        assert 'data-progress-x="' in html
        assert 'data-progress-y="' in html

    def test_render_html_outputs_search_controls_and_shared_row_search_data(self):
        data = {'project': {'name': '検索', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '親', 'assignee': '担当者A'}, {'id': '1.1', 'name': '子', 'comment': '確認対象', 'issue': 138, 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        rendered = wbsgen.render_html(data, result)
        css = __import__('wbsgen.render.html', fromlist=['read_text_asset']).read_text_asset('style.css')
        for token in ('data-search-summary', 'data-search-drawer', 'data-search-keyword', 'placeholder="空白でAND、-で除外"', 'data-search-field="all"', 'data-search-field="name"', 'data-search-field="comment"', 'data-search-field="assignee"', 'data-search-field="issue"', 'data-search-mode="filter"', 'data-search-mode="highlight"', 'data-search-name="子"', 'data-search-comment="確認対象"', 'data-search-assignee="担当者A"', 'data-search-issue="138"'):
            with nullcontext():
                assert token in rendered
        assert '.search-summary' in css
        assert '.search-drawer' in css
        assert '.wbs-row.is-search-match' in css
        assert '.gantt-row.is-search-match' in css
        assert '.wbs-row.is-search-match.is-pinned-task' in css
        assert '.gantt-row.is-search-match.is-pinned-task' in css
        assert '.search-close:hover' in css
        assert 'linear-gradient(var(--hover-row), var(--hover-row))' in css

    def test_browser_copies_current_shareable_display_state_without_changing_page_url(self):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file() or not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright runtime is not available')
        data = {'project': {'name': '共有', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '確認対象', 'assignee': '担当者A', 'issue': 164, 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / 'share-link.html'
            html_path.write_text(wbsgen.render_html(data, result), encoding='utf-8')
            runner = '''import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

html_path = Path(sys.argv[1]).resolve()
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=['--disable-gpu', '--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width': 1360, 'height': 900})
    try:
        page.goto(html_path.as_uri() + '?ignored=1#shared')
        page.wait_for_timeout(100)
        page.evaluate("""() => {
          Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
            writeText: async (text) => { window.__copiedShareLink = text; }
          }});
        }""")
        page.evaluate("""() => {
          const input = document.querySelector('[data-search-keyword]');
          input.value = '確認 担当者A -完了'; input.dispatchEvent(new Event('input', {bubbles: true}));
          ['comment', 'assignee'].forEach((field) => {
            const control = document.querySelector(`[data-search-field="${field}"]`);
            control.checked = false; control.dispatchEvent(new Event('change', {bubbles: true}));
          });
          const mode = document.querySelector('[data-search-mode="highlight"]');
          mode.checked = true; mode.dispatchEvent(new Event('change', {bubbles: true}));
          ['comment'].forEach((column) => document.querySelector(`[data-column-visibility-toggle="${column}"]`).click());
          document.querySelector('[data-layer-target="actual"]').click();
          document.querySelector('[data-tooltip-toggle]').click();
          document.querySelector('[data-column-order="progress"][data-direction="up"]').click();
          document.querySelector('[data-wbs-view-target="analysis"]').click();
          document.querySelector('[data-column-order="pace"][data-direction="up"]').click();
          document.querySelector('[data-wbs-view-target="standard"]').click();
        }""")
        before = page.url
        page.evaluate("document.querySelector('[data-share-link-copy]').click()")
        page.wait_for_timeout(20)
        success_label = page.locator('[data-share-link-copy]').text_content()
        page.evaluate("""() => {
          Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
            writeText: async () => { throw new Error('denied'); }
          }});
          document.querySelector('[data-share-link-copy]').click();
        }""")
        page.wait_for_timeout(20)
        print(json.dumps({
          'before': before,
          'after': page.url,
          'copied': page.evaluate('window.__copiedShareLink'),
          'label': success_label,
          'failureLabel': page.locator('[data-share-link-copy]').text_content(),
        }))
    finally:
        browser.close()
'''
            proc = subprocess.run([str(browser_python), '-c', runner, str(html_path)], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
            if proc.returncode != 0:
                if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                    pytest.skip('Browser launch is not permitted in this environment')
                pytest.fail(proc.stderr)
            state = json.loads(proc.stdout)
        assert state['after'] == state['before']
        assert state['label'] == 'コピーしました'
        assert state['failureLabel'] == 'コピーできませんでした'
        assert state['copied'].endswith('#shared')
        assert 'ignored=1' not in state['copied']
        assert 'keyword=%E7%A2%BA%E8%AA%8D+%E6%8B%85%E5%BD%93%E8%80%85A+-%E5%AE%8C%E4%BA%86' in state['copied']
        assert 'fields=name%2Cissue' in state['copied']
        assert 'mode=highlight' in state['copied']
        assert 'hideColumns=comment' in state['copied']
        assert 'hideLayers=actual%2Ctooltip' in state['copied']
        assert 'standardOrder=assignee%2Cplanned-period%2Cprogress%2Cactual-period%2Cexpected-progress%2Cissue' in state['copied']
        assert 'analysisOrder=assignee%2Cprogress%2Cexpected-progress%2Cdelta%2Cpace%2Cdelay' in state['copied']
        assert 'columnWidths=name%3A220%2Cassignee%3A56%2Ccomment%3A220' in state['copied']

    def test_render_html_includes_assignee_column_head_and_resize_handle(self):
        data = {'project': {'name': '担当者確認', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1, 'assignee': '担当者A'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        html = wbsgen.render_html(data, result)
        assert '<div class="head-cell column-head assignee-head" data-column="assignee">' in html
        assert '担当者' in html
        assert 'class="resize-handle assignee-resize-handle"' in html
        assert '<div class="wbs-cell assignee" data-column="assignee" style="width: 56px;">' in html
        assert 'data-tooltip-role="assignee"' in html
        assert '>担当者A<' in html

    def test_render_html_shows_placeholder_when_assignee_is_missing(self):
        data = {'project': {'name': '担当者未指定', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        html = wbsgen.render_html(data, result)
        assert '<div class="wbs-cell assignee" data-column="assignee" style="width: 56px;">' in html
        assert '<span class="assignee-label" data-tooltip-text="-" data-tooltip-role="assignee">-</span>' in html

    def test_render_html_outputs_expected_progress_column_values(self):
        data = {'project': {'name': '期待進捗', 'statusDate': '2026-06-03'}, 'tasks': [{'id': '1', 'name': '計画あり', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 20}, {'id': '2', 'name': '未計画', 'progress': 40}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 3))
        html = wbsgen.render_html(data, result)
        assert '<span class="column-label">期待</span>' in html
        assert re.search(re.compile('<div class="wbs-row[^"]*" data-task-id="1"[^>]*>.*?data-column="expected-progress" style="width: 52px;"><span class="progress-pill">40%</span></div>.*?(?=\\n\\s*<div class="wbs-row|\\n\\s*</div>\\n\\s*</section>)', re.S), html)
        assert re.search(re.compile('<div class="wbs-row[^"]*" data-task-id="2"[^>]*>.*?data-column="expected-progress" style="width: 52px;"><span class="progress-pill">-</span></div>.*?(?=\\n\\s*<div class="wbs-row|\\n\\s*</div>\\n\\s*</section>)', re.S), html)
        assert 'data-column="expected-progress" style="width: 52px;"><span class="progress-pill delayed"' not in html
        assert 'data-column="expected-progress" style="width: 52px;"><span class="progress-pill done"' not in html

    def test_render_html_outputs_layer_toggle_controls_and_legend_labels(self):
        data = {'project': {'name': 'レイヤー切替', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': '実績あり', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-02', 'actualEnd': None, 'progress': 40}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        html = wbsgen.render_html(data, result)
        assert 'data-layer-target="inazuma"' in html
        assert 'data-layer-target="actual"' in html
        assert 'data-layer-query="hideInazuma"' not in html
        assert 'data-layer-query="hideActual"' not in html
        assert '>イナズマ線</label>' in html
        assert '>実績線</label>' in html
        assert 'class="legend-item layer-legend" data-layer="inazuma"' in html
        assert 'class="legend-item layer-legend" data-layer="actual"' in html
        assert 'イナズマ線</span>' in html
        assert '進捗基準線</span>' not in html
        assert '.app.is-layer-actual-hidden .bar.actual' in html
        assert '.app.is-layer-inazuma-hidden .gantt-inazuma' in html
        assert "const layerTargets = ['inazuma', 'actual', 'milestone'];" in html
        assert 'const layerQueries' not in html
        assert "params.get('hideInazuma')" not in html
        assert "params.get('hideActual')" not in html
        assert "queryList(params, 'hideLayers')" in html
        assert 'function updateLayerVisibility()' in html
        assert 'function setLayerVisible(layer, visible)' in html
        assert 'app.classList.toggle(`is-layer-${layer}-hidden`, !visible);' in html
        assert 'checkbox.checked = !hiddenLayers.has(layer);' in html

    def test_visual_test_json_supports_sticky_scroll_reference_cases(self):
        visual_json = Path('examples/visual-test.json')
        data = json.loads(visual_json.read_text(encoding='utf-8'))
        tasks = data['tasks']
        assert data['display'] == {'standard': {'columns': {'visible': ['*'], 'width': {'name': 220, 'assignee': 56, 'comment': 220}}}, 'layers': {'visible': ['*']}}
        assert data['project']['startDate'] == '2026-05-31'
        assert data['project']['endDate'] == '2026-08-03'
        assert any((task['id'] == '4' for task in tasks))
        scroll_tasks = [task for task in tasks if task['id'].startswith('4.')]
        assert len(scroll_tasks) >= 18
        result = wbsgen.build_project_model(data, today=date(2026, 6, 29))
        rows = wbsgen.flatten_computed_tasks(result.computed_roots)
        tasks_by_id = {row.task.id: row.task for row in rows}
        july_20 = date(2026, 7, 20)
        spans_july_20 = [task_id for task_id in ('4.3', '4.4', '4.5') if tasks_by_id[task_id].planned_start <= july_20 <= tasks_by_id[task_id].planned_end]
        assert spans_july_20 == ['4.3', '4.4', '4.5']
        clip_tasks = {task['id']: task for task in tasks if task['id'].startswith('5')}
        assert set(clip_tasks) == {'5', '5.1', '5.2', '5.3', '5.4', '5.5'}
        out_of_range_warnings = [warning for warning in result.validation.warnings if warning.code == wbsgen.CODE_TASK_DATE_OUT_OF_RANGE]
        assert len(out_of_range_warnings) == 8

    def test_visual_reference_inazuma_reaches_gantt_bottom(self):
        assert Path('mockups/visual-reference.html').is_file()
        mockup = Path('mockups/visual-reference.html').read_text(encoding='utf-8')
        assert '352,1248' in mockup
        assert '352,1056"></polyline>' not in mockup

    def test_visual_test_html_outputs_issue_55_inazuma_points(self):
        data = json.loads(Path('examples/visual-test.json').read_text(encoding='utf-8'))
        result = wbsgen.build_project_model(data)
        html = wbsgen.render_html(data, result)
        expected_points = {'4.4': (352, 592), '4.12': (352, 848), '5': (768, 1072), '5.1': (90, 1104), '5.2': (1952, 1136), '5.3': (971, 1168), '5.4': (0, 1200), '5.5': (352, 1232)}
        for task_id, (x, y) in expected_points.items():
            assert f'<circle class="gantt-progress-point" cx="{x}" cy="{y}" r="3" data-task-id="{task_id}" />' in html
        assert '352,1248' in html

    def test_render_html_uses_source_actual_end_for_wbs_actual_end_column(self):
        data = {'project': {'name': '個人開発', 'statusDate': '2026-06-17'}, 'tasks': [{'id': '1', 'name': '進行中', 'plannedStart': '2026-06-01', 'plannedDuration': 10, 'actualStart': '2026-06-07', 'actualEnd': None, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert result.computed_roots[0].actual_end is None
        html = wbsgen.render_html(data, result)
        assert '6/7 -' in html

    def test_render_html_outputs_generated_parent_comment(self):
        data = {'project': {'name': '個人開発', 'statusDate': '2026-06-17', 'displayStart': '2026-06-01', 'displayEnd': '2026-06-17'}, 'tasks': [{'id': '3.1', 'name': '子タスク', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'actualStart': '2026-06-01', 'actualEnd': None, 'progress': 50}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert '自動補完された親タスクです' in html

    def test_render_issue_without_base_url_outputs_plain_text(self):
        assert wbsgen.render_issue(123, None) == '#123'

    def test_render_issue_uses_plain_text_for_unsafe_base_url_scheme(self):
        cases = ['javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', 'ftp://example.com/issues', 'github.com/user/repo/issues']
        for issue_base_url in cases:
            with nullcontext():
                assert wbsgen.render_issue(123, issue_base_url) == '#123'

    def build_result_for_gantt(self):
        data = {'project': {'name': '個人開発', 'startDate': '2026-06-05', 'endDate': '2026-06-09', 'statusDate': '2026-06-08'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        return (data, wbsgen.build_project_model(data, today=date(2026, 6, 18)))

    def test_render_html_outputs_resizable_pane_and_column_handles(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'class="head-cell task-name-head"' in html
        assert 'class="head-cell column-head comment-head"' in html
        assert 'class="resize-handle task-name-resize-handle"' in html
        assert 'aria-label="タスク名列幅を変更する"' in html
        assert 'class="resize-handle pane-resize-handle"' in html
        assert 'aria-label="左右ペイン幅を変更する"' in html
        assert html.index('class="resize-handle pane-resize-handle"') < html.index('class="left-head"')
        assert html.index('class="resize-handle pane-resize-handle"') < html.index('class="right-pane"')
        assert 'class="comment-label"' in html
        assert 'style="width: 220px;">タスク名</div>' not in html
        assert 'data-tooltip-role="comment" data-tooltip-text="' not in html

    def test_render_html_left_head_exposes_column_width_data_attributes(self):
        data, result = self.build_result_for_gantt()
        html = wbsgen.render_html(data, result)
        assert 'class="left-head" data-task-name-width="220" data-assignee-width="56" data-comment-width="220"' in html
        assert '<div class="head-cell task-name-head"><span class="column-label">タスク名</span>' in html

    def test_render_html_left_head_reflects_json_column_widths(self):
        data = {'project': {'name': 'P', 'statusDate': '2026-06-18'}, 'display': {'standard': {'columns': {'width': {'name': 260, 'assignee': 70, 'comment': 200}}}}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'class="left-head" data-task-name-width="260" data-assignee-width="70" data-comment-width="200"' in html

    def test_render_html_left_head_falls_back_when_column_widths_partial(self):
        data = {'project': {'name': 'P', 'statusDate': '2026-06-18'}, 'display': {'standard': {'columns': {'width': {'assignee': 70}}}}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-05', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        html = wbsgen.render_html(data, result)
        assert 'class="left-head" data-task-name-width="220" data-assignee-width="70" data-comment-width="220"' in html

    def test_render_html_css_defines_resizable_pane_and_column_widths(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '--task-name-w: 220px;' in css
        assert '--comment-w: 220px;' in css
        assert '.task-name-head {' in css
        assert 'width: var(--task-name-w) !important;' in css
        assert '.comment-head {' in css
        assert 'width: var(--comment-w) !important;' in css
        assert '.wbs-row > .wbs-cell:nth-child(2)' in css
        assert '.wbs-cell.note {' in css
        assert 'width: var(--comment-w) !important;' in css
        assert '.resize-handle {' in css
        assert '.pane-resize-handle {' in css
        pane_handle_rule = re.search('\\.pane-resize-handle \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert pane_handle_rule is not None
        assert 'right: -6px;' in pane_handle_rule.group('body')
        assert 'left: -5px;' not in pane_handle_rule.group('body')
        left_pane_rule = re.search('\\.left-pane \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert left_pane_rule is not None
        assert 'min-width: 0;' in left_pane_rule.group('body')
        assert 'overflow: visible;' in left_pane_rule.group('body')
        assert 'overflow: hidden;' not in left_pane_rule.group('body')
        assert '.task-name-resize-handle,' in css
        assert '.assignee-resize-handle {' in css
        assert 'body.is-resizing' in css
        assert 'scrollbar-gutter: stable;' in css
        assert 'scrollbar-gutter: stable both-edges;' not in css

    def test_render_html_css_defines_column_settings(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '.column-settings {' in css
        assert '.column-order-button' in css
        assert 'grid-template-columns: var(--column-label-w, 68px) 40px max-content;' in css
        assert 'gap: 8px;' in css
        assert '.column-settings-analysis .column-settings-header' in css
        assert '.column-settings-analysis .column-settings-row > :nth-child(2)' in css
        assert '.layer-settings-grid' in css
        assert 'grid-template-columns: repeat(3, 1fr);' in css
        assert '.is-hidden-column {' in css
        assert 'display: none !important;' in css

    def test_render_html_css_matches_approved_search_and_menu_design(self):
        from wbsgen.render import html

        css = html.read_text_asset('style.css')

        def rule(selector):
            match = re.search(rf'{re.escape(selector)} \{{(?P<body>.*?)\n    \}}', css, re.DOTALL)
            assert match is not None
            return match.group('body')

        assert 'font-size: 11px;' in rule('.search-options label,\n    .search-mode label')
        assert 'font-weight: 400;' in rule('.search-options label,\n    .search-mode label')
        assert 'min-height: 20px;' in rule('.search-summary')
        assert 'padding: 0 6px;' in rule('.warning-toggle')
        assert 'padding: 0 6px;' in rule('.holiday-toggle')
        assert 'border-bottom: 1px solid var(--border);' in rule('.column-settings-header')
        assert 'padding-bottom: 3px;' in rule('.column-settings-header')
        assert 'color: var(--muted);' in rule('.view-menu-section-title')
        assert 'margin-top: 4px;' in rule('.view-menu-section-title')
        assert 'font-size: 11px;' in rule('.layer-settings-grid .layer-toggle')
        assert 'white-space: nowrap;' in rule('.layer-settings-grid .layer-toggle')

    def test_render_html_js_sizes_column_setting_labels_from_the_longest_item(self):
        from wbsgen.render import html
        javascript = html.read_text_asset('app.js')
        assert 'function updateColumnSettingsLabelWidths()' in javascript
        assert 'context.measureText' in javascript
        assert "settings.style.setProperty('--column-label-w'" in javascript
        assert '    updateColumnSettingsLabelWidths();\n  }\n\n  function updateColumnSettingsLabelWidths()' in javascript

    def test_render_html_css_defines_assignee_column_width_and_resize_handle(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        assert '--assignee-w: 56px;' in css
        assert '.assignee-head {' in css
        assert 'width: var(--assignee-w) !important;' in css
        assert '.wbs-row > .wbs-cell[data-column="assignee"] {' in css
        assert '.wbs-cell.assignee {' in css
        assert '.assignee-label' in css
        assert '.assignee-resize-handle' in css

    def test_render_html_css_head_cell_supports_narrow_widths(self):
        from wbsgen.render import html
        css = html.read_text_asset('style.css')
        head_cell_rule = re.search('\\.head-cell \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert head_cell_rule is not None
        assert 'min-width: 0;' in head_cell_rule.group('body')
        column_label_column_head_rule = re.search('\\.head-cell\\.column-head \\.column-label \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert column_label_column_head_rule is not None
        assert 'min-width: 0;' in column_label_column_head_rule.group('body')
        assert 'text-align: center;' in column_label_column_head_rule.group('body')
        assert 'width: 100%;' in column_label_column_head_rule.group('body')
        comment_head_label_rule = re.search('\\.comment-head \\.column-label \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert comment_head_label_rule is not None
        assert 'text-align: left;' in comment_head_label_rule.group('body')
        task_name_head_label_rule = re.search('\\.task-name-head \\.column-label \\{(?P<body>.*?)\\n    \\}', css, re.DOTALL)
        assert task_name_head_label_rule is not None
        assert 'min-width: 0;' in task_name_head_label_rule.group('body')

class TestMilestoneRenderTests:

    def base_data(self, milestones=None):
        data = {'project': {'name': 'P', 'startDate': '2026-05-31', 'endDate': '2026-08-03', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 0}]}
        if milestones is not None:
            data['milestones'] = milestones
        return data

    def render(self, milestones=None):
        data = self.base_data(milestones)
        result = wbsgen.build_project_model(data)
        return wbsgen.render_html(data, result)

    def test_render_html_outputs_milestone_band_marker_pill_and_line(self):
        html = self.render([{'date': '2026-06-12', 'name': '要件確定'}])
        assert '<div class="milestone-band"' in html
        assert 'class="milestone-marker"' in html
        assert 'style="left:416px;top:6px;"' in html
        assert '>要件確定</div>' in html
        assert '<line class="milestone-line" x1="416" y1="0" x2="416"' in html
        assert '<div class="milestone-cell">マイルストーン</div>' in html
        assert 'style="--milestone-band-total:26px;"' in html
        assert 'data-layer-target="milestone"' in html

    def test_render_html_outputs_two_tier_band_for_crowded_milestones(self):
        html = self.render([{'date': '2026-06-24', 'name': '設計凍結'}, {'date': '2026-06-26', 'name': '中間レビュー'}])
        assert 'style="--milestone-band-total:50px;"' in html
        assert 'style="left:809px;top:4px;"' in html
        assert 'style="left:873px;top:28px;"' in html

    def test_render_html_without_milestones_has_no_band(self):
        html = self.render()
        assert 'class="milestone-band"' not in html
        assert 'class="milestone-cell"' not in html
        assert not re.search('<line class="milestone-line" x1="\\d', html)
        assert '--milestone-band-total:' not in html
        assert 'data-milestone-band-total' not in html
        assert 'data-layer-target="milestone"' in html

    def test_render_html_excludes_out_of_range_milestone_from_band(self):
        html = self.render([{'date': '2026-06-12', 'name': '範囲内'}, {'date': '2026-08-04', 'name': '範囲外'}])
        assert '>範囲内</div>' in html
        assert '>範囲外</div>' not in html

    def test_app_js_wires_milestone_layer(self):
        html = self.render([{'date': '2026-06-12', 'name': '要件確定'}])
        assert "['inazuma', 'actual', 'milestone']" in html
        assert "['inazuma', 'actual', 'highlight', 'tooltip', 'delayHighlight', 'milestone']" in html
        assert '.app.is-layer-milestone-hidden' in html
        assert 'app.dataset.milestoneBandTotal' in html
        assert 'line.milestone-line' in html
        assert 'data-milestone-band-total="26px"' in html
