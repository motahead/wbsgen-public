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

class TestPlannerModuleTests:

    def test_planner_exports_existing_planning_functions(self):
        from wbsgen import planner
        assert planner.build_wbs_tree is wbsgen.build_wbs_tree
        assert planner.compute_task is wbsgen.compute_task
        assert planner.compute_roots is wbsgen.compute_roots
        assert planner.build_project_model is wbsgen.build_project_model
        assert planner.progress_x_for_task is wbsgen.progress_x_for_task

class TestWorkingDayCalculationTests:

    def test_work_calendar_returns_matching_holiday_or_none(self):
        holiday = wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日')
        calendar = wbsgen.WorkCalendar(holidays=(holiday,))
        assert calendar.holiday_for(date(2026, 6, 8)) is holiday
        assert calendar.holiday_for(date(2026, 6, 9)) is None

    def test_calculate_planned_end_counts_start_date_as_day_one(self):
        assert wbsgen.calculate_planned_end(date(2026, 6, 1), 5) == date(2026, 6, 5)

    def test_calculate_planned_end_skips_weekends(self):
        assert wbsgen.calculate_planned_end(date(2026, 6, 4), 3) == date(2026, 6, 8)

    def test_calculate_planned_end_rejects_non_positive_duration(self):
        with pytest.raises(ValueError, match='planned_duration must be positive'):
            wbsgen.calculate_planned_end(date(2026, 6, 1), 0)

    def test_is_weekend_detects_saturday_and_sunday(self):
        assert not wbsgen.is_weekend(date(2026, 6, 5))
        assert wbsgen.is_weekend(date(2026, 6, 6))
        assert wbsgen.is_weekend(date(2026, 6, 7))

    def test_calculate_planned_end_excludes_holiday_between_weekends(self):
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        assert wbsgen.calculate_planned_end(date(2026, 6, 4), 3, calendar=calendar) == date(2026, 6, 9)

    def test_calculate_planned_end_excludes_holiday_after_weekend(self):
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 7, 20), name='海の日'),))
        assert wbsgen.calculate_planned_end(date(2026, 7, 17), 2, calendar=calendar) == date(2026, 7, 21)

    def test_calculate_planned_end_matches_weekend_only_result_without_calendar(self):
        assert wbsgen.calculate_planned_end(date(2026, 6, 4), 3) == date(2026, 6, 8)

