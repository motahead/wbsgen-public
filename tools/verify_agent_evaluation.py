"""Independently verify one isolated AI-agent WBS-GEN trial."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.workflow_verification import assert_source_equal, assert_valid_xlsx, run_zipapp


REQUIRED_EXPECTATION_KEYS = frozenset(
    {"scenarioId", "artifacts", "source", "computed", "requiredExports", "rubric"}
)


def load_expectation(path: Path) -> dict[str, Any]:
    """Load and minimally validate the evaluator-only expectation file."""

    expectation = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(expectation, dict):
        raise ValueError("expectation must be a JSON object")
    missing = sorted(REQUIRED_EXPECTATION_KEYS - expectation.keys())
    if missing:
        raise ValueError(f"expectation is missing keys: {', '.join(missing)}")
    return expectation


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path.name} must contain a JSON object")
    return data


def _expected_artifact_names(expectation: dict[str, Any]) -> list[str]:
    artifacts = expectation["artifacts"]
    if not isinstance(artifacts, dict):
        raise ValueError("expectation.artifacts must be an object")
    names = list(artifacts.values())
    if not all(isinstance(name, str) and name for name in names):
        raise ValueError("expectation.artifacts values must be non-empty strings")
    return names


def _compare_expected_fields(
    expected: Any, actual: Any, path: str, differences: list[str]
) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            differences.append(
                f"{path}: expected object actual={actual!r}"
            )
            return
        for key, expected_value in expected.items():
            child_path = f"{path}.{key}" if path else key
            if key not in actual:
                differences.append(f"{child_path}: expected={expected_value!r} actual=<missing>")
                continue
            _compare_expected_fields(expected_value, actual[key], child_path, differences)
        return
    if expected != actual:
        differences.append(f"{path}: expected={expected!r} actual={actual!r}")


def _compare_expected_tasks(
    expected_tasks: list[dict[str, Any]], actual_tasks: Any, differences: list[str]
) -> None:
    if not isinstance(actual_tasks, list):
        differences.append("tasks: expected list actual=<non-list>")
        return
    tasks_by_id = {
        task.get("id"): task for task in actual_tasks if isinstance(task, dict) and "id" in task
    }
    for expected_task in expected_tasks:
        task_id = expected_task["id"]
        actual_task = tasks_by_id.get(task_id)
        if actual_task is None:
            differences.append(f"tasks[{task_id}]: expected task actual=<missing>")
            continue
        _compare_expected_fields(expected_task, actual_task, f"tasks[{task_id}]", differences)


def _assert_expected_source(expected_source: dict[str, Any], actual_source: dict[str, Any]) -> None:
    differences: list[str] = []
    for key in ("project", "display", "holidays", "milestones"):
        if key in expected_source:
            _compare_expected_fields(expected_source[key], actual_source.get(key), key, differences)
    if "tasks" in expected_source:
        _compare_expected_tasks(expected_source["tasks"], actual_source.get("tasks"), differences)
    if differences:
        raise AssertionError("source fields differ:\n- " + "\n- ".join(differences))


def _assert_clean_validation(zipapp: Path, html_name: str, run_dir: Path) -> None:
    completed = run_zipapp(zipapp, ["validate", html_name, "--json"], run_dir)
    report = json.loads(completed.stdout)
    for key in ("errorCount", "warningCount"):
        if report.get(key) != 0:
            raise AssertionError(f"validate report has {key}={report.get(key)!r}")


def _assert_computed_planned_ends(
    zipapp: Path, expected_computed: dict[str, Any], html_name: str, run_dir: Path
) -> None:
    planned_ends = expected_computed.get("plannedEnds")
    if not isinstance(planned_ends, dict):
        raise ValueError("expectation.computed.plannedEnds must be an object")
    differences: list[str] = []
    for task_id, expected_end in planned_ends.items():
        completed = run_zipapp(
            zipapp,
            ["task", "show", html_name, "--id", str(task_id), "--complement"],
            run_dir,
        )
        actual_end = json.loads(completed.stdout).get("task", {}).get("plannedEnd")
        if expected_end != actual_end:
            differences.append(
                f"tasks[{task_id}].plannedEnd: expected={expected_end!r} actual={actual_end!r}"
            )
    if differences:
        raise AssertionError("computed fields differ:\n- " + "\n- ".join(differences))


def _assert_exports(
    zipapp: Path, expectation: dict[str, Any], run_dir: Path, actual_source: dict[str, Any]
) -> None:
    artifacts = expectation["artifacts"]
    markdown = (run_dir / artifacts["markdown"]).read_text(encoding="utf-8")
    if "| ID | タスク名 |" not in markdown:
        raise AssertionError("markdown export did not contain the WBS header")

    csv_path = run_dir / artifacts["csv"]
    try:
        csv_rows = list(csv.reader(csv_path.read_text(encoding="utf-8-sig").splitlines()))
    except UnicodeDecodeError as error:
        raise AssertionError("csv export must use UTF-8 or UTF-8 with BOM") from error
    if not csv_rows or not csv_rows[0] or csv_rows[0][0] != "ID":
        raise AssertionError("csv export did not contain the WBS header")

    assert_valid_xlsx(
        run_dir / artifacts["xlsx"],
        project_name=expectation["source"]["project"]["name"],
        expected_wbs_rows=len(actual_source["tasks"]),
    )

    with tempfile.TemporaryDirectory(prefix="wbsgen-agent-evaluation-") as temp_dir:
        exported_path = Path(temp_dir) / "exported-from-html.json"
        run_zipapp(
            zipapp,
            ["export", "json", artifacts["html"], "-o", str(exported_path)],
            run_dir,
        )
        exported = _read_json(exported_path)
        assert_source_equal(actual_source, exported)


def verify_run(zipapp: Path, expectation: dict[str, Any], run_dir: Path) -> None:
    """Verify expected files, source fields, computed values, and exports."""

    if not zipapp.is_file():
        raise AssertionError(f"zipapp does not exist: {zipapp}")
    if not run_dir.is_dir():
        raise AssertionError(f"run directory does not exist: {run_dir}")

    artifact_names = _expected_artifact_names(expectation)
    missing = [name for name in artifact_names if not (run_dir / name).is_file()]
    if missing:
        raise AssertionError("missing required artifacts: " + ", ".join(missing))

    artifacts = expectation["artifacts"]
    actual_source = _read_json(run_dir / artifacts["json"])
    _assert_expected_source(expectation["source"], actual_source)
    _assert_clean_validation(zipapp, artifacts["html"], run_dir)
    _assert_computed_planned_ends(zipapp, expectation["computed"], artifacts["html"], run_dir)
    _assert_exports(zipapp, expectation, run_dir, actual_source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zipapp", type=Path, required=True)
    parser.add_argument("--expectation", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expectation = load_expectation(args.expectation.resolve())
        verify_run(args.zipapp.resolve(), expectation, args.run_dir.resolve())
    except (AssertionError, OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"{expectation['scenarioId']}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
