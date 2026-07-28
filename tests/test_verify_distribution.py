from pathlib import Path

from tools import verify_distribution


def test_command_markers_cover_each_public_cli_family():
    markers = verify_distribution.command_markers(Path("workflow.html"))

    assert ["--version"] in markers
    assert ["init", "initial.json", "--name", "初期化確認"] in markers
    assert ["template", "template.json"] in markers
    assert ["project", "show", "workflow.html"] in markers
    assert ["task", "move", "workflow.html", "--id", "2.2", "--to", "2.3"] in markers
    assert ["milestone", "show", "workflow.html"] in markers
    assert ["holiday", "show", "workflow.html"] in markers
    assert any(marker[:3] == ["holiday", "merge", "workflow.html"] for marker in markers)
    assert any(marker[:3] == ["holiday", "import-gov", "workflow.html"] for marker in markers)
    assert ["display", "show", "workflow.html"] in markers
    assert any(marker[:3] == ["export", "xlsx", "workflow.html"] for marker in markers)


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