class TestComputedTaskTests:

    def test_compute_leaf_task_calculates_planned_end(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 4), planned_duration=3, progress=50, source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.id == '1'
        assert computed.planned_start == date(2026, 6, 4)
        assert computed.planned_end == date(2026, 6, 8)
        assert computed.planned_duration == 3
        assert computed.progress == 50
        assert not computed.children
        assert not validation.errors
        assert not validation.warnings

    def test_compute_leaf_task_warns_for_weekend_start(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='週末開始', planned_start=date(2026, 6, 6), planned_duration=1, progress=0, source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.planned_end == date(2026, 6, 8)
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_TASK_PLANNED_START_WEEKEND, 'tasks[0].plannedStart')]

    def test_compute_leaf_task_calculates_planned_end_excluding_holidays(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 4), planned_duration=3, progress=50, source_index=0)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10), calendar=calendar)
        assert computed.planned_start == date(2026, 6, 4)
        assert computed.planned_end == date(2026, 6, 9)
        assert not validation.warnings

    def test_compute_leaf_task_warns_for_holiday_start(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='祝日開始', planned_start=date(2026, 6, 8), planned_duration=1, progress=0, source_index=0)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10), calendar=calendar)
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_TASK_PLANNED_START_NON_WORKING_DAY, 'tasks[0].plannedStart')]
        assert wbsgen.CODE_TASK_PLANNED_START_WEEKEND not in [message.code for message in validation.warnings]

    def test_compute_leaf_task_prefers_holiday_warning_when_start_is_weekend_and_holiday(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='週末かつ祝日開始', planned_start=date(2026, 6, 6), planned_duration=1, progress=0, source_index=0)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 6), name='特別休日'),))
        wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10), calendar=calendar)
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_TASK_PLANNED_START_NON_WORKING_DAY, 'tasks[0].plannedStart')]

    def test_compute_leaf_task_marks_missing_plan_as_unplanned_warning(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='未計画', progress=0, source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.planned_start is None
        assert computed.planned_end is None
        assert computed.planned_duration is None
        assert computed.progress == 0
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_TASK_UNPLANNED, 'tasks[0]')]

    def test_compute_leaf_task_skips_invalid_duration_without_warning(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='不正期間', planned_start=date(2026, 6, 1), planned_duration=0, progress=0, source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.planned_start is None
        assert computed.planned_end is None
        assert computed.planned_duration is None
        assert not validation.errors
        assert not validation.warnings

    def test_compute_leaf_task_keeps_open_actual_end_as_none(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='実績中', planned_start=date(2026, 6, 1), planned_duration=1, actual_start=date(2026, 6, 2), actual_end=None, progress=50, source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.actual_start == date(2026, 6, 2)
        assert computed.actual_end is None

    def test_compute_parent_aggregates_descendant_leaf_tasks(self):
        validation = wbsgen.ValidationResult()
        root = wbsgen.Task(id='1', name='親', progress=100, source_index=0)
        child_a = wbsgen.Task(id='1.1', name='子A', planned_start=date(2026, 6, 1), planned_duration=5, actual_start=date(2026, 6, 1), actual_end=date(2026, 6, 5), progress=100, source_index=1)
        child_group = wbsgen.Task(id='1.2', name='子グループ', planned_start=date(2026, 6, 15), planned_duration=10, actual_start=date(2026, 6, 15), actual_end=date(2026, 6, 19), progress=0, source_index=2)
        grandchild_b = wbsgen.Task(id='1.2.1', name='孫B', planned_start=date(2026, 6, 8), planned_duration=3, actual_start=date(2026, 6, 8), actual_end=None, progress=50, source_index=3)
        child_group.children = [grandchild_b]
        root.children = [child_a, child_group]
        computed = wbsgen.compute_task(root, validation, status_date=date(2026, 6, 10))
        assert computed.planned_start == date(2026, 6, 1)
        assert computed.planned_end == date(2026, 6, 10)
        assert computed.planned_duration == 8
        assert computed.actual_start == date(2026, 6, 1)
        assert computed.actual_end is None
        assert computed.progress == 81
        assert [child.id for child in computed.children] == ['1.1', '1.2']

    def test_compute_parent_ignores_unplanned_leaf_for_plan_and_progress(self):
        validation = wbsgen.ValidationResult()
        root = wbsgen.Task(id='1', name='親', source_index=0)
        planned = wbsgen.Task(id='1.1', name='計画済み', planned_start=date(2026, 6, 1), planned_duration=5, progress=20, source_index=1)
        unplanned = wbsgen.Task(id='1.2', name='未計画', progress=100, source_index=2)
        root.children = [planned, unplanned]
        computed = wbsgen.compute_task(root, validation, status_date=date(2026, 6, 10))
        assert computed.planned_start == date(2026, 6, 1)
        assert computed.planned_end == date(2026, 6, 5)
        assert computed.planned_duration == 5
        assert computed.progress == 20
        assert (wbsgen.CODE_TASK_UNPLANNED, 'tasks[2]') in [(message.code, message.path) for message in validation.warnings]

class TestWbsTreeBuildingTests:

    def test_build_wbs_tree_sorts_roots_and_children_by_numeric_segments(self):
        validation = wbsgen.ValidationResult()
        tasks = [wbsgen.Task(id='1.10', name='子10', source_index=0), wbsgen.Task(id='2', name='別ルート', source_index=1), wbsgen.Task(id='1.2', name='子2', source_index=2), wbsgen.Task(id='1', name='親', source_index=3)]
        roots = wbsgen.build_wbs_tree(tasks, validation)
        assert [task.id for task in roots] == ['1', '2']
        assert [task.id for task in roots[0].children] == ['1.2', '1.10']
        assert not validation.errors
        assert not validation.warnings

    def test_build_wbs_tree_generates_all_missing_ancestor_tasks(self):
        validation = wbsgen.ValidationResult()
        tasks = [wbsgen.Task(id='1.2.3', name='実装', source_index=0)]
        roots = wbsgen.build_wbs_tree(tasks, validation)
        assert [task.id for task in roots] == ['1']
        assert roots[0].name == 'タスクを定義してください'
        assert roots[0].generated
        assert roots[0].source_index is None
        assert roots[0].planned_start is None
        assert roots[0].planned_duration is None
        assert roots[0].actual_start is None
        assert roots[0].actual_end is None
        assert roots[0].progress is None
        assert roots[0].issue is None
        assert roots[0].comment is None
        assert roots[0].assignee is None
        generated_child = roots[0].children[0]
        assert generated_child.id == '1.2'
        assert generated_child.generated
        assert generated_child.children[0].id == '1.2.3'
        assert tasks == [generated_child.children[0]]
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id'), (wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id')]

    def test_build_wbs_tree_warns_for_each_direct_parent_field_ignored(self):
        validation = wbsgen.ValidationResult()
        tasks = [wbsgen.Task(id='1', name='親', planned_start=date(2026, 6, 1), planned_duration=5, actual_start=date(2026, 6, 2), actual_end=date(2026, 6, 3), progress=100, has_progress_input=True, source_index=0), wbsgen.Task(id='1.1', name='子', source_index=1)]
        wbsgen.build_wbs_tree(tasks, validation)
        assert [(message.code, message.path) for message in validation.warnings] == [(wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].plannedStart'), (wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].plannedDuration'), (wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].actualStart'), (wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].actualEnd'), (wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].progress')]

    def test_build_wbs_tree_does_not_warn_for_defaulted_parent_progress(self):
        validation = wbsgen.ValidationResult()
        tasks = wbsgen.parse_tasks([{'id': '1', 'name': '親'}, {'id': '1.1', 'name': '子'}], validation)
        wbsgen.build_wbs_tree(tasks, validation)
        assert tasks[0].progress == 0
        assert (wbsgen.CODE_PARENT_FIELD_IGNORED, 'tasks[0].progress') not in [(message.code, message.path) for message in validation.warnings]

