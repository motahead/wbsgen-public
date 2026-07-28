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

class TestVisualScreenshotToolTests:

    def test_parse_args_sets_default_viewport_and_output_dir(self):
        from tools import visual_screenshot
        args = visual_screenshot.parse_args(['--generated-html', 'output/visual-test.html', '--output-dir', 'output'])
        assert args.generated_html == Path('output/visual-test.html')
        assert args.output_dir == Path('output')
        assert args.viewport == '1360x900'
        assert args.input_json == Path('examples/visual-test.json')

    def test_screenshot_html_closes_browser_when_page_navigation_fails(self):
        from tools import visual_screenshot

        class FakeBrowser:

            def __init__(self):
                self.closed = False

            def new_page(self, **_kwargs):
                return SimpleNamespace(goto=mock.Mock(side_effect=RuntimeError('navigation failed')), wait_for_timeout=mock.Mock(), screenshot=mock.Mock())

            def close(self):
                self.closed = True

        class FakePlaywrightContext:

            def __init__(self, browser):
                self.browser = browser

            def __enter__(self):
                return SimpleNamespace(chromium=SimpleNamespace(launch=mock.Mock(return_value=self.browser)))

            def __exit__(self, _exc_type, _exc, _traceback):
                return False
        browser = FakeBrowser()
        sync_api = SimpleNamespace(sync_playwright=mock.Mock(return_value=FakePlaywrightContext(browser)))
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}):
            with pytest.raises(RuntimeError, match='navigation failed'):
                visual_screenshot.screenshot_html(Path('missing.html'), Path('unused.png'), visual_screenshot.Viewport(width=1360, height=900))
        assert browser.closed

    def test_screenshot_html_opens_view_menu_for_comparison_only(self):
        from tools import visual_screenshot

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.evaluate = mock.Mock()
                self.wait_for_timeout = mock.Mock()
                self.screenshot = mock.Mock()

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
            visual_screenshot.screenshot_html(Path('sample.html'), Path('output.png'), visual_screenshot.Viewport(width=1360, height=900))
        page.evaluate.assert_called_once()
        view_state_script = page.evaluate.call_args.args[0]
        assert "document.querySelectorAll('details.view-menu').forEach((menu) => { menu.open = true; })" in view_state_script
        assert "document.querySelector('#holiday-toggle')" in view_state_script
        assert 'holidayToggle.checked = true' in view_state_script
        assert "holidayToggle.dispatchEvent(new Event('change', {bubbles: true}))" in view_state_script
        page.wait_for_timeout.assert_called_once_with(250)
        page.screenshot.assert_called_once()
        assert browser.closed

    def test_screenshot_html_can_capture_a_fixed_clip(self):
        from tools import visual_screenshot

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.evaluate = mock.Mock()
                self.wait_for_timeout = mock.Mock()
                self.screenshot = mock.Mock()

        class FakeBrowser:

            def __init__(self, page):
                self.page = page

            def new_page(self, **_kwargs):
                return self.page

            def close(self):
                pass

        class FakePlaywrightContext:

            def __enter__(self):
                return SimpleNamespace(chromium=SimpleNamespace(launch=mock.Mock(return_value=FakeBrowser(page))))

            def __exit__(self, _exc_type, _exc, _traceback):
                return False
        page = FakePage()
        sync_api = SimpleNamespace(sync_playwright=mock.Mock(return_value=FakePlaywrightContext()))
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}):
            visual_screenshot.screenshot_html(Path('sample.html'), Path('output.png'), visual_screenshot.Viewport(width=1360, height=900), clip={'x': 0, 'y': 0, 'width': 1360, 'height': 420})
        page.screenshot.assert_called_once_with(path='output.png', full_page=False, clip={'x': 0, 'y': 0, 'width': 1360, 'height': 420})

    def test_screenshot_html_supports_clean_view_state(self):
        from tools import visual_screenshot

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.evaluate = mock.Mock()
                self.wait_for_timeout = mock.Mock()
                self.screenshot = mock.Mock()

        class FakeBrowser:

            def new_page(self, **_kwargs):
                return page

            def close(self):
                pass

        class FakePlaywrightContext:

            def __enter__(self):
                return SimpleNamespace(chromium=SimpleNamespace(launch=mock.Mock(return_value=FakeBrowser())))

            def __exit__(self, _exc_type, _exc, _traceback):
                return False
        page = FakePage()
        sync_api = SimpleNamespace(sync_playwright=mock.Mock(return_value=FakePlaywrightContext()))
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}):
            visual_screenshot.screenshot_html(Path('sample.html'), Path('output.png'), visual_screenshot.Viewport(width=1360, height=900), view_state='clean')
        script = page.evaluate.call_args.args[0]
        assert 'menu.open = false' in script
        assert 'holidayToggle.checked = false' in script
        assert 'warningToggle.checked = false' in script

    def test_screenshot_html_supports_workspace_bottom_state(self):
        from tools import visual_screenshot

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.evaluate = mock.Mock()
                self.wait_for_timeout = mock.Mock()
                self.screenshot = mock.Mock()

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
            visual_screenshot.screenshot_html(Path('sample.html'), Path('output.png'), visual_screenshot.Viewport(width=1360, height=900), view_state='workspace-bottom')
        view_state_script = page.evaluate.call_args.args[0]
        assert 'warningToggle.checked = false' in view_state_script
        assert "document.querySelector('#warning-window-toggle')" in view_state_script
        assert 'workspace.scrollTop = workspace.scrollHeight' in view_state_script
        assert 'workspace.scrollLeft = 0' in view_state_script
        page.wait_for_timeout.assert_called_once_with(250)
        page.screenshot.assert_called_once()
        assert browser.closed

    def test_screenshot_html_supports_analysis_view_state(self):
        from tools import visual_screenshot

        class FakePage:

            def __init__(self):
                self.goto = mock.Mock()
                self.evaluate = mock.Mock()
                self.wait_for_timeout = mock.Mock()
                self.screenshot = mock.Mock()

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
            visual_screenshot.screenshot_html(Path('sample.html'), Path('output.png'), visual_screenshot.Viewport(width=1360, height=900), view_state='analysis')
        view_state_script = page.evaluate.call_args.args[0]
        assert 'document.querySelector(\'[data-wbs-view-target="analysis"]\')' in view_state_script
        assert 'analysisTab.click()' in view_state_script
        page.wait_for_timeout.assert_called_once_with(250)
        page.screenshot.assert_called_once()
        assert browser.closed

    def test_screenshot_html_closes_browser_when_new_page_fails(self):
        from tools import visual_screenshot

        class FakeBrowser:

            def __init__(self):
                self.closed = False

            def new_page(self, **_kwargs):
                raise RuntimeError('new page failed')

            def close(self):
                self.closed = True

        class FakePlaywrightContext:

            def __init__(self, browser):
                self.browser = browser

            def __enter__(self):
                return SimpleNamespace(chromium=SimpleNamespace(launch=mock.Mock(return_value=self.browser)))

            def __exit__(self, _exc_type, _exc, _traceback):
                return False
        browser = FakeBrowser()
        sync_api = SimpleNamespace(sync_playwright=mock.Mock(return_value=FakePlaywrightContext(browser)))
        with mock.patch.dict('sys.modules', {'playwright': SimpleNamespace(sync_api=sync_api), 'playwright.sync_api': sync_api}):
            with pytest.raises(RuntimeError, match='new page failed'):
                visual_screenshot.screenshot_html(Path('missing.html'), Path('unused.png'), visual_screenshot.Viewport(width=1360, height=900))
        assert browser.closed

    def test_main_writes_errors_to_stderr(self):
        from tools import visual_screenshot
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(visual_screenshot, 'run', side_effect=ValueError('generated HTML not found: missing.html')):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = visual_screenshot.main(['--generated-html', 'missing.html', '--output-dir', 'output'])
        assert exit_code == 1
        assert stdout.getvalue() == ''
        assert 'visual_screenshot: error: generated HTML not found: missing.html' in stderr.getvalue()

    def test_run_requires_project_local_playwright_browser_cache(self):
        from tools import visual_screenshot
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            generated_html = tmp / 'visual-test.html'
            generated_html.write_text('<!doctype html><title>generated</title>', encoding='utf-8')
            args = visual_screenshot.parse_args(['--generated-html', str(generated_html), '--output-dir', str(tmp / 'output')])
            with mock.patch.dict('os.environ', {}, clear=True):
                with pytest.raises(ValueError, match='PLAYWRIGHT_BROWSERS_PATH must be .cache/ms-playwright'):
                    visual_screenshot.run(args)

    def test_run_accepts_project_local_playwright_browser_cache(self):
        from tools import visual_screenshot
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            generated_html = tmp / 'visual-test.html'
            generated_html.write_text('<!doctype html><title>generated</title>', encoding='utf-8')
            args = visual_screenshot.parse_args(['--generated-html', str(generated_html), '--output-dir', str(tmp / 'output')])
            with mock.patch.dict('os.environ', {'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'}, clear=True):
                with mock.patch.object(visual_screenshot, 'screenshot_html') as screenshot:
                    visual_screenshot.run(args)
            assert screenshot.call_count == 3
            assert screenshot.call_args_list[1].kwargs == {'view_state': 'workspace-bottom'}
            assert screenshot.call_args_list[2].kwargs == {'view_state': 'analysis'}
            assert not (tmp / 'output' / 'visual-metadata.json').exists()

    def test_parse_viewport_accepts_width_and_height(self):
        from tools import visual_screenshot
        assert visual_screenshot.parse_viewport('1360x900') == visual_screenshot.Viewport(width=1360, height=900)

    def test_parse_viewport_rejects_invalid_value(self):
        from tools import visual_screenshot
        with pytest.raises(ValueError, match='viewport must be WIDTHxHEIGHT'):
            visual_screenshot.parse_viewport('wide')
