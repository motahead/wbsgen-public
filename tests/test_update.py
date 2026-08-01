from contextlib import nullcontext
import pytest
import copy
import tempfile
from pathlib import Path
from unittest import mock
from wbsgen.update import add_holiday, add_milestone, add_task, atomic_write_text, format_diff, format_json, merge_holidays, move_task, next_task_id, remove_holiday, remove_milestone, remove_task, show_holidays, show_display, show_project, show_milestones, show_task, update_holiday, update_display_analysis, update_display_layers, update_display_standard, update_milestone, update_project, update_task


def test_update_facade_reexports_domain_operations():
    from wbsgen import update
    from wbsgen import update_calendar, update_project_display, update_tasks

    assert update.add_task is update_tasks.add_task
    assert update.update_project is update_project_display.update_project
    assert update.update_display_standard is update_project_display.update_display_standard
    assert update.add_holiday is update_calendar.add_holiday
    assert update.add_milestone is update_calendar.add_milestone

class TestJsonUpdateTests:

    def base_data(self):
        return {'project': {'name': '個人開発'}, 'tasks': [{'id': '1', 'name': '既存タスク', 'progress': 0}]}

    def hierarchy_data(self):
        return {'project': {'name': '階層プロジェクト'}, 'tasks': [{'id': '1', 'name': '親タスク'}, {'id': '1.1', 'name': '子タスク'}, {'id': '1.1.1.1', 'name': 'ひ孫タスク'}, {'id': '2', 'name': '別タスク'}]}

    def test_show_task_returns_source_ancestors_and_descendants(self):
        result = show_task(self.hierarchy_data(), '1.1', direct=False, complement=False)
        assert result['scope'] == 'all'
        assert [item['id'] for item in result['parents']] == ['1']
        assert result['task']['id'] == '1.1'
        assert [item['id'] for item in result['children']] == ['1.1.1.1']

    def test_show_task_can_select_generated_task(self):
        result = show_task(self.hierarchy_data(), '1.1.1', direct=False, complement=True)
        assert result['task'] == {'id': '1.1.1', 'name': 'タスクを定義してください', 'generated': True, 'progress': 0}
        assert [item['id'] for item in result['parents']] == ['1', '1.1']
        assert [item['id'] for item in result['children']] == ['1.1.1.1']

    def test_show_task_direct_scope_returns_only_direct_parent_and_children(self):
        result = show_task(self.hierarchy_data(), '1.1.1.1', direct=True, complement=True)
        assert result['scope'] == 'direct'
        assert [item['id'] for item in result['parents']] == ['1.1.1']
        assert result['children'] == []

    def test_show_task_complement_preserves_source_child_order(self):
        data = {'project': {'name': '入力順プロジェクト'}, 'tasks': [{'id': '1', 'name': '親タスク'}, {'id': '1.2', 'name': '先に入力された子タスク'}, {'id': '1.1', 'name': '後に入力された子タスク'}]}
        direct_result = show_task(data, '1', direct=True, complement=True)
        all_result = show_task(data, '1', direct=False, complement=True)
        assert [item['id'] for item in direct_result['children']] == ['1.2', '1.1']
        assert [item['id'] for item in all_result['children']] == ['1.2', '1.1']

    def test_show_task_rejects_generated_and_unknown_ids_when_not_selected(self):
        with pytest.raises(ValueError, match='task id not found'):
            show_task(self.hierarchy_data(), '1.1.1', direct=False, complement=False)
        with pytest.raises(ValueError, match='task id not found'):
            show_task(self.hierarchy_data(), '9', direct=False, complement=True)

    def test_show_task_complement_adds_planned_end_without_overwriting_leaf_fields(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [
                {'id': '1', 'name': 'leaf', 'plannedStart': '2026-08-03', 'plannedDuration': 3, 'progress': 40},
            ],
        }
        result = show_task(data, '1', direct=False, complement=True)
        task = result['task']
        assert task['plannedStart'] == '2026-08-03'
        assert task['plannedDuration'] == 3
        assert task['progress'] == 40
        assert task['plannedEnd'] == '2026-08-05'

    def test_show_task_complement_fills_parent_aggregate_fields(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [
                {'id': '1', 'name': 'parent'},
                {'id': '1.1', 'name': 'child a', 'plannedStart': '2026-08-03', 'plannedDuration': 2, 'progress': 80},
                {'id': '1.2', 'name': 'child b', 'plannedStart': '2026-08-05', 'plannedDuration': 1, 'progress': 20},
            ],
        }
        result = show_task(data, '1', direct=False, complement=True)
        task = result['task']
        assert task == {
            'id': '1',
            'name': 'parent',
            'plannedStart': '2026-08-03',
            'plannedEnd': '2026-08-05',
            'plannedDuration': 3,
            'progress': 60,
        }

    def test_show_task_complement_fills_generated_task_computed_fields(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [
                {'id': '1.1', 'name': 'leaf', 'plannedStart': '2026-08-03', 'plannedDuration': 2, 'progress': 50},
            ],
        }
        result = show_task(data, '1', direct=False, complement=True)
        task = result['task']
        assert task['generated'] is True
        assert task['plannedStart'] == '2026-08-03'
        assert task['plannedEnd'] == '2026-08-04'
        assert task['plannedDuration'] == 2
        assert task['progress'] == 50

    def test_show_task_complement_omits_planned_end_when_not_computable(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [{'id': '1', 'name': 'unplanned'}],
        }
        result = show_task(data, '1', direct=False, complement=True)
        task = result['task']
        assert 'plannedEnd' not in task
        assert 'plannedStart' not in task
        assert 'plannedDuration' not in task
        # progress は未計画でも既定値0が計算されるため、原本に無いキーとして補完される。
        assert task['progress'] == 0

    def test_show_task_without_complement_never_adds_planned_end(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [
                {'id': '1', 'name': 'leaf', 'plannedStart': '2026-08-03', 'plannedDuration': 3},
            ],
        }
        result = show_task(data, '1', direct=False, complement=False)
        assert 'plannedEnd' not in result['task']

    def test_show_task_complement_applies_to_parents_and_children_entries(self):
        data = {
            'project': {'name': 'P', 'statusDate': '2026-08-01'},
            'tasks': [
                {'id': '1', 'name': 'parent'},
                {'id': '1.1', 'name': 'child', 'plannedStart': '2026-08-03', 'plannedDuration': 2, 'progress': 50},
            ],
        }
        result = show_task(data, '1.1', direct=False, complement=True)
        assert result['task']['plannedEnd'] == '2026-08-04'
        assert result['parents'][0]['id'] == '1'
        assert result['parents'][0]['plannedEnd'] == '2026-08-04'
        assert result['parents'][0]['plannedStart'] == '2026-08-03'

    def test_remove_task_requires_recursive_and_preserves_input_order(self):
        with pytest.raises(ValueError, match='--recursive'):
            remove_task(self.hierarchy_data(), '1', recursive=False)
        candidate, deleted = remove_task(self.hierarchy_data(), '1', recursive=True)
        assert [item['id'] for item in deleted] == ['1', '1.1', '1.1.1.1']
        assert [item['id'] for item in candidate['tasks']] == ['2']

    def test_remove_task_rejects_id_missing_from_source_json(self):
        with pytest.raises(ValueError, match='task id not found in source JSON: 1.1.1'):
            remove_task(self.hierarchy_data(), '1.1.1', recursive=True)

    def test_add_task_appends_all_supported_fields_in_standard_order(self):
        original = self.base_data()
        original_copy = copy.deepcopy(original)
        candidate, summary = add_task(original, '1.1', {'name': '調査', 'plannedStart': '2026-07-15', 'plannedDuration': 2, 'actualStart': '2026-07-15', 'actualEnd': '2026-07-16', 'progress': 100, 'issue': 88, 'comment': '完了', 'assignee': '担当者A'})
        assert original == original_copy
        assert summary == 'added task 1.1'
        assert candidate['tasks'][-1] == {'id': '1.1', 'name': '調査', 'plannedStart': '2026-07-15', 'plannedDuration': 2, 'actualStart': '2026-07-15', 'actualEnd': '2026-07-16', 'progress': 100, 'issue': 88, 'comment': '完了', 'assignee': '担当者A'}

    def test_next_task_id_uses_maximum_direct_numeric_sibling_without_filling_gaps(self):
        data = {
            'project': {'name': 'P'},
            'tasks': [
                {'id': '1', 'name': 'root'},
                {'id': '2', 'name': 'root'},
                {'id': '4', 'name': 'root'},
                {'id': '03', 'name': 'leading zero'},
                {'id': 'alpha', 'name': 'non-numeric'},
                {'id': '1.1', 'name': 'child'},
                {'id': '1.4', 'name': 'child'},
                {'id': '1.4.9', 'name': 'grandchild'},
                {'id': '1.x', 'name': 'non-numeric child'},
            ],
        }

        assert next_task_id(data, None) == '5'
        assert next_task_id(data, '1') == '1.5'
        assert next_task_id({'project': {'name': 'P'}, 'tasks': [{'id': '1', 'name': 'root'}]}, '1') == '1.1'

    def test_next_task_id_rejects_a_missing_parent_and_invalid_tasks_shape(self):
        data = {'project': {'name': 'P'}, 'tasks': [{'id': '1', 'name': 'root'}]}

        with pytest.raises(ValueError, match='parent task id not found: 9'):
            next_task_id(data, '9')
        with pytest.raises(ValueError, match='tasks must be an array'):
            next_task_id({'project': {}, 'tasks': {}}, None)

    def test_update_task_changes_values_and_clears_multiple_optional_fields(self):
        original = self.base_data()
        original['tasks'][0].update({'actualStart': '2026-07-01', 'actualEnd': '2026-07-02', 'comment': 'old', 'assignee': '担当者B'})
        candidate, summary = update_task(original, '1', {'progress': 0}, {'actual-start', 'actual-end', 'comment', 'assignee'})
        assert summary == 'updated task 1'
        assert candidate['tasks'][0] == {'id': '1', 'name': '既存タスク', 'progress': 0}

    def test_update_project_changes_and_clears_optional_fields(self):
        original = self.base_data()
        original['project'].update({'startDate': '2026-07-01', 'issueBaseUrl': 'https://github.com/your_account/your_repo/issues/'})
        candidate, summary = update_project(original, {'statusDate': '2026-07-15'}, {'start-date', 'issue-base-url'})
        assert summary == 'updated project'
        assert candidate['project'] == {'name': '個人開発', 'statusDate': '2026-07-15'}

    def test_add_and_update_reject_wrong_target_state_and_conflicting_clear(self):
        data = self.base_data()
        with pytest.raises(ValueError, match='task id already exists: 1'):
            add_task(data, '1', {'name': '重複'})
        with pytest.raises(ValueError, match='task id not found: 9'):
            update_task(data, '9', {'progress': 10}, set())
        with pytest.raises(ValueError, match='cannot both set and clear: progress'):
            update_task(data, '1', {'progress': 10}, {'progress'})

    def test_update_helpers_reject_invalid_document_shapes_and_empty_changes(self):
        with pytest.raises(ValueError, match='project must be an object'):
            update_project({'project': [], 'tasks': []}, {'name': 'P'}, set())
        with pytest.raises(ValueError, match='tasks must be an array'):
            add_task({'project': {}, 'tasks': {}}, '1', {'name': 'P'})
        with pytest.raises(ValueError, match='invalid field for --clear: name'):
            update_task(self.base_data(), '1', {}, {'name'})
        with pytest.raises(ValueError, match='at least one field'):
            update_project(self.base_data(), {}, set())

    def test_format_json_diff_and_atomic_write_are_normalized_and_safe(self):
        before = '{"project":{"name":"旧"},"tasks":[]}\n'
        after = format_json({'project': {'name': '新'}, 'tasks': []})
        assert after == '{\n  "project": {\n    "name": "新"\n  },\n  "tasks": []\n}\n'
        assert '-{"project"' in format_diff(before, after, Path('project.json'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'project.json'
            path.write_text(before, encoding='utf-8')
            atomic_write_text(path, after)
            assert path.read_text(encoding='utf-8') == after

    def test_atomic_write_keeps_original_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'project.json'
            path.write_text('before\n', encoding='utf-8')
            with mock.patch('wbsgen.source.os.replace', side_effect=OSError('disk error')):
                with pytest.raises(ValueError, match='failed to update JSON file'):
                    atomic_write_text(path, 'after\n')
            assert path.read_text(encoding='utf-8') == 'before\n'

class TestMilestoneUpdateTests:

    def base_data(self):
        return {'project': {'name': '個人開発'}, 'milestones': [{'date': '2026-06-30', 'name': 'リリース判定'}, {'date': '2026-06-12', 'name': '中間レビュー'}, {'date': '2026-06-12', 'name': '同名', 'note': 'A'}], 'tasks': [{'id': '1', 'name': '既存タスク', 'progress': 0}]}

    def test_add_milestone_appends_entry(self):
        data = {'project': {'name': 'P'}, 'tasks': []}
        candidate, summary = add_milestone(data, '2026-07-01', 'QA開始')
        assert candidate['milestones'] == [{'date': '2026-07-01', 'name': 'QA開始'}]
        assert 'milestones' not in data
        assert 'QA開始' in summary

    def test_add_milestone_rejects_exact_duplicate(self):
        with pytest.raises(ValueError):
            add_milestone(self.base_data(), '2026-06-12', '中間レビュー')

    def test_update_milestone_by_name(self):
        candidate, _ = update_milestone(self.base_data(), '中間レビュー', None, '2026-06-19', None)
        assert candidate['milestones'][1]['date'] == '2026-06-19'

    def test_update_milestone_requires_new_value(self):
        with pytest.raises(ValueError):
            update_milestone(self.base_data(), '中間レビュー', None, None, None)

    def test_update_milestone_rejects_unknown_name(self):
        with pytest.raises(ValueError):
            update_milestone(self.base_data(), '存在しない', None, '2026-06-19', None)

    def test_update_milestone_rejects_ambiguous_name(self):
        data = self.base_data()
        data['milestones'].append({'date': '2026-07-01', 'name': '同名'})
        with pytest.raises(ValueError):
            update_milestone(data, '同名', None, None, '改名')
        candidate, _ = update_milestone(data, '同名', '2026-07-01', None, '改名')
        assert candidate['milestones'][3]['name'] == '改名'

    def test_remove_milestone_by_name_and_date(self):
        candidate, _ = remove_milestone(self.base_data(), '同名', '2026-06-12')
        assert len(candidate['milestones']) == 2

    def test_show_milestones_sorted_by_date(self):
        milestones = show_milestones(self.base_data())
        assert [item['name'] for item in milestones] == ['中間レビュー', '同名', 'リリース判定']

    def test_show_milestones_empty_when_missing(self):
        assert show_milestones({'project': {'name': 'P'}, 'tasks': []}) == []

class TestHolidayUpdateTests:

    def base_data(self):
        return {'project': {'name': '個人開発'}, 'holidays': [{'date': '2026-07-20', 'name': '海の日'}, {'date': '2026-06-08', 'name': '会社休日'}], 'tasks': []}

    def test_add_holiday_supports_optional_name_without_mutating_input(self):
        original = {'project': {'name': 'P'}, 'tasks': []}
        original_copy = copy.deepcopy(original)
        named, named_summary = add_holiday(original, '2026-08-10', '山の日')
        unnamed, unnamed_summary = add_holiday(original, '2026-08-11', None)
        assert original == original_copy
        assert named['holidays'] == [{'date': '2026-08-10', 'name': '山の日'}]
        assert unnamed['holidays'] == [{'date': '2026-08-11'}]
        assert named_summary == 'added holiday 2026-08-10'
        assert unnamed_summary == 'added holiday 2026-08-11'

    def test_add_holiday_rejects_duplicate_date(self):
        with pytest.raises(ValueError, match='holiday already exists: 2026-07-20'):
            add_holiday(self.base_data(), '2026-07-20', '別名')

    def test_update_holiday_sets_or_clears_name_without_mutating_input(self):
        original = self.base_data()
        original_copy = copy.deepcopy(original)
        renamed, renamed_summary = update_holiday(original, '2026-07-20', '祝日', False)
        cleared, cleared_summary = update_holiday(original, '2026-07-20', None, True)
        assert original == original_copy
        assert renamed['holidays'][0] == {'date': '2026-07-20', 'name': '祝日'}
        assert cleared['holidays'][0] == {'date': '2026-07-20'}
        assert renamed_summary == 'updated holiday 2026-07-20'
        assert cleared_summary == 'updated holiday 2026-07-20'

    def test_update_holiday_requires_one_non_conflicting_change(self):
        with pytest.raises(ValueError, match='set or clear holiday name'):
            update_holiday(self.base_data(), '2026-07-20', None, False)
        with pytest.raises(ValueError, match='cannot both set and clear: name'):
            update_holiday(self.base_data(), '2026-07-20', '祝日', True)

    def test_update_and_remove_reject_unknown_date(self):
        with pytest.raises(ValueError, match='holiday not found: 2026-12-31'):
            update_holiday(self.base_data(), '2026-12-31', '休業日', False)
        with pytest.raises(ValueError, match='holiday not found: 2026-12-31'):
            remove_holiday(self.base_data(), '2026-12-31')

    def test_remove_holiday_deletes_matching_date(self):
        candidate, summary = remove_holiday(self.base_data(), '2026-06-08')
        assert candidate['holidays'] == [{'date': '2026-07-20', 'name': '海の日'}]
        assert summary == 'removed holiday 2026-06-08'

    def test_show_holidays_returns_sorted_copy_and_empty_for_missing_key(self):
        original = self.base_data()
        shown = show_holidays(original)
        assert [item['date'] for item in shown] == ['2026-06-08', '2026-07-20']
        shown[0]['name'] = '変更'
        assert original['holidays'][1]['name'] == '会社休日'
        assert show_holidays({'project': {'name': 'P'}, 'tasks': []}) == []

    def test_holiday_helpers_reject_non_array_holidays(self):
        data = {'project': {'name': 'P'}, 'holidays': {}, 'tasks': []}
        for operation in (lambda: add_holiday(data, '2026-08-10', '山の日'), lambda: update_holiday(data, '2026-08-10', '山の日', False), lambda: remove_holiday(data, '2026-08-10'), lambda: show_holidays(data)):
            with nullcontext():
                with pytest.raises(ValueError, match='holidays must be an array'):
                    operation()

    def test_merge_holidays_preserves_input_and_adds_or_replaces_by_date(self):
        original = self.base_data()
        original_copy = copy.deepcopy(original)
        candidate, summary = merge_holidays(original, {'holidays': [{'date': '2026-07-20', 'name': '祝日名を更新'}, {'date': '2026-08-11', 'name': '山の日'}]})
        assert original == original_copy
        assert candidate['holidays'] == [{'date': '2026-07-20', 'name': '祝日名を更新'}, {'date': '2026-06-08', 'name': '会社休日'}, {'date': '2026-08-11', 'name': '山の日'}]
        assert summary == 'merged holidays'

    def test_merge_holidays_same_name_is_a_non_mutating_no_op(self):
        original = self.base_data()
        candidate, _ = merge_holidays(original, {'holidays': [{'date': '2026-07-20', 'name': '海の日'}]})
        assert candidate == original
        assert candidate is not original

    def test_merge_holidays_rejects_invalid_supplement_before_returning_candidate(self):
        invalid_supplements = ([], {'holidays': {}}, {'holidays': ['not-an-object']}, {'holidays': [{'date': 'not-a-date'}]}, {'holidays': [{'date': '2026-08-11'}, {'date': '2026-08-11', 'name': 'duplicate'}]})
        for supplemental in invalid_supplements:
            with nullcontext():
                with pytest.raises(ValueError, match='invalid supplemental holidays'):
                    merge_holidays(self.base_data(), supplemental)

    def test_update_holiday_can_move_date_and_rejects_an_existing_destination(self):
        candidate, _ = update_holiday(self.base_data(), '2026-07-20', new_date='2026-07-21')
        assert candidate['holidays'][0]['date'] == '2026-07-21'
        with pytest.raises(ValueError, match='holiday already exists: 2026-06-08'):
            update_holiday(self.base_data(), '2026-07-20', new_date='2026-06-08')

class TestHtmlSourceUpdateTests:

    def test_move_task_updates_source_descendants_without_mutating_input(self):
        original = {'project': {'name': 'P'}, 'tasks': [{'id': '2.3', 'name': '親'}, {'id': '2.3.1', 'name': '子'}, {'id': '1.4', 'name': '既存'}]}
        candidate, _ = move_task(original, '2.3', '3.1')
        assert [task['id'] for task in candidate['tasks']] == ['3.1', '3.1.1', '1.4']
        assert original['tasks'][0]['id'] == '2.3'
        with pytest.raises(ValueError, match='below itself'):
            move_task(original, '2.3', '2.3.1')

    def test_move_task_rejects_same_missing_and_colliding_ids(self):
        data = {'project': {'name': 'P'}, 'tasks': [{'id': '1', 'name': 'one'}, {'id': '2', 'name': 'two'}]}
        with pytest.raises(ValueError, match='must differ'):
            move_task(data, '1', '1')
        with pytest.raises(ValueError, match='not found'):
            move_task(data, '9', '3')
        with pytest.raises(ValueError, match='already exists: 2'):
            move_task(data, '1', '2')

    def test_move_task_ignores_non_task_entries_and_holiday_merge_keeps_unnamed_items(self):
        data = {'project': {'name': 'P'}, 'tasks': [None, {'id': '1', 'name': 'one'}]}
        candidate, _ = move_task(data, '1', '2')
        assert candidate['tasks'] == [None, {'id': '2', 'name': 'one'}]
        merged, _ = merge_holidays({'project': {'name': 'P'}, 'tasks': []}, {'holidays': [{'date': '2026-08-11'}]})
        assert merged['holidays'] == [{'date': '2026-08-11'}]

    def test_show_generated_task_handles_sparse_model_ancestors_and_generated_children(self):
        source_child = __import__('wbsgen').Task(id='1.1', name='source', source_index=0)
        generated_root = __import__('wbsgen').Task(id='1', name='generated', generated=True, children=[source_child])
        data = {'project': {'name': 'P'}, 'tasks': [{'id': '1.1', 'name': 'source'}]}
        with mock.patch('wbsgen.update_tasks._all_model_tasks', return_value={'1': generated_root, '1.1': source_child}):
            generated = show_task(data, '1', direct=False, complement=True)
        with mock.patch('wbsgen.update_tasks._all_model_tasks', return_value={'1.1': source_child}):
            sparse = show_task(data, '1.1', direct=False, complement=True)
        assert generated['task']['generated'] == True
        assert [item['id'] for item in generated['children']] == ['1.1']
        assert sparse['parents'] == []

    def test_show_generated_descendant_uses_first_source_child_order(self):
        task_type = __import__('wbsgen').Task
        source_root = task_type(id='1', name='root', source_index=0)
        source_leaf = task_type(id='1.1.1', name='leaf', source_index=1)
        generated_child = task_type(id='1.1', name='generated', generated=True, children=[source_leaf])
        source_root.children = [generated_child]
        data = {'project': {'name': 'P'}, 'tasks': [{'id': '1', 'name': 'root'}, {'id': '1.1.1', 'name': 'leaf'}]}
        with mock.patch('wbsgen.update_tasks._all_model_tasks', return_value={'1': source_root, '1.1': generated_child, '1.1.1': source_leaf}):
            result = show_task(data, '1', direct=False, complement=True)
        assert [item['id'] for item in result['children']] == ['1.1', '1.1.1']

    def test_show_generated_descendant_reuses_cached_source_index(self):
        task_type = __import__('wbsgen').Task
        source_root = task_type(id='1', name='root', source_index=0)
        source_leaf = task_type(id='1.1.1', name='leaf', source_index=1)
        generated_child = task_type(id='1.1', name='generated', generated=True, children=[source_leaf])
        source_root.children = [generated_child, generated_child]
        data = {'project': {'name': 'P'}, 'tasks': [{'id': '1', 'name': 'root'}, {'id': '1.1.1', 'name': 'leaf'}]}
        with mock.patch('wbsgen.update_tasks._all_model_tasks', return_value={'1': source_root, '1.1': generated_child, '1.1.1': source_leaf}):
            result = show_task(data, '1', direct=True, complement=True)
        assert [item['id'] for item in result['children']] == ['1.1', '1.1']

    def test_show_project_and_display_preserve_stored_values(self):
        original = {'project': {'name': 'P'}, 'display': {'standard': {'columns': {'visible': ['*']}}}, 'tasks': []}
        assert show_project(original) == {'name': 'P'}
        assert show_display(original) == {'standard': {'columns': {'visible': ['*']}}}
        candidate, _ = update_display_layers(original, {'visible': ['*', '-tooltip']}, set())
        assert candidate.get('display') == {'standard': {'columns': {'visible': ['*']}}, 'layers': {'visible': ['*', '-tooltip']}}
        assert show_display({'project': {'name': 'P'}, 'tasks': []}) == {}

    def test_display_and_milestone_helpers_reject_invalid_shapes_and_remove_empty_display(self):
        with pytest.raises(ValueError, match='display must be an object'):
            show_display({'project': {}, 'tasks': [], 'display': []})
        candidate, _ = update_display_standard({'project': {}, 'tasks': [], 'display': {'standard': {'columns': {'visible': ['*']}}}}, {}, {'visible'})
        assert 'display' not in candidate
        with pytest.raises(ValueError, match='milestones must be an array'):
            show_milestones({'project': {}, 'tasks': [], 'milestones': {}})

    def test_update_display_standard_sets_and_clears_width_and_order(self):
        data = {'project': {'name': 'P'}, 'tasks': []}
        candidate, _ = update_display_standard(data, {'width': {'name': 300, 'comment': 200}, 'order': ['assignee', 'issue']}, set())
        assert candidate['display']['standard']['columns'] == {'width': {'name': 300, 'comment': 200}, 'order': ['assignee', 'issue']}
        cleared, _ = update_display_standard(candidate, {}, {'width', 'order'})
        assert 'display' not in cleared

    def test_update_display_analysis_sets_and_clears_order(self):
        data = {'project': {'name': 'P'}, 'tasks': []}
        candidate, _ = update_display_analysis(data, {'order': ['delta', 'pace']}, set())
        assert candidate['display']['analysis']['columns'] == {'order': ['delta', 'pace']}
        cleared, _ = update_display_analysis(candidate, {}, {'order'})
        assert 'display' not in cleared