class TestProjectModelBuildTests:

    def test_build_project_model_parses_project_tasks_and_roots(self):
        data = {'project': {'name': '個人開発プロジェクト'}, 'tasks': [{'id': '1.1', 'name': '子', 'progress': 0}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert result.project is not None
        assert result.project.status_date == date(2026, 6, 18)
        assert [task.id for task in result.tasks] == ['1.1']
        assert [task.id for task in result.roots] == ['1']
        assert result.roots[0].generated
        assert result.roots[0].children[0].id == '1.1'
        assert not result.validation.errors
        assert [(message.code, message.path) for message in result.validation.warnings] == [(wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id'), (wbsgen.CODE_TASK_UNPLANNED, 'tasks[0]')]

    def test_build_project_model_includes_computed_roots_and_project_range(self):
        data = {'project': {'name': '個人開発プロジェクト', 'startDate': '2026-06-01', 'endDate': '2026-06-30', 'statusDate': '2026-06-17'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-04', 'plannedDuration': 3}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert result.display_start_date == date(2026, 6, 1)
        assert result.display_end_date == date(2026, 6, 30)
        assert result.computed_roots[0].planned_end == date(2026, 6, 8)

    def test_build_project_model_auto_calculates_display_range(self):
        data = {'project': {'name': '個人開発プロジェクト', 'statusDate': '2026-06-17'}, 'tasks': [{'id': '1', 'name': '実装', 'plannedStart': '2026-06-04', 'plannedDuration': 3, 'actualStart': '2026-06-09'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert result.display_start_date == date(2026, 6, 4)
        assert result.display_end_date == date(2026, 6, 17)

    def test_build_project_model_keeps_display_range_order_with_partial_project_range(self):
        data = {'project': {'name': '個人開発プロジェクト', 'startDate': '2026-06-20', 'statusDate': '2026-06-17'}, 'tasks': []}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert result.display_start_date == date(2026, 6, 20)
        assert result.display_end_date == date(2026, 6, 20)

    def test_build_project_model_warns_for_status_date_out_of_range(self):
        data = {'project': {'name': '個人開発プロジェクト', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-17'}, 'tasks': [{'id': '1', 'name': '未計画'}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert (wbsgen.CODE_PROJECT_STATUS_DATE_OUT_OF_RANGE, 'project.statusDate') in [(message.code, message.path) for message in result.validation.warnings]

    def test_build_project_model_warns_for_task_dates_out_of_range(self):
        data = {'project': {'name': '個人開発プロジェクト', 'startDate': '2026-06-01', 'endDate': '2026-06-10', 'statusDate': '2026-06-05'}, 'tasks': [{'id': '1', 'name': '範囲外', 'plannedStart': '2026-06-11', 'plannedDuration': 1}]}
        result = wbsgen.build_project_model(data, today=date(2026, 6, 18))
        assert (wbsgen.CODE_TASK_DATE_OUT_OF_RANGE, 'tasks[0].plannedStart') in [(message.code, message.path) for message in result.validation.warnings]

    def test_build_project_model_uses_current_date_when_today_is_omitted(self):
        data = {'project': {'name': '個人開発プロジェクト'}, 'tasks': []}
        result = wbsgen.build_project_model(data)
        assert result.project is not None
        assert result.project.status_date == date.today()

    def test_format_validation_messages_outputs_errors_before_warnings(self):
        validation = wbsgen.ValidationResult()
        validation.warning(wbsgen.CODE_MISSING_PARENT_TASK, 'tasks[0].id', '親タスク 1 を補完しました')
        validation.error(wbsgen.CODE_PROJECT_NAME_REQUIRED, 'project.name', 'project.name は必須です')
        assert wbsgen.format_validation_messages(validation) == ['wbsgen: error PROJECT_NAME_REQUIRED project.name: project.name は必須です', 'wbsgen: warning MISSING_PARENT_TASK tasks[0].id: 親タスク 1 を補完しました']

class TestChartScaleTests:

    def test_iter_dates_includes_start_and_end(self):
        assert list(wbsgen.iter_dates(date(2026, 6, 5), date(2026, 6, 7))) == [date(2026, 6, 5), date(2026, 6, 6), date(2026, 6, 7)]

    def test_chart_scale_converts_dates_to_column_positions(self):
        scale = wbsgen.ChartScale(start_date=date(2026, 6, 1), end_date=date(2026, 6, 3), day_width=24)
        assert scale.column_count == 3
        assert scale.chart_width == 72
        assert scale.x_for_date(date(2026, 6, 1)) == 0
        assert scale.x_for_date(date(2026, 6, 2)) == 24
        assert scale.x_for_date_end(date(2026, 6, 3)) == 72

    def test_progress_x_uses_planned_start_for_zero_progress(self):
        scale = wbsgen.ChartScale(start_date=date(2026, 6, 1), end_date=date(2026, 6, 12), day_width=28)
        assert wbsgen.progress_x_for_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), progress=0, status_date=date(2026, 6, 10), scale=scale) == scale.x_for_date(date(2026, 6, 1))

    def test_progress_x_uses_status_date_end_for_complete_progress(self):
        scale = wbsgen.ChartScale(start_date=date(2026, 6, 1), end_date=date(2026, 6, 12), day_width=28)
        assert wbsgen.progress_x_for_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), progress=100, status_date=date(2026, 6, 10), scale=scale) == scale.x_for_date_end(date(2026, 6, 10))

    def test_progress_x_excludes_weekends_for_partial_progress(self):
        scale = wbsgen.ChartScale(start_date=date(2026, 6, 1), end_date=date(2026, 6, 12), day_width=28)
        assert wbsgen.progress_x_for_task(planned_start=date(2026, 6, 4), planned_end=date(2026, 6, 10), progress=50, status_date=date(2026, 6, 10), scale=scale) == scale.x_for_date(date(2026, 6, 8)) + 14

    def test_progress_x_excludes_holidays_for_partial_progress(self):
        scale = wbsgen.ChartScale(start_date=date(2026, 6, 1), end_date=date(2026, 6, 12), day_width=28)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        assert wbsgen.progress_x_for_task(planned_start=date(2026, 6, 4), planned_end=date(2026, 6, 10), progress=50, status_date=date(2026, 6, 10), scale=scale, calendar=calendar) == scale.x_for_date(date(2026, 6, 5)) + 28

class TestPlannerFunctionTests:

    def test_planner_guards_for_empty_ranges_and_generated_tasks(self):
        from wbsgen import planner
        source = wbsgen.Task(id='1', name='T')
        weekend_task = wbsgen.ComputedTask(id='1', name='T', source_task=source, planned_start=date(2026, 6, 6), planned_end=date(2026, 6, 7), progress=50)
        project = wbsgen.Project(name='P', status_date=date(2026, 6, 7))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 10))
        assert wbsgen.expected_progress_for_task(weekend_task, project) is None
        assert wbsgen.progress_analysis_for_task(weekend_task, project).delta is None
        assert wbsgen.progress_x_for_task(date(2026, 6, 6), date(2026, 6, 7), 50, project.status_date, scale) == scale.x_for_date(date(2026, 6, 6))
        assert planner.task_source_path(wbsgen.Task(id='1', name='T')) == 'tasks'
        assert planner.determine_display_range(None, []) == (None, None)

    def test_planner_helpers_handle_leaf_trees_and_missing_display_ranges(self):
        from wbsgen import planner
        leaf = wbsgen.Task(id='1.1', name='leaf')
        root = wbsgen.Task(id='1', name='root', children=[leaf])
        validation = wbsgen.ValidationResult()
        assert planner.leaf_tasks(root) == [leaf]
        planner.validate_display_range(None, [], None, None, validation)
        planner.validate_milestone_range([], None, None, validation)
        assert not validation.errors
        assert not validation.warnings

    def test_display_range_includes_explicit_end_without_start(self):
        from wbsgen import planner
        project = wbsgen.Project(name='P', status_date=date(2026, 6, 10), end_date=date(2026, 6, 20))
        assert planner.determine_display_range(project, []) == (date(2026, 6, 10), date(2026, 6, 20))

    def test_progress_analysis_handles_calendar_that_becomes_empty_after_expectation(self):
        from wbsgen import planner
        task = wbsgen.ComputedTask(id='1', name='T', source_task=wbsgen.Task(id='1', name='T'), planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 2), progress=0)
        project = wbsgen.Project(name='P', status_date=date(2026, 6, 2))
        with mock.patch('wbsgen.planner.working_dates_between', side_effect=[[date(2026, 6, 1), date(2026, 6, 2)], [], [date(2026, 6, 2)]]):
            analysis = planner.progress_analysis_for_task(task, project)
        assert analysis.delay_business_days is None

    def test_progress_position_has_a_defensive_fallback_for_inconsistent_rounding(self):
        from wbsgen import planner
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 2))
        with mock.patch.object(planner, 'working_dates_between', return_value=[date(2026, 6, 1)]), mock.patch('builtins.round', return_value=99):
            value = planner.progress_x_for_task(date(2026, 6, 1), date(2026, 6, 1), 50, date(2026, 6, 1), scale)
        assert value == scale.x_for_date_end(date(2026, 6, 1))

    def test_planner_exports_expected_progress_function(self):
        from wbsgen import planner
        assert planner.expected_progress_for_task is wbsgen.expected_progress_for_task

    def test_expected_progress_treats_status_date_as_start_of_day(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 3))
        source_task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 1), planned_duration=5)
        task = wbsgen.ComputedTask(id='1', name='実装', source_task=source_task, planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), planned_duration=5)
        assert wbsgen.expected_progress_for_task(task, project) == 40

    def test_expected_progress_handles_before_start_after_end_and_unplanned(self):
        source_task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 1), planned_duration=5)
        task = wbsgen.ComputedTask(id='1', name='実装', source_task=source_task, planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), planned_duration=5)
        unplanned_task = wbsgen.ComputedTask(id='2', name='未計画', source_task=wbsgen.Task(id='2', name='未計画'))
        assert wbsgen.expected_progress_for_task(task, wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 1))) == 0
        assert wbsgen.expected_progress_for_task(task, wbsgen.Project(name='進捗確認', status_date=date(2026, 5, 31))) == 0
        assert wbsgen.expected_progress_for_task(task, wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 8))) == 100
        assert wbsgen.expected_progress_for_task(unplanned_task, wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 3))) is None

    def test_expected_progress_excludes_weekends(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 8))
        source_task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 4), planned_duration=5)
        task = wbsgen.ComputedTask(id='1', name='実装', source_task=source_task, planned_start=date(2026, 6, 4), planned_end=date(2026, 6, 10), planned_duration=5)
        assert wbsgen.expected_progress_for_task(task, project) == 40

    def test_expected_progress_excludes_holidays(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 9))
        source_task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 4), planned_duration=5)
        task = wbsgen.ComputedTask(id='1', name='実装', source_task=source_task, planned_start=date(2026, 6, 4), planned_end=date(2026, 6, 10), planned_duration=5)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        assert wbsgen.expected_progress_for_task(task, project, calendar=calendar) == 50

    def test_expected_progress_uses_planned_end_for_aggregated_task_with_gap(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 5))
        task = wbsgen.ComputedTask(id='1', name='親タスク', source_task=wbsgen.Task(id='1', name='親タスク'), planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 10), planned_duration=4)
        assert wbsgen.expected_progress_for_task(task, project) == 50

