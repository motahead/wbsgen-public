from copy import deepcopy

from tools import qa_explore


def test_qa_explore_uses_reported_seed_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(qa_explore, "run_workflow", lambda **_kwargs: None)

    assert qa_explore.run(tmp_path / "wbsgen.pyz", tmp_path / "qa", seed=42) == 0

    assert (tmp_path / "qa" / "42").is_dir()
    assert "seed=42" in capsys.readouterr().err


def test_seed_date_is_stable_for_replay():
    assert qa_explore.seed_date(42) == qa_explore.seed_date(42)
    assert qa_explore.seed_date(42) != qa_explore.seed_date(43)


def test_run_workflow_exercises_all_task_add_id_paths(tmp_path, monkeypatch):
    initial = {
        "project": {
            "name": "QAテスト案件",
            "startDate": "2026-01-01",
            "endDate": "2026-01-31",
            "statusDate": "2026-01-15",
        },
        "tasks": [
            {"id": "1", "name": "親タスク"},
            {
                "id": "1.1",
                "name": "子タスク1",
                "assignee": "担当者A",
                "plannedStart": "2026-01-10",
                "plannedDuration": 1,
            },
            {
                "id": "1.2",
                "name": "子タスク2",
                "assignee": "担当者B",
                "plannedStart": "2026-01-11",
                "plannedDuration": 1,
            },
            {"id": "2", "name": "別の親タスク"},
        ],
        "holidays": [],
        "milestones": [],
    }

    def with_added_task(data, task_id):
        updated = deepcopy(data)
        updated["tasks"].append(
            {
                "id": task_id,
                "name": "QA追加タスク",
                "assignee": "QA担当",
                "plannedStart": "2026-01-31",
                "plannedDuration": 1,
                "progress": 0,
            }
        )
        return updated

    after_explicit_child = with_added_task(initial, "1.3")
    after_parent_auto_child = with_added_task(after_explicit_child, "1.4")
    after_root_auto = with_added_task(after_parent_auto_child, "3")
    states = iter(
        [
            initial,
            initial,
            after_explicit_child,
            after_parent_auto_child,
            after_root_auto,
            after_root_auto,
            after_root_auto,
            after_root_auto,
            after_root_auto,
        ]
    )
    commands = []

    monkeypatch.setattr(
        qa_explore,
        "run_zipapp",
        lambda _zipapp, args, _cwd: commands.append(args),
    )
    monkeypatch.setattr(
        qa_explore,
        "_assert_html_state",
        lambda *_args: next(states),
    )
    monkeypatch.setattr(qa_explore, "_export_source", lambda *_args: after_root_auto)
    monkeypatch.setattr(qa_explore, "assert_dom_matches_source", lambda *_args: None)
    monkeypatch.setattr(qa_explore, "capture_dom_state", lambda *_args: {})
    monkeypatch.setattr(qa_explore, "assert_source_equal", lambda *_args: None)
    monkeypatch.setattr(qa_explore, "assert_valid_xlsx", lambda *_args, **_kwargs: None)

    qa_explore.run_workflow(
        zipapp=tmp_path / "wbsgen.pyz",
        work_dir=tmp_path,
        data=initial,
    )

    task_adds = [args for args in commands if args[:2] == ["task", "add"]]
    assert task_adds[0][3:5] == ["--id", "1.3"]
    assert "--parent-id" in task_adds[1]
    assert task_adds[1][task_adds[1].index("--parent-id") + 1] == "1"
    assert "--id" not in task_adds[1]
    assert "--id" not in task_adds[2]
    assert "--parent-id" not in task_adds[2]
