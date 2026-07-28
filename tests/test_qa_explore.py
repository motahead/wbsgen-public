from tools import qa_explore


def test_qa_explore_uses_reported_seed_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qa_explore, "run_workflow", lambda **_kwargs: None)

    assert qa_explore.run(tmp_path / "wbsgen.pyz", tmp_path / "qa", seed=42) == 0

    assert (tmp_path / "qa" / "42").is_dir()
    assert "seed=42" in capsys.readouterr().err


def test_seed_date_is_stable_for_replay():
    assert qa_explore.seed_date(42) == qa_explore.seed_date(42)
    assert qa_explore.seed_date(42) != qa_explore.seed_date(43)