class TestProgressAnalysisTests:

    def build_task(self, *, planned_start, planned_end, progress):
        source_task = wbsgen.Task(id='1', name='対象タスク', planned_start=planned_start, planned_duration=1)
        return wbsgen.ComputedTask(id='1', name='対象タスク', source_task=source_task, planned_start=planned_start, planned_end=planned_end, progress=progress)

    def test_progress_analysis_matches_spec_example_for_delayed_task(self):
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 12), progress=40)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 9))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert analysis.delta == -20
        assert analysis.delay_business_days == 2
        assert not analysis.pace_unattainable

    def test_progress_analysis_delay_is_zero_when_progress_meets_or_exceeds_expected(self):
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 12), progress=90)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 9))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert analysis.delta == 30
        assert analysis.delay_business_days == 0

    def test_progress_analysis_required_pace_uses_remaining_business_days(self):
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 17), progress=40)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 10))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert abs(analysis.required_pace - 10.0) <= 7
        assert not analysis.pace_unattainable

    def test_progress_analysis_pace_is_zero_when_progress_is_complete(self):
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), progress=100)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 10))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert analysis.required_pace == 0.0
        assert not analysis.pace_unattainable

    def test_progress_analysis_pace_is_unattainable_when_no_remaining_business_days(self):
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), progress=60)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 10))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert analysis.required_pace is None
        assert analysis.pace_unattainable

    def test_progress_analysis_returns_all_none_when_task_is_unplanned(self):
        source_task = wbsgen.Task(id='1', name='未計画')
        task = wbsgen.ComputedTask(id='1', name='未計画', source_task=source_task, progress=0)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 10))
        analysis = wbsgen.progress_analysis_for_task(task, project)
        assert analysis.delta is None
        assert analysis.delay_business_days is None
        assert analysis.required_pace is None
        assert not analysis.pace_unattainable

    def test_progress_analysis_reflects_holiday_calendar_in_delay_and_pace(self):
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='臨時休日'),))
        task = self.build_task(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 12), progress=40)
        project = wbsgen.Project(name='進捗分析確認', status_date=date(2026, 6, 9))
        analysis = wbsgen.progress_analysis_for_task(task, project, calendar=calendar)
        assert analysis.delta is not None
        assert analysis.delta != wbsgen.progress_analysis_for_task(task, project).delta

