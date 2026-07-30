import subprocess
from pathlib import Path

import pytest

from tools import verify_distribution


def test_command_markers_cover_each_public_cli_family():
    markers = verify_distribution.command_markers(Path("workflow.html"))

    assert ["--version"] in markers
    assert ["init", "initial.json", "--name", "初期化確認"] in markers
    assert ["template", "template.json"] in markers
    assert ["project", "show", "workflow.html"] in markers
    assert ["task", "show", "workflow.html", "--id", "1.2", "--direct"] in markers
    assert ["task", "show", "workflow.html", "--id", "1.2", "--complement"] in markers
    assert ["task", "add", "workflow.html", "--id", "1.3", "--name", "明示IDタスク", "--assignee", "担当者F", "--planned-start", "2026-08-24", "--planned-duration", "1"] in markers
    assert ["task", "add", "workflow.html", "--parent-id", "2", "--name", "一時タスク", "--assignee", "担当者D", "--planned-start", "2026-08-24", "--planned-duration", "1"] in markers
    assert ["task", "add", "workflow.html", "--name", "トップレベルタスク", "--assignee", "担当者E", "--planned-start", "2026-08-25", "--planned-duration", "1"] in markers
    assert ["task", "update", "workflow.html", "--id", "1.2", "--comment", "下書き", "--dry-run"] in markers
    assert ["task", "update", "workflow.html", "--id", "1.2", "--clear", "comment"] in markers
    assert ["task", "move", "workflow.html", "--id", "2.2", "--to", "2.4"] in markers
    assert ["milestone", "show", "workflow.html"] in markers
    assert ["holiday", "show", "workflow.html"] in markers
    assert any(marker[:3] == ["holiday", "merge", "workflow.html"] for marker in markers)
    assert any(marker[:3] == ["holiday", "import-gov", "workflow.html"] for marker in markers)
    assert ["display", "show", "workflow.html"] in markers
    assert any(marker[:3] == ["export", "xlsx", "workflow.html"] for marker in markers)
    assert ["export", "md", "workflow.html", "-o", "workflow-alias.md", "--overwrite"] in markers


def test_run_uses_only_the_given_work_directory(tmp_path, monkeypatch):
    calls = []

    monkeypatch.setattr(
        verify_distribution,
        "run_zipapp",
        lambda _zipapp, args, cwd: calls.append((args, cwd)),
    )
    monkeypatch.setattr(verify_distribution, "_run_sample_contract", lambda *_args: None)
    monkeypatch.setattr(verify_distribution, "_run_contract", lambda *_args: None)

    verify_distribution.run(tmp_path / "wbsgen.pyz", tmp_path / "output" / "distribution")

    assert calls == []
    assert (tmp_path / "output" / "distribution").is_dir()


def test_clean_validation_rejects_warning_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify_distribution,
        "run_zipapp",
        lambda *_args: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"errorCount": 0, "warningCount": 1}',
            stderr="",
        ),
    )

    with pytest.raises(AssertionError, match="warningCount=1"):
        verify_distribution._assert_clean_validation(
            tmp_path / "wbsgen.pyz", "sample.json", tmp_path
        )


def test_clean_validation_accepts_error_and_warning_free_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verify_distribution,
        "run_zipapp",
        lambda *_args: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"errorCount": 0, "warningCount": 0}',
            stderr="",
        ),
    )

    verify_distribution._assert_clean_validation(
        tmp_path / "wbsgen.pyz", "sample.json", tmp_path
    )
