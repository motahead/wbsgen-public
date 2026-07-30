"""Run a seed-recorded exploratory QA workflow against a release zipapp."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.generate_qa_data import generate_project, write_project  # noqa: E402
from tools.workflow_verification import (  # noqa: E402
    assert_dom_matches_source,
    assert_pane_boundary_states,
    capture_pane_boundary_states,
    assert_source_equal,
    assert_valid_xlsx,
    capture_dom_state,
    run_zipapp,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _export_source(zipapp: Path, html: Path, work_dir: Path, name: str) -> dict[str, Any]:
    output = work_dir / name
    run_zipapp(
        zipapp,
        ["export", "json", html.name, "-o", output.name, "--overwrite"],
        work_dir,
    )
    return _read_json(output)


def _assert_html_state(zipapp: Path, html: Path, work_dir: Path) -> dict[str, Any]:
    data = _export_source(zipapp, html, work_dir, "current.json")
    assert_dom_matches_source(data, capture_dom_state(html))
    assert_pane_boundary_states(capture_pane_boundary_states(html))
    return data


def _new_child_id(data: dict[str, Any]) -> str:
    parent_ids = [task["id"] for task in data["tasks"] if "." not in task["id"]]
    parent_id = parent_ids[0]
    child_numbers = [
        int(task["id"].split(".")[1])
        for task in data["tasks"]
        if task["id"].startswith(f"{parent_id}.")
        and task["id"].count(".") == 1
        and task["id"].split(".")[1].isdigit()
    ]
    return f"{parent_id}.{max(child_numbers, default=0) + 1}"


def _new_root_id(data: dict[str, Any]) -> str:
    root_numbers = [
        int(task["id"])
        for task in data["tasks"]
        if task["id"].isdigit()
    ]
    return str(max(root_numbers, default=0) + 1)


def _planned_leaf_tasks(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for task in data["tasks"]
        if "assignee" in task and "plannedStart" in task and "plannedDuration" in task
    ]


def _assert_task_present(data: dict[str, Any], task_id: str) -> None:
    if not any(task["id"] == task_id for task in data["tasks"]):
        raise AssertionError(f"task add did not create expected id: {task_id}")


def seed_date(seed: int) -> date:
    """Derive a stable project date so a recorded seed is replayable on any day."""
    return date(2025, 1, 1) + timedelta(days=seed % 365)


def run_workflow(*, zipapp: Path, work_dir: Path, data: dict[str, Any]) -> None:
    """Exercise data-dependent edits and round trips, retaining all seed artifacts."""
    input_json = work_dir / "qa-data.json"
    html = work_dir / "qa.html"
    regenerated_html = work_dir / "qa-regenerated.html"
    write_project(data, input_json)
    run_zipapp(
        zipapp,
        ["generate", input_json.name, "-o", html.name, "--overwrite"],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)

    planned = _planned_leaf_tasks(current)
    if len(planned) < 2:
        raise AssertionError("exploratory fixture needs at least two planned leaf tasks")
    completed = planned[0]
    run_zipapp(
        zipapp,
        [
            "task", "update", html.name, "--id", completed["id"], "--progress", "100",
            "--actual-start", completed["plannedStart"], "--actual-end", completed["plannedStart"],
        ],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)

    added_id = _new_child_id(current)
    project_end = current["project"]["endDate"]
    run_zipapp(
        zipapp,
        [
            "task", "add", html.name, "--id", added_id, "--name", "QA追加タスク",
            "--assignee", "QA担当", "--planned-start", project_end,
            "--planned-duration", "1", "--progress", "0",
        ],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)
    _assert_task_present(current, added_id)

    parent_id = added_id.split(".", 1)[0]
    parent_auto_id = _new_child_id(current)
    run_zipapp(
        zipapp,
        [
            "task", "add", html.name, "--parent-id", parent_id,
            "--name", "QA親指定自動採番タスク", "--assignee", "QA担当",
            "--planned-start", project_end, "--planned-duration", "1", "--progress", "0",
        ],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)
    _assert_task_present(current, parent_auto_id)

    root_auto_id = _new_root_id(current)
    run_zipapp(
        zipapp,
        [
            "task", "add", html.name, "--name", "QA最上位自動採番タスク",
            "--assignee", "QA担当", "--planned-start", project_end,
            "--planned-duration", "1", "--progress", "0",
        ],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)
    _assert_task_present(current, root_auto_id)

    delayed = next(task for task in _planned_leaf_tasks(current) if task["id"] != completed["id"])
    run_zipapp(
        zipapp,
        [
            "task", "update", html.name, "--id", delayed["id"], "--progress", "25",
            "--actual-start", delayed["plannedStart"],
        ],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)

    run_zipapp(
        zipapp,
        ["display", "update", "standard", html.name, "--visible", "assignee,progress,issue"],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)
    run_zipapp(
        zipapp,
        ["display", "update", "analysis", html.name, "--order", "assignee,delta,delay,pace"],
        work_dir,
    )
    current = _assert_html_state(zipapp, html, work_dir)
    run_zipapp(
        zipapp,
        ["display", "update", "layers", html.name, "--visible", "actual,inazuma"],
        work_dir,
    )
    original = _assert_html_state(zipapp, html, work_dir)
    write_project(original, work_dir / "qa-original.json")

    edited = json.loads(json.dumps(original))
    edited["project"]["name"] = f"{edited['project']['name']}（再生成）"
    write_project(edited, work_dir / "qa-edited.json")
    run_zipapp(
        zipapp,
        ["generate", "qa-edited.json", "-o", regenerated_html.name, "--overwrite"],
        work_dir,
    )
    regenerated = _export_source(zipapp, regenerated_html, work_dir, "qa-regenerated.json")
    assert_source_equal(edited, regenerated)
    assert_dom_matches_source(regenerated, capture_dom_state(regenerated_html))
    final_xlsx = work_dir / "qa.xlsx"
    run_zipapp(
        zipapp,
        ["export", "xlsx", regenerated_html.name, "-o", final_xlsx.name, "--overwrite"],
        work_dir,
    )
    assert_valid_xlsx(
        final_xlsx,
        project_name=regenerated["project"]["name"],
        expected_wbs_rows=len(regenerated["tasks"]),
    )


def run(zipapp: Path, work_dir: Path, seed: int | None) -> int:
    resolved_seed = seed if seed is not None else time.time_ns()
    print(f"seed={resolved_seed}", file=sys.stderr)
    seed_dir = work_dir / str(resolved_seed)
    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    seed_dir.mkdir(parents=True)
    run_workflow(
        zipapp=zipapp.resolve(),
        work_dir=seed_dir,
        data=generate_project(resolved_seed, seed_date(resolved_seed)),
    )
    print(f"qa_explore: passed (artifacts: {seed_dir})", file=sys.stderr)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zipapp", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "output" / "qa")
    parser.add_argument("--seed", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        return run(args.zipapp, args.work_dir, args.seed)
    except Exception as exc:
        print(f"qa_explore: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