class TestProgressPointTests:

    def build_row(self, *, task_id: str='1', planned_start: date, planned_end: date, progress: int) -> wbsgen.DisplayRow:
        task = wbsgen.ComputedTask(id=task_id, name='進捗点', source_task=wbsgen.Task(id=task_id, name='進捗点'), planned_start=planned_start, planned_end=planned_end, planned_duration=1, progress=progress)
        return wbsgen.DisplayRow(task=task, depth=0)

    def test_progress_point_uses_status_date_for_future_unstarted_on_schedule_task(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 10))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 30))
        row = self.build_row(planned_start=date(2026, 6, 15), planned_end=date(2026, 6, 17), progress=0)
        point = wbsgen.progress_point_for_row(row, 0, scale, project)
        assert point == (wbsgen.status_date_right_x(project, scale), wbsgen.row_center_y(0), '1')

    def test_progress_point_uses_planned_start_for_unstarted_task_with_expected_progress(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 10))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 30))
        row = self.build_row(planned_start=date(2026, 6, 1), planned_end=date(2026, 6, 5), progress=0)
        point = wbsgen.progress_point_for_row(row, 0, scale, project)
        assert point == (0, wbsgen.row_center_y(0), '1')

    def test_progress_point_includes_clipped_plan_rows(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 5))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 10))
        row = self.build_row(planned_start=date(2026, 5, 28), planned_end=date(2026, 6, 5), progress=50)
        point = wbsgen.progress_point_for_row(row, 0, scale, project)
        assert point is not None
        assert point[0] >= 0
        assert point[0] <= scale.chart_width

    def test_progress_point_clamps_before_display_range_to_left_edge(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 10))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 10))
        row = self.build_row(planned_start=date(2026, 5, 18), planned_end=date(2026, 5, 22), progress=0)
        point = wbsgen.progress_point_for_row(row, 0, scale, project)
        assert point == (0, wbsgen.row_center_y(0), '1')

    def test_progress_point_excludes_holidays_for_partial_progress(self):
        project = wbsgen.Project(name='進捗確認', status_date=date(2026, 6, 10))
        scale = wbsgen.ChartScale(date(2026, 6, 1), date(2026, 6, 30))
        row = self.build_row(planned_start=date(2026, 6, 4), planned_end=date(2026, 6, 10), progress=50)
        calendar = wbsgen.WorkCalendar(holidays=(wbsgen.Holiday(date=date(2026, 6, 8), name='会社休日'),))
        point = wbsgen.progress_point_for_row(row, 0, scale, project, calendar=calendar)
        assert point == (scale.x_for_date(date(2026, 6, 5)) + 32, wbsgen.row_center_y(0), '1')

