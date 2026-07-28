import pytest
import json
import os
import subprocess
import tempfile
from pathlib import Path

class TestWidthModelTests:

    def evaluate_width_model(self, script):
        browser_python = Path('.venv/bin/python')
        if not browser_python.is_file():
            pytest.skip('Playwright runtime is not available')
        if not Path('.cache/ms-playwright').exists():
            pytest.skip('Playwright browser cache is not available')
        from wbsgen.render import html
        width_model_source = html.read_text_asset('width-model.js')
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as tmp:
            tmp.write(width_model_source)
            width_model_path = tmp.name
        runner = "\nimport json\nimport sys\nfrom pathlib import Path\nfrom playwright.sync_api import sync_playwright\n\nwidth_model_path = Path(sys.argv[1]).resolve()\nscript = sys.argv[2]\n\nwith sync_playwright() as playwright:\n    browser = playwright.chromium.launch(headless=True, args=['--disable-gpu', '--disable-dev-shm-usage'])\n    page = browser.new_page()\n    try:\n        page.goto('about:blank')\n        page.add_script_tag(path=str(width_model_path))\n        print(json.dumps(page.evaluate(script)))\n    finally:\n        browser.close()\n"
        try:
            proc = subprocess.run([str(browser_python), '-c', runner, width_model_path, script], capture_output=True, text=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': '.cache/ms-playwright'})
        finally:
            Path(width_model_path).unlink(missing_ok=True)
        if proc.returncode != 0:
            if 'bootstrap_check_in' in proc.stderr or 'Permission denied' in proc.stderr:
                pytest.skip('Browser launch is not permitted in this environment')
            pytest.fail(proc.stderr)
        return json.loads(proc.stdout)

    def test_create_returns_initial_widths_from_config(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n          return {\n            taskNameWidth: model.getTaskNameWidth(),\n            assigneeWidth: model.getAssigneeWidth(),\n            commentWidth: model.getCommentWidth(),\n            leftPaneWidth: model.getLeftPaneWidth(),\n            isCommentHidden: model.isColumnHidden('comment'),\n            isAssigneeHidden: model.isColumnHidden('assignee'),\n            commentColumnWidth: model.getColumnWidth('comment'),\n            assigneeColumnWidth: model.getColumnWidth('assignee'),\n            issueColumnWidth: model.getColumnWidth('issue'),\n            visibleColumnTotalWidth: model.getVisibleColumnTotalWidth(),\n          };\n        }"
        state = self.evaluate_width_model(script)
        assert state['taskNameWidth'] == 220
        assert state['assigneeWidth'] == 56
        assert state['commentWidth'] == 244
        assert state['leftPaneWidth'] == 892
        assert not state['isCommentHidden']
        assert not state['isAssigneeHidden']
        assert state['commentColumnWidth'] == 244
        assert state['assigneeColumnWidth'] == 56
        assert state['issueColumnWidth'] == 58
        assert state['visibleColumnTotalWidth'] == 892

    def test_set_column_hidden_shrinks_and_restores_left_pane_width(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n          const afterHideIssue = model.setColumnHidden('issue', true);\n          const issueHiddenWidth = model.getColumnWidth('issue');\n          const afterShowIssue = model.setColumnHidden('issue', false);\n          const afterHideComment = model.setColumnHidden('comment', true);\n          const afterHideAssignee = model.setColumnHidden('assignee', true);\n          const assigneeHiddenWidth = model.getColumnWidth('assignee');\n          return {\n            afterHideIssueLeftWidth: afterHideIssue.leftPaneWidth,\n            issueHiddenWidth,\n            afterShowIssueLeftWidth: afterShowIssue.leftPaneWidth,\n            afterHideCommentLeftWidth: afterHideComment.leftPaneWidth,\n            afterHideAssigneeLeftWidth: afterHideAssignee.leftPaneWidth,\n            assigneeHiddenWidth,\n            otherColumnKeys: model.getOtherColumnKeys(),\n          };\n        }"
        state = self.evaluate_width_model(script)
        assert state['afterHideIssueLeftWidth'] == 892 - 58
        assert state['issueHiddenWidth'] == 0
        assert state['afterShowIssueLeftWidth'] == 892
        assert state['afterHideCommentLeftWidth'] == 892 - 244
        assert state['afterHideAssigneeLeftWidth'] == 892 - 244 - 56
        assert state['assigneeHiddenWidth'] == 0
        assert sorted(state['otherColumnKeys']) == sorted(['planned-period', 'actual-period', 'progress', 'expected-progress', 'issue'])

    def test_task_name_resize_clamps_to_default_min_and_reachable_max(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n\n          model.beginTaskNameResize();\n          const grown = model.updateTaskNameResize(9999, {windowInnerWidth: 2000, workspaceClientWidth: 1800});\n\n          model.beginTaskNameResize();\n          const shrunkBelowDefault = model.updateTaskNameResize(-9999, {windowInnerWidth: 2000, workspaceClientWidth: 1800});\n\n          model.beginTaskNameResize();\n          const boundedByNarrowViewport = model.updateTaskNameResize(9999, {windowInnerWidth: 1000, workspaceClientWidth: 800});\n\n          return {grown, shrunkBelowDefault, boundedByNarrowViewport};\n        }"
        state = self.evaluate_width_model(script)
        assert state['grown']['taskNameWidth'] == 700
        assert state['grown']['leftPaneWidth'] == 892 + 480
        assert state['shrunkBelowDefault']['taskNameWidth'] == 220
        assert state['shrunkBelowDefault']['leftPaneWidth'] == 892 + 480 - 480
        assert state['boundedByNarrowViewport']['taskNameWidth'] == 220
        assert state['boundedByNarrowViewport']['leftPaneWidth'] == 892

    def test_assignee_resize_grows_from_default_and_does_not_shrink_below_it(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n\n          model.beginAssigneeResize();\n          const grown = model.updateAssigneeResize(100, {windowInnerWidth: 2000});\n\n          model.beginAssigneeResize();\n          const shrunkBelowDefault = model.updateAssigneeResize(-9999, {windowInnerWidth: 2000});\n\n          return {grown, shrunkBelowDefault};\n        }"
        state = self.evaluate_width_model(script)
        assert state['grown']['assigneeWidth'] == 156
        assert state['grown']['leftPaneWidth'] == 892 + 100
        assert state['shrunkBelowDefault']['assigneeWidth'] == 56
        assert state['shrunkBelowDefault']['leftPaneWidth'] == 892 + 100 - 100

    def test_pane_resize_grows_comment_width_and_clamps_to_bounds(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n\n          model.beginPaneResize();\n          const grown = model.updatePaneResize(100, {windowInnerWidth: 1000});\n\n          model.beginPaneResize();\n          const shrunkToMin = model.updatePaneResize(-9999, {windowInnerWidth: 1000});\n\n          return {grown, shrunkToMin};\n        }"
        state = self.evaluate_width_model(script)
        assert state['grown']['commentWidth'] == 344
        assert state['grown']['leftPaneWidth'] == 992
        assert state['shrunkToMin']['commentWidth'] == 244
        assert state['shrunkToMin']['leftPaneWidth'] == 278

    def test_pane_resize_does_not_grow_past_fixed_part_when_comment_hidden_at_start(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n\n          model.setColumnHidden('comment', true);\n          model.beginPaneResize();\n          const afterResize = model.updatePaneResize(9999, {windowInnerWidth: 1000});\n\n          return {afterResize};\n        }"
        state = self.evaluate_width_model(script)
        assert state['afterResize']['leftPaneWidth'] == 648
        assert state['afterResize']['commentWidth'] == 244

    def test_get_id_column_width_returns_configured_value(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n          return {idColumnWidth: model.getIdColumnWidth()};\n        }"
        state = self.evaluate_width_model(script)
        assert state['idColumnWidth'] == 58

    def test_set_left_pane_width_clamps_between_min_and_caller_supplied_max(self):
        script = "() => {\n          const model = WbsWidthModel.create({\n            idColumnWidth: 58,\n            defaultTaskNameWidth: 220,\n            defaultAssigneeWidth: 56,\n            defaultCommentWidth: 244,\n            columnWidths: {'planned-period': 76, 'actual-period': 76, progress: 52, 'expected-progress': 52, issue: 58},\n          });\n\n          const withinRange = model.setLeftPaneWidth(400, 500);\n          const clampedToMax = model.setLeftPaneWidth(9999, 500);\n          const clampedToMin = model.setLeftPaneWidth(-9999, 500);\n\n          return {withinRange, clampedToMax, clampedToMin};\n        }"
        state = self.evaluate_width_model(script)
        assert state['withinRange']['leftPaneWidth'] == 400
        assert state['clampedToMax']['leftPaneWidth'] == 500
