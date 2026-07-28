from contextlib import nullcontext
import io
import json
import tempfile
from contextlib import redirect_stderr
from datetime import date, timedelta
from pathlib import Path

class TestGenerateQaDataTests:

    def test_same_seed_and_today_produce_identical_output(self):
        from tools import generate_qa_data
        today = date(2026, 7, 24)
        first = generate_qa_data.generate_project(seed=42, today=today)
        second = generate_qa_data.generate_project(seed=42, today=today)
        assert first == second

    def test_generated_project_includes_required_variety(self):
        from tools import generate_qa_data
        today = date(2026, 7, 24)
        for seed in range(10):
            data = generate_qa_data.generate_project(seed=seed, today=today)
            leaf_tasks = [t for t in data['tasks'] if 'assignee' in t]
            planned = [t for t in leaf_tasks if 'plannedStart' in t]
            holiday_dates = {h['date'] for h in data['holidays']}
            with nullcontext():
                assert any(('plannedStart' not in t for t in leaf_tasks))
                assert any((date.fromisoformat(t['plannedStart']).weekday() >= 5 for t in planned))
                assert any((t['plannedStart'] in holiday_dates for t in planned))
                assert len({t['assignee'] for t in leaf_tasks}) >= 2, 'not enough assignees'
                assert any(('.' in t['id'] for t in data['tasks']))
                assert len(data['holidays']) > 0
                assert len(data['milestones']) == 3
                start = date.fromisoformat(data['project']['startDate'])
                end = date.fromisoformat(data['project']['endDate'])
                assert (end - start).days <= 62, 'project span exceeds ~2 months'
                for task in data['tasks']:
                    if 'plannedStart' in task and 'plannedDuration' in task:
                        planned_start = date.fromisoformat(task['plannedStart'])
                        planned_end = planned_start + timedelta(days=task['plannedDuration'] - 1)
                        assert planned_start >= start
                        assert planned_end <= end
                    if 'actualStart' in task:
                        assert date.fromisoformat(task['actualStart']) >= start
                    if 'actualEnd' in task:
                        assert date.fromisoformat(task['actualEnd']) <= end

    def test_parse_args_requires_output_and_accepts_seed(self):
        from tools import generate_qa_data
        args = generate_qa_data.parse_args(['-o', '/tmp/qa-data.json', '--seed', '1'])
        assert args.output == Path('/tmp/qa-data.json')
        assert args.seed == 1

    def test_parse_args_seed_defaults_to_none(self):
        from tools import generate_qa_data
        args = generate_qa_data.parse_args(['-o', '/tmp/qa-data.json'])
        assert args.seed is None

    def test_run_writes_seed_to_stderr_and_json_to_output(self):
        from tools import generate_qa_data
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / 'qa-data.json'
            args = generate_qa_data.parse_args(['-o', str(output), '--seed', '99'])
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = generate_qa_data.run(args)
            assert exit_code == 0
            assert 'seed=99' in stderr.getvalue()
            data = json.loads(output.read_text(encoding='utf-8'))
            assert 'tasks' in data
            assert 'project' in data
