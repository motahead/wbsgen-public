from contextlib import nullcontext
import pytest
import io
import importlib.util
import json
import tempfile
import zipfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import wbsgen

class TestParserModuleTests:

    def test_parser_exports_existing_parse_functions(self):
        from wbsgen import parser
        assert parser.parse_project is wbsgen.parse_project
        assert parser.parse_tasks is wbsgen.parse_tasks
        assert parser.parse_display is wbsgen.parse_display
        assert parser.parse_holidays is wbsgen.parse_holidays
        assert parser.load_json is wbsgen.load_json

    def test_parse_project_survives_an_unrelated_existing_validation_error(self):
        validation = wbsgen.ValidationResult()
        validation.error('OTHER', 'tasks[0]', 'unrelated')
        project = wbsgen.parse_project({'name': 'P'}, validation, date(2026, 6, 1))
        assert project.name == 'P'

    def test_parse_tasks_rejects_non_list_input(self):
        validation = wbsgen.ValidationResult()
        assert wbsgen.parse_tasks(None, validation) == []
        assert validation.has_errors

class TestDisplayParsingTests:

    def test_parse_display_normalizes_nested_partial_orders(self):
        validation = wbsgen.ValidationResult()
        display = wbsgen.parse_display({'standard': {'columns': {'visible': ['*', '-comment'], 'width': {'name': 260}, 'order': ['progress']}}, 'analysis': {'columns': {'order': ['delay']}}, 'layers': {'visible': ['*', '-tooltip']}}, validation)
        assert display.standard_columns == ('*', '-comment')
        assert display.standard_column_widths == {'name': 260}
        assert display.standard_column_order == ('progress', 'assignee', 'planned-period', 'actual-period', 'expected-progress', 'issue')
        assert display.analysis_column_order == ('delay', 'assignee', 'progress', 'expected-progress', 'delta', 'pace')
        assert display.layers == ('*', '-tooltip')
        assert not validation.errors

    def test_parse_display_rejects_old_and_fixed_or_duplicate_order_keys(self):
        cases = [({'columns': ['*']}, 'display.columns'), ({'columnWidths': {}}, 'display.columnWidths'), ({'layers': ['*']}, 'display.layers'), ({'standard': {'columns': {'order': ['comment']}}}, 'display.standard.columns.order[0]'), ({'analysis': {'columns': {'visible': ['*']}}}, 'display.analysis.columns.visible'), ({'standard': {'columns': {'order': ['progress', 'progress']}}}, 'display.standard.columns.order[1]')]
        for raw_display, path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_display(raw_display, validation)
                assert validation.errors[0].code == wbsgen.CODE_DISPLAY_INVALID
                assert validation.errors[0].path == path

    def test_parse_display_defaults_to_all_visible(self):
        validation = wbsgen.ValidationResult()
        display = wbsgen.parse_display(None, validation)
        assert display.standard_columns == ('*',)
        assert display.layers == ('*',)
        assert not validation.errors

    def test_parse_display_accepts_star_exclusions_and_explicit_lists(self):
        validation = wbsgen.ValidationResult()
        display = wbsgen.parse_display({'standard': {'columns': {'visible': ['*', '-comment']}}, 'layers': {'visible': ['actual', 'inazuma', 'highlight']}}, validation)
        assert display.standard_columns == ('*', '-comment')
        assert display.layers == ('actual', 'inazuma', 'highlight')
        assert not validation.errors

    def test_parse_display_rejects_invalid_shapes_and_keys(self):
        cases = [([], 'display'), ({'standard': 'planned'}, 'display.standard'), ({'standard': {'columns': []}}, 'display.standard.columns'), ({'standard': {'columns': {'visible': []}}}, 'display.standard.columns.visible'), ({'layers': {'visible': [1]}}, 'display.layers.visible[0]'), ({'layers': {'visible': None}}, 'display.layers.visible'), ({'layers': {'visible': []}}, 'display.layers.visible'), ({'standard': {'columns': {'visible': ['unknown']}}}, 'display.standard.columns.visible[0]'), ({'standard': {'columns': {'visible': ['-comment']}}}, 'display.standard.columns.visible'), ({'layers': {'visible': ['*', '-unknown']}}, 'display.layers.visible[1]')]
        for raw_display, expected_path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_display(raw_display, validation)
                assert validation.errors
                assert validation.errors[0].code == wbsgen.CODE_DISPLAY_INVALID
                assert validation.errors[0].path == expected_path

    def test_build_project_model_includes_display_settings(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'visible': ['*', '-comment']}}, 'layers': {'visible': ['*', '-tooltip']}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        assert result.display_settings.standard_columns == ('*', '-comment')
        assert result.display_settings.layers == ('*', '-tooltip')
        assert not result.validation.errors

    def test_build_project_model_rejects_null_display_object(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': None, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        assert result.display_settings.standard_columns == ('*',)
        assert result.display_settings.layers == ('*',)
        assert [(message.code, message.path) for message in result.validation.errors] == [(wbsgen.CODE_DISPLAY_INVALID, 'display')]

    def test_parse_display_column_widths_defaults_to_empty(self):
        validation = wbsgen.ValidationResult()
        display = wbsgen.parse_display(None, validation)
        assert display.standard_column_widths == {}
        assert not validation.errors

    def test_parse_display_column_widths_accepts_partial_valid_values(self):
        validation = wbsgen.ValidationResult()
        display = wbsgen.parse_display({'standard': {'columns': {'width': {'name': 260, 'comment': 200}}}}, validation)
        assert display.standard_column_widths == {'name': 260, 'comment': 200}
        assert not validation.errors

    def test_parse_display_column_widths_rejects_invalid_values(self):
        cases = [({'standard': {'columns': {'width': []}}}, 'display.standard.columns.width'), ({'standard': {'columns': {'width': {'unknown': 100}}}}, 'display.standard.columns.width.unknown'), ({'standard': {'columns': {'width': {'name': 39}}}}, 'display.standard.columns.width.name'), ({'standard': {'columns': {'width': {'assignee': '70'}}}}, 'display.standard.columns.width.assignee')]
        for raw_display, expected_path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_display(raw_display, validation)
                assert validation.errors
                assert validation.errors[0].code == wbsgen.CODE_DISPLAY_INVALID
                assert validation.errors[0].path == expected_path

    def test_build_project_model_includes_column_widths(self):
        data = {'project': {'name': '表示設定', 'statusDate': '2026-06-10'}, 'display': {'standard': {'columns': {'width': {'name': 260, 'assignee': 70, 'comment': 200}}}}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-09', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 10))
        assert result.display_settings.standard_column_widths == {'name': 260, 'assignee': 70, 'comment': 200}
        assert not result.validation.errors

class TestProjectParsingTests:

    def test_parse_project_uses_input_status_date(self):
        validation = wbsgen.ValidationResult()
        project = wbsgen.parse_project({'name': '個人開発プロジェクト', 'statusDate': '2026-06-17', 'startDate': '2026-06-01', 'endDate': '2026-06-30', 'issueBaseUrl': 'https://github.com/your_account/your_repo/issues/'}, validation, today=date(2026, 6, 18))
        assert project.name == '個人開発プロジェクト'
        assert project.status_date == date(2026, 6, 17)
        assert project.start_date == date(2026, 6, 1)
        assert project.end_date == date(2026, 6, 30)
        assert project.issue_base_url == 'https://github.com/your_account/your_repo/issues/'
        assert not validation.errors

    def test_parse_project_uses_today_when_status_date_is_missing(self):
        validation = wbsgen.ValidationResult()
        project = wbsgen.parse_project({'name': '個人開発プロジェクト'}, validation, today=date(2026, 6, 18))
        assert project.status_date == date(2026, 6, 18)
        assert not validation.errors
        assert not validation.warnings

    def test_parse_project_reports_required_and_date_errors(self):
        cases = [(None, wbsgen.CODE_PROJECT_REQUIRED, 'project'), ({}, wbsgen.CODE_PROJECT_NAME_REQUIRED, 'project.name'), ({'name': 'x', 'statusDate': '2026/06/17'}, wbsgen.CODE_PROJECT_DATE_INVALID, 'project.statusDate'), ({'name': 'x', 'statusDate': '20260617'}, wbsgen.CODE_PROJECT_DATE_INVALID, 'project.statusDate'), ({'name': 'x', 'startDate': 'bad-date'}, wbsgen.CODE_PROJECT_DATE_INVALID, 'project.startDate'), ({'name': 'x', 'endDate': 'bad-date'}, wbsgen.CODE_PROJECT_DATE_INVALID, 'project.endDate')]
        for raw_project, expected_code, expected_path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                project = wbsgen.parse_project(raw_project, validation, today=date(2026, 6, 18))
                assert project is None
                assert validation.errors[0].code == expected_code
                assert validation.errors[0].path == expected_path

    def test_parse_project_collects_multiple_project_errors(self):
        validation = wbsgen.ValidationResult()
        project = wbsgen.parse_project({'statusDate': 'bad-status', 'startDate': 'bad-start', 'endDate': 'bad-end'}, validation, today=date(2026, 6, 18))
        assert project is None
        assert [(message.code, message.path) for message in validation.errors] == [(wbsgen.CODE_PROJECT_NAME_REQUIRED, 'project.name'), (wbsgen.CODE_PROJECT_DATE_INVALID, 'project.statusDate'), (wbsgen.CODE_PROJECT_DATE_INVALID, 'project.startDate'), (wbsgen.CODE_PROJECT_DATE_INVALID, 'project.endDate')]

class TestTaskParsingTests:

    def test_parse_tasks_accepts_valid_leaf_task(self):
        validation = wbsgen.ValidationResult()
        tasks = wbsgen.parse_tasks([{'id': '1.2', 'name': 'Lambda修正', 'plannedStart': '2026-06-06', 'plannedDuration': 10, 'actualStart': '2026-06-07', 'actualEnd': None, 'progress': 50, 'issue': 124, 'comment': '実装中', 'assignee': '担当者A'}], validation)
        assert len(tasks) == 1
        assert tasks[0].id == '1.2'
        assert tasks[0].name == 'Lambda修正'
        assert tasks[0].planned_start == date(2026, 6, 6)
        assert tasks[0].planned_duration == 10
        assert tasks[0].actual_start == date(2026, 6, 7)
        assert tasks[0].actual_end is None
        assert tasks[0].progress == 50
        assert tasks[0].issue == 124
        assert tasks[0].comment == '実装中'
        assert tasks[0].assignee == '担当者A'
        assert tasks[0].source_index == 0
        assert not tasks[0].generated
        assert not validation.errors

    def test_parse_tasks_ignores_non_string_assignee(self):
        validation = wbsgen.ValidationResult()
        tasks = wbsgen.parse_tasks([{'id': '1', 'name': 'タスク', 'assignee': 123}], validation)
        assert tasks[0].assignee is None

    def test_parse_tasks_defaults_missing_progress_to_zero(self):
        validation = wbsgen.ValidationResult()
        tasks = wbsgen.parse_tasks([{'id': '1', 'name': 'x'}], validation)
        assert tasks[0].progress == 0
        assert not validation.errors

    def test_parse_tasks_treats_missing_progress_with_actual_end_as_mismatch(self):
        validation = wbsgen.ValidationResult()
        wbsgen.parse_tasks([{'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': '2026-06-02'}], validation)
        assert [(message.code, message.path) for message in validation.errors] == [(wbsgen.CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH, 'tasks[0].progress')]

    def test_parse_tasks_rejects_invalid_wbs_ids(self):
        cases = [('A', wbsgen.CODE_TASK_ID_INVALID), ('1.A', wbsgen.CODE_TASK_ID_INVALID), ('1..2', wbsgen.CODE_TASK_ID_INVALID), ('.1', wbsgen.CODE_TASK_ID_INVALID), ('1.', wbsgen.CODE_TASK_ID_INVALID), ('01', wbsgen.CODE_TASK_ID_INVALID), ('', wbsgen.CODE_TASK_ID_REQUIRED), (None, wbsgen.CODE_TASK_ID_REQUIRED), (0, wbsgen.CODE_TASK_ID_INVALID), (False, wbsgen.CODE_TASK_ID_INVALID)]
        for task_id, expected_code in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                tasks = wbsgen.parse_tasks([{'id': task_id, 'name': 'bad', 'progress': 0}], validation)
                assert tasks == []
                assert validation.errors[0].code == expected_code
                assert validation.errors[0].path == 'tasks[0].id'

    def test_parse_tasks_reports_required_and_duplicate_errors(self):
        validation = wbsgen.ValidationResult()
        tasks = wbsgen.parse_tasks(['not-object', {'id': '1'}, {'id': '1', 'name': 'duplicate', 'progress': 0}], validation)
        assert [task.id for task in tasks] == ['1']
        assert [(message.code, message.path) for message in validation.errors] == [(wbsgen.CODE_TASK_REQUIRED, 'tasks[0]'), (wbsgen.CODE_TASK_NAME_REQUIRED, 'tasks[1].name'), (wbsgen.CODE_TASK_ID_DUPLICATED, 'tasks[2].id')]

    def test_parse_tasks_reports_progress_and_duration_errors(self):
        cases = [({'id': '1', 'name': 'x', 'progress': -1}, wbsgen.CODE_TASK_PROGRESS_INVALID, 'tasks[0].progress'), ({'id': '1', 'name': 'x', 'progress': 101}, wbsgen.CODE_TASK_PROGRESS_INVALID, 'tasks[0].progress'), ({'id': '1', 'name': 'x', 'progress': '50'}, wbsgen.CODE_TASK_PROGRESS_INVALID, 'tasks[0].progress'), ({'id': '1', 'name': 'x', 'progress': True}, wbsgen.CODE_TASK_PROGRESS_INVALID, 'tasks[0].progress'), ({'id': '1', 'name': 'x', 'progress': 0, 'plannedDuration': 0}, wbsgen.CODE_TASK_PLANNED_DURATION_INVALID, 'tasks[0].plannedDuration'), ({'id': '1', 'name': 'x', 'progress': 0, 'plannedDuration': True}, wbsgen.CODE_TASK_PLANNED_DURATION_INVALID, 'tasks[0].plannedDuration')]
        for raw_task, expected_code, expected_path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_tasks([raw_task], validation)
                assert (expected_code, expected_path) in [(message.code, message.path) for message in validation.errors]

    def test_parse_tasks_validates_actual_end_and_progress_consistency(self):
        cases = [({'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': '2026-06-02', 'progress': 100}, []), ({'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': None, 'progress': 50}, []), ({'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': None, 'progress': 100}, [(wbsgen.CODE_TASK_PROGRESS_COMPLETE_WITHOUT_ACTUAL_END, 'tasks[0].progress')]), ({'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': '2026-06-02'}, [(wbsgen.CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH, 'tasks[0].progress')]), ({'id': '1', 'name': 'x', 'actualStart': '2026-06-01', 'actualEnd': '2026-06-02', 'progress': 50}, [(wbsgen.CODE_TASK_PROGRESS_ACTUAL_END_MISMATCH, 'tasks[0].progress')])]
        for raw_task, expected_errors in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_tasks([raw_task], validation)
                assert [(message.code, message.path) for message in validation.errors] == expected_errors

    def test_parse_tasks_rejects_actual_end_before_actual_start(self):
        validation = wbsgen.ValidationResult()
        wbsgen.parse_tasks([{'id': '1', 'name': 'x', 'actualStart': '2026-06-03', 'actualEnd': '2026-06-02', 'progress': 100}], validation)
        assert (wbsgen.CODE_TASK_ACTUAL_END_BEFORE_ACTUAL_START, 'tasks[0].actualEnd') in [(message.code, message.path) for message in validation.errors]

    def test_parse_tasks_rejects_actual_end_without_actual_start(self):
        validation = wbsgen.ValidationResult()
        wbsgen.parse_tasks([{'id': '1', 'name': 'x', 'actualEnd': '2026-06-02', 'progress': 100}], validation)
        assert (wbsgen.CODE_TASK_ACTUAL_END_WITHOUT_ACTUAL_START, 'tasks[0].actualStart') in [(message.code, message.path) for message in validation.errors]

class TestHolidayModelTests:

    def test_holiday_model_holds_date_and_optional_name(self):
        holiday = wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日')
        assert holiday.date == date(2026, 6, 8)
        assert holiday.name == '会社休日'

    def test_holiday_model_defaults_name_to_none(self):
        holiday = wbsgen.Holiday(date=date(2026, 8, 10))
        assert holiday.name is None

class TestHolidayParsingTests:

    def test_parse_holidays_defaults_to_empty_list_when_omitted(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays(None, validation)
        assert holidays == []
        assert not validation.errors

    def test_parse_holidays_accepts_empty_array(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays([], validation)
        assert holidays == []
        assert not validation.errors

    def test_parse_holidays_keeps_date_and_name(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays([{'date': '2026-06-08', 'name': '会社休日'}], validation)
        assert len(holidays) == 1
        assert holidays[0].date == date(2026, 6, 8)
        assert holidays[0].name == '会社休日'
        assert not validation.errors

    def test_parse_holidays_treats_missing_name_as_no_name(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays([{'date': '2026-08-10'}], validation)
        assert holidays[0].date == date(2026, 8, 10)
        assert holidays[0].name is None
        assert not validation.errors

    def test_parse_holidays_treats_empty_name_as_no_name(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays([{'date': '2026-08-10', 'name': ''}], validation)
        assert holidays[0].date == date(2026, 8, 10)
        assert holidays[0].name is None
        assert not validation.errors

    def test_parse_holidays_rejects_non_array(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays({'date': '2026-06-08'}, validation)
        assert holidays == []
        assert [(message.code, message.path) for message in validation.errors] == [(wbsgen.CODE_HOLIDAYS_INVALID, 'holidays')]

    def test_parse_holidays_reports_element_and_date_errors(self):
        cases = [('not-object', wbsgen.CODE_HOLIDAY_REQUIRED, 'holidays[0]'), ({'name': '元日なのに日付がない'}, wbsgen.CODE_HOLIDAY_DATE_INVALID, 'holidays[0].date'), ({'date': 20260608}, wbsgen.CODE_HOLIDAY_DATE_INVALID, 'holidays[0].date'), ({'date': '2026/06/08'}, wbsgen.CODE_HOLIDAY_DATE_INVALID, 'holidays[0].date'), ({'date': '2026-02-30'}, wbsgen.CODE_HOLIDAY_DATE_INVALID, 'holidays[0].date'), ({'date': '2026-06-08', 'name': 123}, wbsgen.CODE_HOLIDAY_NAME_INVALID, 'holidays[0].name')]
        for raw_holiday, expected_code, expected_path in cases:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_holidays([raw_holiday], validation)
                assert validation.errors[0].code == expected_code
                assert validation.errors[0].path == expected_path

    def test_parse_holidays_reports_duplicate_date(self):
        validation = wbsgen.ValidationResult()
        holidays = wbsgen.parse_holidays([{'date': '2026-06-08', 'name': '会社休日A'}, {'date': '2026-06-08', 'name': '会社休日B'}], validation)
        assert [(message.code, message.path) for message in validation.errors] == [(wbsgen.CODE_HOLIDAY_DATE_DUPLICATED, 'holidays[1].date')]

class TestLoadJsonTests:

    def test_load_json_rejects_missing_file(self):
        with pytest.raises(ValueError, match='input JSON file not found'):
            wbsgen.load_json(Path('missing.json'))

    def test_load_json_rejects_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / 'input.json'
            input_path.write_text('{invalid', encoding='utf-8')
            with pytest.raises(ValueError, match='invalid JSON'):
                wbsgen.load_json(input_path)

    def test_load_json_rejects_non_object_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / 'input.json'
            input_path.write_text('[]', encoding='utf-8')
            with pytest.raises(ValueError, match='root must be an object'):
                wbsgen.load_json(input_path)

class TestParseMilestonesTests:

    def test_parse_milestones_returns_empty_for_none(self):
        validation = wbsgen.ValidationResult()
        assert wbsgen.parse_milestones(None, validation) == []
        assert not validation.errors
        assert not validation.warnings

    def test_parse_milestones_rejects_non_list(self):
        validation = wbsgen.ValidationResult()
        assert wbsgen.parse_milestones({'date': '2026-06-12'}, validation) == []
        assert validation.errors[0].code == wbsgen.CODE_MILESTONES_INVALID

    def test_parse_milestones_rejects_non_dict_entry(self):
        validation = wbsgen.ValidationResult()
        assert wbsgen.parse_milestones(['x'], validation) == []
        assert validation.errors[0].code == wbsgen.CODE_MILESTONE_REQUIRED
        assert validation.errors[0].path == 'milestones[0]'

    def test_parse_milestones_requires_valid_date(self):
        for raw in [{}, {'date': '2026/06/12', 'name': 'A'}, {'date': 20260612, 'name': 'A'}]:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                wbsgen.parse_milestones([raw], validation)
                codes = [message.code for message in validation.errors]
                assert wbsgen.CODE_MILESTONE_DATE_INVALID in codes

    def test_parse_milestones_requires_name(self):
        for raw in [{'date': '2026-06-12'}, {'date': '2026-06-12', 'name': ''}, {'date': '2026-06-12', 'name': 1}]:
            with nullcontext():
                validation = wbsgen.ValidationResult()
                assert wbsgen.parse_milestones([raw], validation) == []
                codes = [message.code for message in validation.errors]
                assert wbsgen.CODE_MILESTONE_NAME_REQUIRED in codes

    def test_parse_milestones_parses_valid_entries_with_source_index(self):
        validation = wbsgen.ValidationResult()
        milestones = wbsgen.parse_milestones([{'date': '2026-06-12', 'name': '中間レビュー'}, {'date': '2026-06-30', 'name': 'リリース判定'}], validation)
        assert [(m.date, m.name, m.source_index) for m in milestones] == [(date(2026, 6, 12), '中間レビュー', 0), (date(2026, 6, 30), 'リリース判定', 1)]
        assert not validation.errors

    def test_parse_milestones_warns_on_exact_duplicate_and_keeps_both(self):
        validation = wbsgen.ValidationResult()
        milestones = wbsgen.parse_milestones([{'date': '2026-06-12', 'name': '中間レビュー'}, {'date': '2026-06-12', 'name': '中間レビュー'}], validation)
        assert len(milestones) == 2
        assert validation.warnings[0].code == wbsgen.CODE_MILESTONE_DUPLICATED

    def test_display_layers_accepts_milestone_key(self):
        validation = wbsgen.ValidationResult()
        settings = wbsgen.parse_display({'layers': {'visible': ['milestone']}}, validation)
        assert not validation.errors
        assert settings.layers == ('milestone',)