class TestBuildProjectModelMilestoneTests:

    def base_data(self):
        return {'project': {'name': 'P', 'startDate': '2026-06-01', 'endDate': '2026-06-30', 'statusDate': '2026-06-10'}, 'tasks': [{'id': '1', 'name': 'T', 'plannedStart': '2026-06-01', 'plannedDuration': 5, 'progress': 0}]}

    def test_build_project_model_collects_milestones(self):
        data = self.base_data()
        data['milestones'] = [{'date': '2026-06-12', 'name': '中間レビュー'}]
        result = wbsgen.build_project_model(data)
        assert len(result.milestones) == 1
        assert result.milestones[0].name == '中間レビュー'

    def test_build_project_model_defaults_to_no_milestones(self):
        result = wbsgen.build_project_model(self.base_data())
        assert result.milestones == []

    def test_build_project_model_warns_for_out_of_range_milestone(self):
        data = self.base_data()
        data['milestones'] = [{'date': '2026-07-15', 'name': '範囲外'}]
        result = wbsgen.build_project_model(data)
        warnings = [w for w in result.validation.warnings if w.code == wbsgen.CODE_MILESTONE_DATE_OUT_OF_RANGE]
        assert len(warnings) == 1
        assert warnings[0].path == 'milestones[0].date'

