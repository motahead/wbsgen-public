import subprocess
from unittest import mock

import pytest

from tools import workflow_verification


def test_assert_source_equal_ignores_generator_metadata():
    expected = {"project": {"name": "P"}, "tasks": [], "holidays": [], "milestones": []}

    workflow_verification.assert_source_equal(
        expected,
        {**expected, "_wbsgen": {"generatorVersion": "development"}},
    )


def test_assert_source_equal_reports_task_loss():
    expected = {"project": {}, "tasks": [{"id": "1"}], "holidays": [], "milestones": []}
    actual = {"project": {}, "tasks": [], "holidays": [], "milestones": []}

    with pytest.raises(AssertionError, match="tasks"):
        workflow_verification.assert_source_equal(expected, actual)


def test_run_zipapp_reports_stdout_and_stderr_on_failure(tmp_path):
    completed = subprocess.CompletedProcess(
        args=["python", "wbsgen.pyz", "validate"],
        returncode=1,
        stdout="validation output",
        stderr="validation error",
    )

    with mock.patch("subprocess.run", return_value=completed):
        with pytest.raises(AssertionError, match="validation error"):
            workflow_verification.run_zipapp(tmp_path / "wbsgen.pyz", ["validate"], tmp_path)


def test_assert_valid_xlsx_rejects_a_corrupt_archive(tmp_path):
    target = tmp_path / "broken.xlsx"
    target.write_bytes(b"not a zip file")

    with pytest.raises(AssertionError, match="valid XLSX ZIP"):
        workflow_verification.assert_valid_xlsx(target)


def test_assert_pane_boundary_states_accepts_allowed_handle_overlap():
    states = {
        "standard-initial": {"leftPaneRight": 640.0, "dividerX": 637.0},
        "analysis-after-standard-resize": {"leftPaneRight": 650.0, "dividerX": 647.0},
    }

    workflow_verification.assert_pane_boundary_states(states)


def test_assert_pane_boundary_states_reports_state_and_gap():
    states = {
        "analysis-after-standard-resize": {"leftPaneRight": 598.0, "dividerX": 644.0}
    }

    with pytest.raises(AssertionError, match=r"analysis-after-standard-resize.*46"):
        workflow_verification.assert_pane_boundary_states(states)
