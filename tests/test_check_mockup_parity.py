import io
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

def make_view_state(**overrides):
    base = {'taskRowCount': 1, 'taskRows': [{'taskId': 'T1', 'name': 'Task 1', 'assignee': 'Alice', 'comment': '-', 'progressText': '50%', 'progressClass': 'progress-pill', 'deltaText': '-', 'deltaClass': 'wbs-cell right analysis-only', 'delayText': '-', 'paceText': '-', 'paceClass': 'wbs-cell right analysis-only'}], 'headerToggleOrder': ['warning-toggle', 'holiday-toggle'], 'commentHeadTextAlign': 'left', 'firstPlanBarRect': {'left': '10px', 'top': '0px', 'width': '40px', 'height': '18px', 'delayState': None}, 'analysisOnlyVisible': False, 'columnVisibilityControlsDisabled': False}
    base.update(overrides)
    return base

class TestCheckMockupParityToolTests:

    def test_parse_args_requires_generated_and_reference_html(self):
        from tools import check_mockup_parity
        args = check_mockup_parity.parse_args(['--generated-html', 'output/visual-test.html', '--reference-html', 'mockups/visual-reference.html'])
        assert args.generated_html == Path('output/visual-test.html')
        assert args.reference_html == Path('mockups/visual-reference.html')
        assert args.viewport == '1360x900'

    def test_diff_states_reports_row_count_mismatch(self):
        from tools import check_mockup_parity
        generated = {'default': make_view_state(taskRowCount=2, taskRows=[make_view_state()['taskRows'][0]] * 2), 'analysis': make_view_state(taskRowCount=2, taskRows=[make_view_state()['taskRows'][0]] * 2)}
        reference = {'default': make_view_state(), 'analysis': make_view_state(taskRowCount=2, taskRows=[make_view_state()['taskRows'][0]] * 2)}
        differences = check_mockup_parity.diff_states(generated, reference)
        assert len(differences) == 1
        assert '[default]' in differences[0]
        assert 'task row count differs' in differences[0]

    def test_diff_states_reports_zero_rows_on_both_sides_as_a_difference(self):
        from tools import check_mockup_parity
        empty_view = make_view_state(taskRowCount=0, taskRows=[])
        generated = {'default': empty_view, 'analysis': empty_view}
        reference = {'default': empty_view, 'analysis': empty_view}
        differences = check_mockup_parity.diff_states(generated, reference)
        assert len(differences) == 2
        assert all(('0 task rows' in diff for diff in differences))

    def test_diff_states_reports_task_row_content_and_style_differences(self):
        from tools import check_mockup_parity
        generated_row = dict(make_view_state()['taskRows'][0], progressClass='progress-pill delayed')
        reference_row = dict(make_view_state()['taskRows'][0], assignee='Bob')
        generated_view = make_view_state(taskRows=[generated_row], headerToggleOrder=['warning-toggle', 'holiday-toggle'], commentHeadTextAlign='left')
        reference_view = make_view_state(taskRows=[reference_row], headerToggleOrder=['holiday-toggle', 'warning-toggle'], commentHeadTextAlign='center')
        generated = {'default': generated_view, 'analysis': generated_view}
        reference = {'default': reference_view, 'analysis': reference_view}
        differences = check_mockup_parity.diff_states(generated, reference)
        joined = '\n'.join(differences)
        assert 'task row 0 differs' in joined
        assert 'header toggle order differs' in joined
        assert 'comment head text-align differs' in joined

    def test_diff_states_reports_analysis_only_visibility_and_control_state_differences(self):
        from tools import check_mockup_parity
        generated_analysis = make_view_state(analysisOnlyVisible=True, columnVisibilityControlsDisabled=True)
        reference_analysis = make_view_state(analysisOnlyVisible=False, columnVisibilityControlsDisabled=False)
        generated = {'default': make_view_state(), 'analysis': generated_analysis}
        reference = {'default': make_view_state(), 'analysis': reference_analysis}
        differences = check_mockup_parity.diff_states(generated, reference)
        joined = '\n'.join(differences)
        assert '[analysis] analysis-only column visibility differs' in joined
        assert '[analysis] column visibility controls disabled-state differs' in joined

    def test_diff_states_returns_empty_list_when_states_match(self):
        from tools import check_mockup_parity
        state = {'default': make_view_state(), 'analysis': make_view_state()}
        differences = check_mockup_parity.diff_states(state, state)
        assert differences == []

    def test_capture_view_states_applies_default_then_analysis_view_state(self):
        from tools import check_mockup_parity

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.wait_for_selector = mock.Mock()
                self.wait_for_function = mock.Mock()
                self.evaluate = mock.Mock(side_effect=[make_view_state(), make_view_state(analysisOnlyVisible=True, columnVisibilityControlsDisabled=True)])

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
        applied_states = []
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}), mock.patch.object(check_mockup_parity, 'apply_default_view_state', side_effect=lambda p: applied_states.append('default')), mock.patch.object(check_mockup_parity, 'apply_analysis_view_state', side_effect=lambda p: applied_states.append('analysis')):
            result = check_mockup_parity.capture_view_states(Path('sample.html'), check_mockup_parity.Viewport(width=1360, height=900))
        assert applied_states == ['default', 'analysis']
        assert 'default' in result
        assert 'analysis' in result
        assert not result['default']['analysisOnlyVisible']
        assert result['analysis']['analysisOnlyVisible']
        page.wait_for_selector.assert_called_once_with('.left-rows .wbs-row', timeout=5000)
        page.wait_for_function.assert_called_once_with("document.documentElement.dataset.wbsView === 'analysis'", timeout=5000)
        assert browser.closed

    def test_run_returns_1_and_prints_differences_when_states_differ(self):
        from tools import check_mockup_parity
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            generated_html = tmp / 'visual-test.html'
            reference_html = tmp / 'visual-reference.html'
            generated_html.write_text('<!doctype html><title>generated</title>', encoding='utf-8')
            reference_html.write_text('<!doctype html><title>reference</title>', encoding='utf-8')
            args = check_mockup_parity.parse_args(['--generated-html', str(generated_html), '--reference-html', str(reference_html)])
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch.dict('os.environ', {'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'}, clear=True), mock.patch.object(check_mockup_parity, 'capture_view_states', side_effect=[{'default': make_view_state(), 'analysis': make_view_state()}, {'default': make_view_state(taskRows=[dict(make_view_state()['taskRows'][0], assignee='Bob')]), 'analysis': make_view_state(taskRows=[dict(make_view_state()['taskRows'][0], assignee='Bob')])}]), mock.patch.object(check_mockup_parity, 'capture_pane_boundary_states', return_value={'standard-initial': {'leftPaneRight': 640.0, 'dividerX': 637.0}}):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = check_mockup_parity.run(args)
        assert exit_code == 1
        assert 'differences found' in stderr.getvalue()
        assert 'task row 0 differs' in stderr.getvalue()

    def test_run_returns_0_when_states_match(self):
        from tools import check_mockup_parity
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            generated_html = tmp / 'visual-test.html'
            reference_html = tmp / 'visual-reference.html'
            generated_html.write_text('<!doctype html><title>generated</title>', encoding='utf-8')
            reference_html.write_text('<!doctype html><title>reference</title>', encoding='utf-8')
            args = check_mockup_parity.parse_args(['--generated-html', str(generated_html), '--reference-html', str(reference_html)])
            same_state = {'default': make_view_state(), 'analysis': make_view_state()}
            stdout = io.StringIO()
            with mock.patch.dict('os.environ', {'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'}, clear=True), mock.patch.object(check_mockup_parity, 'capture_view_states', return_value=same_state), mock.patch.object(check_mockup_parity, 'capture_pane_boundary_states', return_value={'standard-initial': {'leftPaneRight': 640.0, 'dividerX': 637.0}}):
                with redirect_stdout(stdout):
                    exit_code = check_mockup_parity.run(args)
        assert exit_code == 0
        assert 'no differences' in stdout.getvalue()

    def test_main_writes_errors_to_stderr_when_file_missing(self):
        from tools import check_mockup_parity
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = check_mockup_parity.main(['--generated-html', 'missing-generated.html', '--reference-html', 'missing-reference.html'])
        assert exit_code == 1
        assert 'check_mockup_parity: error:' in stderr.getvalue()
        assert 'missing-generated.html' in stderr.getvalue()