class TestLayoutMilestonesTests:

    def scale(self):
        return wbsgen.ChartScale(date(2026, 5, 31), date(2026, 8, 3))

    def milestone(self, day, name, index=0):
        return wbsgen.Milestone(date=day, name=name, source_index=index)

    def test_layout_returns_empty_for_no_milestones(self):
        assert wbsgen.layout_milestones([], self.scale()) == []

    def test_layout_places_single_milestone_on_tier_zero(self):
        placed = wbsgen.layout_milestones([self.milestone(date(2026, 6, 12), '要件確定')], self.scale())
        assert len(placed) == 1
        assert placed[0].tier == 0
        assert placed[0].x == 416

    def test_layout_excludes_out_of_range_milestones(self):
        placed = wbsgen.layout_milestones([self.milestone(date(2026, 5, 30), '前', 0), self.milestone(date(2026, 6, 12), '中', 1), self.milestone(date(2026, 8, 4), '後', 2)], self.scale())
        assert [p.milestone.name for p in placed] == ['中']

    def test_layout_sorts_by_date_keeping_input_order_for_same_date(self):
        placed = wbsgen.layout_milestones([self.milestone(date(2026, 6, 30), '後', 0), self.milestone(date(2026, 6, 12), '同日A', 1), self.milestone(date(2026, 6, 12), '同日B', 2)], self.scale())
        assert [p.milestone.name for p in placed] == ['同日A', '同日B', '後']

    def test_layout_moves_overlapping_label_to_next_tier(self):
        placed = wbsgen.layout_milestones([self.milestone(date(2026, 6, 12), '要件確定', 0), self.milestone(date(2026, 6, 24), '設計凍結', 1), self.milestone(date(2026, 6, 26), '中間レビュー', 2), self.milestone(date(2026, 6, 29), 'QA開始', 3), self.milestone(date(2026, 7, 22), 'リリース判定', 4)], self.scale())
        assert [p.tier for p in placed] == [0, 0, 1, 0, 0]

    def test_layout_same_date_milestones_stack_tiers(self):
        placed = wbsgen.layout_milestones([self.milestone(date(2026, 6, 12), 'その1', 0), self.milestone(date(2026, 6, 12), 'その2', 1), self.milestone(date(2026, 6, 12), 'その3', 2)], self.scale())
        assert [p.tier for p in placed] == [0, 1, 2]

class TestAssigneePassthroughTests:

    def test_leaf_task_assignee_is_passed_through_to_computed_task(self):
        validation = wbsgen.ValidationResult()
        task = wbsgen.Task(id='1', name='実装', planned_start=date(2026, 6, 1), planned_duration=1, assignee='担当者A', source_index=0)
        computed = wbsgen.compute_task(task, validation, status_date=date(2026, 6, 10))
        assert computed.assignee == '担当者A'

    def test_parent_task_assignee_is_taken_from_source_task_not_children(self):
        validation = wbsgen.ValidationResult()
        root = wbsgen.Task(id='1', name='親', assignee='担当者C', source_index=0)
        child = wbsgen.Task(id='1.1', name='子', planned_start=date(2026, 6, 1), planned_duration=1, assignee='担当者A', source_index=1)
        root.children = [child]
        computed = wbsgen.compute_task(root, validation, status_date=date(2026, 6, 10))
        assert computed.assignee == '担当者C'
        assert computed.children[0].assignee == '担当者A'
