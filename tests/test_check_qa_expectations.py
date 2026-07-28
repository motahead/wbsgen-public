
class TestDeriveExpectationsTests:

    def test_derive_expected_warning_ids_includes_unplanned_weekend_and_holiday(self):
        from tools import check_qa_expectations
        data = {'holidays': [{'date': '2026-08-13', 'name': '休'}], 'tasks': [{'id': '1', 'name': 'phase'}, {'id': '1.1', 'name': 'a', 'assignee': 'x', 'progress': 0}, {'id': '1.2', 'name': 'b', 'assignee': 'x', 'plannedStart': '2026-08-08', 'plannedDuration': 2}, {'id': '1.3', 'name': 'c', 'assignee': 'x', 'plannedStart': '2026-08-13', 'plannedDuration': 1}, {'id': '1.4', 'name': 'd', 'assignee': 'x', 'plannedStart': '2026-08-10', 'plannedDuration': 3}]}
        expected = check_qa_expectations.derive_expected_warning_ids(data)
        assert expected == {'1.1', '1.2', '1.3'}

    def test_derive_expected_leaf_plan_bar_and_unplanned_ids(self):
        from tools import check_qa_expectations
        data = {'tasks': [{'id': '1', 'name': 'phase'}, {'id': '1.1', 'name': 'a', 'assignee': 'x', 'progress': 0}, {'id': '1.2', 'name': 'b', 'assignee': 'x', 'plannedStart': '2026-08-10', 'plannedDuration': 2}]}
        assert check_qa_expectations.derive_expected_leaf_plan_bar_ids(data) == {'1.2'}
        assert check_qa_expectations.derive_expected_leaf_unplanned_ids(data) == {'1.1'}

    def test_compare_expectations_reports_warning_plan_bar_and_count_mismatches(self):
        from tools import check_qa_expectations
        data = {'milestones': [{'date': '2026-08-01', 'name': 'm'}], 'holidays': [], 'tasks': [{'id': '1', 'name': 'phase'}, {'id': '1.1', 'name': 'a', 'assignee': 'x', 'plannedStart': '2026-08-08', 'plannedDuration': 2}]}
        dom_state = {'rowCount': 1, 'warningRowIds': [], 'planBarIds': ['1'], 'milestoneCount': 0}
        differences = check_qa_expectations.compare_expectations(data, dom_state)
        joined = '\n'.join(differences)
        assert 'warning-row ids differ' in joined
        assert 'missing plan bars' in joined
        assert 'milestone marker count differs' in joined
        assert 'task row count differs' in joined

    def test_compare_expectations_reports_unexpected_plan_bar_for_unplanned_task(self):
        from tools import check_qa_expectations
        data = {'milestones': [], 'holidays': [], 'tasks': [{'id': '1', 'name': 'phase'}, {'id': '1.1', 'name': 'a', 'assignee': 'x', 'progress': 0}]}
        dom_state = {'rowCount': 2, 'warningRowIds': ['1.1'], 'planBarIds': ['1', '1.1'], 'milestoneCount': 0}
        differences = check_qa_expectations.compare_expectations(data, dom_state)
        assert any(('unexpectedly have plan bars' in diff for diff in differences))

    def test_compare_expectations_returns_empty_list_when_matching(self):
        from tools import check_qa_expectations
        data = {'milestones': [], 'holidays': [], 'tasks': [{'id': '1', 'name': 'phase'}, {'id': '1.1', 'name': 'a', 'assignee': 'x', 'plannedStart': '2026-08-10', 'plannedDuration': 2}]}
        dom_state = {'rowCount': 2, 'warningRowIds': [], 'planBarIds': ['1', '1.1'], 'milestoneCount': 0}
        assert check_qa_expectations.compare_expectations(data, dom_state) == []
import io
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

class TestCheckQaExpectationsCliTests:

    def test_parse_args_requires_html_and_input_json(self):
        from tools import check_qa_expectations
        args = check_qa_expectations.parse_args(['--html', 'output/qa.html', '--input-json', 'output/qa.json'])
        assert args.html == Path('output/qa.html')
        assert args.input_json == Path('output/qa.json')

    def test_capture_dom_state_returns_playwright_evaluate_result(self):
        from tools import check_qa_expectations

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.wait_for_selector = mock.Mock()
                self.evaluate = mock.Mock(return_value={'rowCount': 2, 'warningRowIds': ['1.1'], 'planBarIds': ['1', '1.1'], 'milestoneCount': 1})

        class FakeBrowser:

            def __init__(self, page):
                self.page = page
                self.closed = False

            def new_page(self, **_kwargs):
                return self.page

            def close(self):
                self.closed = True

        class FakePlaywrightContext:

            def __init__(self, browser):
                self.browser = browser

            def __enter__(self):
                return SimpleNamespace(chromium=SimpleNamespace(launch=mock.Mock(return_value=self.browser)))

            def __exit__(self, _exc_type, _exc, _traceback):
                return False
        page = FakePage()
        browser = FakeBrowser(page)
        sync_api = SimpleNamespace(sync_playwright=mock.Mock(return_value=FakePlaywrightContext(browser)))
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}):
            result = check_qa_expectations.capture_dom_state(Path('qa.html'))
        assert result['rowCount'] == 2
        assert result['warningRowIds'] == ['1.1']
        page.wait_for_selector.assert_called_once_with('.left-rows .wbs-row', timeout=5000)
        assert browser.closed

    def test_run_returns_1_and_prints_differences_when_expectations_mismatch(self):
        from tools import check_qa_expectations
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            html_path = tmp / 'qa.html'
            json_path = tmp / 'qa.json'
            html_path.write_text('<!doctype html>', encoding='utf-8')
            json_path.write_text('{"tasks": [{"id": "1", "name": "phase"}], "holidays": [], "milestones": []}', encoding='utf-8')
            args = check_qa_expectations.parse_args(['--html', str(html_path), '--input-json', str(json_path)])
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.dict('os.environ', {'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'}, clear=True), mock.patch.object(check_qa_expectations, 'capture_dom_state', return_value={'rowCount': 2, 'warningRowIds': [], 'planBarIds': ['1'], 'milestoneCount': 0}):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = check_qa_expectations.run(args)
        assert exit_code == 1
        assert 'differences found' in stderr.getvalue()
        assert 'task row count differs' in stderr.getvalue()

    def test_run_returns_0_when_expectations_match(self):
        from tools import check_qa_expectations
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            html_path = tmp / 'qa.html'
            json_path = tmp / 'qa.json'
            html_path.write_text('<!doctype html>', encoding='utf-8')
            json_path.write_text('{"tasks": [{"id": "1", "name": "phase"}], "holidays": [], "milestones": []}', encoding='utf-8')
            args = check_qa_expectations.parse_args(['--html', str(html_path), '--input-json', str(json_path)])
            stdout = io.StringIO()
            with mock.patch.dict('os.environ', {'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'}, clear=True), mock.patch.object(check_qa_expectations, 'capture_dom_state', return_value={'rowCount': 1, 'warningRowIds': [], 'planBarIds': ['1'], 'milestoneCount': 0}):
                with redirect_stdout(stdout):
                    exit_code = check_qa_expectations.run(args)
        assert exit_code == 0
        assert 'no differences' in stdout.getvalue()

    def test_main_writes_errors_to_stderr_when_file_missing(self):
        from tools import check_qa_expectations
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = check_qa_expectations.main(['--html', 'missing.html', '--input-json', 'missing.json'])
        assert exit_code == 1
        assert 'check_qa_expectations: error:' in stderr.getvalue()
        assert 'missing.html' in stderr.getvalue()
