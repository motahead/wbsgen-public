"""Deterministic public CLI contract verification for the release zipapp."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.workflow_verification import (  # noqa: E402
    assert_dom_matches_source,
    assert_source_equal,
    assert_valid_xlsx,
    capture_dom_state,
    run_zipapp,
)

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"
SAMPLE_JSON = PROJECT_ROOT / "examples" / "sample.json"


def command_markers(html_name: Path) -> list[list[str]]:
    """Return stable representative commands for unit-level coverage of the CLI tree."""
    html = str(html_name)
    return [
        ["--version"],
        ["init", "initial.json", "--name", "初期化確認"],
        ["template", "template.json"],
        ["project", "show", html],
        ["task", "move", html, "--id", "2.2", "--to", "2.3"],
        ["milestone", "show", html],
        ["holiday", "show", html],
        ["holiday", "merge", html, "--from", "distribution-holidays.json"],
        ["holiday", "import-gov", html, "--csv", "gov-holidays.csv"],
        ["display", "show", html],
        ["export", "xlsx", html, "-o", "workflow.xlsx", "--overwrite"],
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _export_source(zipapp: Path, html: Path, output: Path, cwd: Path) -> dict[str, Any]:
    run_zipapp(
        zipapp,
        ["export", "json", html.name, "-o", output.name, "--overwrite"],
        cwd,
    )
    return _read_json(output)


def _assert_html_state(zipapp: Path, html: Path, cwd: Path) -> dict[str, Any]:
    data = _export_source(zipapp, html, cwd / "current.json", cwd)
    assert_dom_matches_source(data, capture_dom_state(html))
    return data


def _assert_show_contains(
    zipapp: Path, args: list[str], cwd: Path, expected: str
) -> None:
    completed = run_zipapp(zipapp, args, cwd)
    if expected not in completed.stdout:
        raise AssertionError(
            f"show output does not contain {expected!r}: {completed.stdout!r}"
        )


def _run_sample_contract(zipapp: Path, work_dir: Path) -> None:
    sample_json = work_dir / "sample.json"
    sample_html = work_dir / "sample.html"
    sample_export = work_dir / "sample-export.json"
    sample_xlsx = work_dir / "sample.xlsx"
    shutil.copy2(SAMPLE_JSON, sample_json)
    original = _read_json(sample_json)
    run_zipapp(zipapp, ["validate", sample_json.name, "--json"], work_dir)
    run_zipapp(
        zipapp,
        ["generate", sample_json.name, "-o", sample_html.name, "--overwrite"],
        work_dir,
    )
    run_zipapp(zipapp, ["validate", sample_html.name, "--json"], work_dir)
    exported = _export_source(zipapp, sample_html, sample_export, work_dir)
    assert_source_equal(original, exported)
    assert_dom_matches_source(exported, capture_dom_state(sample_html))
    run_zipapp(
        zipapp,
        ["export", "xlsx", sample_json.name, "-o", sample_xlsx.name, "--overwrite"],
        work_dir,
    )
    assert_valid_xlsx(
        sample_xlsx,
        project_name=original["project"]["name"],
        expected_wbs_rows=len(original["tasks"]),
    )


def _run_contract(zipapp: Path, work_dir: Path) -> None:
    fixture = work_dir / "distribution-workflow.json"
    holidays = work_dir / "distribution-holidays.json"
    gov_holidays = work_dir / "gov-holidays.csv"
    html = work_dir / "workflow.html"
    generated_with_holidays = work_dir / "workflow-with-holidays.html"
    final_xlsx = work_dir / "workflow.xlsx"

    run_zipapp(zipapp, ["--version"], work_dir)
    run_zipapp(zipapp, ["init", "initial.json", "--name", "初期化確認"], work_dir)
    if _read_json(work_dir / "initial.json")["project"]["name"] != "初期化確認":
        raise AssertionError("init did not write the requested project name")
    run_zipapp(zipapp, ["template", "template.json"], work_dir)
    template = _read_json(work_dir / "template.json")
    if template["project"]["startDate"] != "YYYY-MM-DD":
        raise AssertionError("template did not retain its editable placeholder fields")

    original = _read_json(fixture)
    external_holidays = _read_json(holidays)["holidays"]
    run_zipapp(
        zipapp,
        [
            "generate",
            fixture.name,
            "-o",
            generated_with_holidays.name,
            "--overwrite",
            "--holidays",
            holidays.name,
        ],
        work_dir,
    )
    with_holidays = _assert_html_state(zipapp, generated_with_holidays, work_dir)
    if with_holidays["holidays"] != external_holidays:
        raise AssertionError("generate --holidays did not replace input holidays")

    run_zipapp(
        zipapp,
        ["generate", fixture.name, "-o", html.name, "--overwrite"],
        work_dir,
    )
    run_zipapp(zipapp, ["validate", html.name, "--json"], work_dir)
    version = run_zipapp(zipapp, ["version", html.name], work_dir)
    if "cliVersion" not in version.stdout or "generatorVersion" not in version.stdout:
        raise AssertionError(f"version INPUT returned unexpected output: {version.stdout!r}")
    assert_source_equal(original, _assert_html_state(zipapp, html, work_dir))

    _assert_show_contains(zipapp, ["project", "show", html.name], work_dir, "配布ワークフロー検証")
    run_zipapp(zipapp, ["project", "update", html.name, "--name", "配布契約更新"], work_dir)
    if _assert_html_state(zipapp, html, work_dir)["project"]["name"] != "配布契約更新":
        raise AssertionError("project update was not persisted")

    _assert_show_contains(zipapp, ["task", "show", html.name, "--id", "1.2"], work_dir, "設計レビュー")
    run_zipapp(
        zipapp,
        ["task", "add", html.name, "--id", "2.4", "--name", "一時タスク", "--assignee", "担当者D", "--planned-start", "2026-08-24", "--planned-duration", "1", "--progress", "0"],
        work_dir,
    )
    if not any(task["id"] == "2.4" for task in _assert_html_state(zipapp, html, work_dir)["tasks"]):
        raise AssertionError("task add was not persisted")
    run_zipapp(zipapp, ["task", "update", html.name, "--id", "1.2", "--comment", "更新済み"], work_dir)
    if next(task for task in _assert_html_state(zipapp, html, work_dir)["tasks"] if task["id"] == "1.2")["comment"] != "更新済み":
        raise AssertionError("task update was not persisted")
    run_zipapp(zipapp, ["task", "move", html.name, "--id", "2.2", "--to", "2.3"], work_dir)
    if not any(task["id"] == "2.3" for task in _assert_html_state(zipapp, html, work_dir)["tasks"]):
        raise AssertionError("task move was not persisted")
    run_zipapp(zipapp, ["task", "remove", html.name, "--id", "2.4"], work_dir)
    if any(task["id"] == "2.4" for task in _assert_html_state(zipapp, html, work_dir)["tasks"]):
        raise AssertionError("task remove was not persisted")

    _assert_show_contains(zipapp, ["milestone", "show", html.name], work_dir, "設計完了")
    run_zipapp(zipapp, ["milestone", "add", html.name, "--date", "2026-08-24", "--name", "一時節目"], work_dir)
    if not any(item["name"] == "一時節目" for item in _assert_html_state(zipapp, html, work_dir)["milestones"]):
        raise AssertionError("milestone add was not persisted")
    run_zipapp(zipapp, ["milestone", "update", html.name, "--name", "一時節目", "--new-name", "更新節目"], work_dir)
    if not any(item["name"] == "更新節目" for item in _assert_html_state(zipapp, html, work_dir)["milestones"]):
        raise AssertionError("milestone update was not persisted")
    run_zipapp(zipapp, ["milestone", "remove", html.name, "--name", "更新節目"], work_dir)
    if any(item["name"] == "更新節目" for item in _assert_html_state(zipapp, html, work_dir)["milestones"]):
        raise AssertionError("milestone remove was not persisted")

    _assert_show_contains(zipapp, ["holiday", "show", html.name], work_dir, "夏季休暇")
    run_zipapp(zipapp, ["holiday", "add", html.name, "--date", "2026-08-25", "--name", "一時休日"], work_dir)
    if not any(item["date"] == "2026-08-25" for item in _assert_html_state(zipapp, html, work_dir)["holidays"]):
        raise AssertionError("holiday add was not persisted")
    run_zipapp(zipapp, ["holiday", "update", html.name, "--date", "2026-08-25", "--new-date", "2026-08-26", "--name", "更新休日"], work_dir)
    if not any(item["date"] == "2026-08-26" for item in _assert_html_state(zipapp, html, work_dir)["holidays"]):
        raise AssertionError("holiday update was not persisted")
    run_zipapp(zipapp, ["holiday", "merge", html.name, "--from", holidays.name], work_dir)
    merged = _assert_html_state(zipapp, html, work_dir)
    if not any(item == {"date": "2026-08-14", "name": "外部夏季休暇"} for item in merged["holidays"]):
        raise AssertionError("holiday merge did not replace the matching date")
    run_zipapp(zipapp, ["holiday", "import-gov", html.name, "--csv", gov_holidays.name], work_dir)
    if not any(item == {"date": "2026-08-11", "name": "山の日"} for item in _assert_html_state(zipapp, html, work_dir)["holidays"]):
        raise AssertionError("holiday import-gov did not persist the fixture holiday")
    run_zipapp(zipapp, ["holiday", "remove", html.name, "--date", "2026-08-26"], work_dir)
    if any(item["date"] == "2026-08-26" for item in _assert_html_state(zipapp, html, work_dir)["holidays"]):
        raise AssertionError("holiday remove was not persisted")

    _assert_show_contains(zipapp, ["display", "show", html.name], work_dir, "standard")
    run_zipapp(zipapp, ["display", "update", "standard", html.name, "--visible", "name,assignee,comment", "--width", "name=240,assignee=100,comment=180"], work_dir)
    _assert_html_state(zipapp, html, work_dir)
    run_zipapp(zipapp, ["display", "update", "analysis", html.name, "--order", "progress,expectedProgress,delta"], work_dir)
    _assert_html_state(zipapp, html, work_dir)
    run_zipapp(zipapp, ["display", "update", "layers", html.name, "--visible", "plan,actual"], work_dir)
    final_before_refresh = _assert_html_state(zipapp, html, work_dir)

    run_zipapp(zipapp, ["refresh", html.name], work_dir)
    final_after_refresh = _assert_html_state(zipapp, html, work_dir)
    assert_source_equal(final_before_refresh, final_after_refresh)
    run_zipapp(
        zipapp,
        ["export", "xlsx", html.name, "-o", final_xlsx.name, "--overwrite"],
        work_dir,
    )
    assert_valid_xlsx(
        final_xlsx,
        project_name=final_after_refresh["project"]["name"],
        expected_wbs_rows=len(final_after_refresh["tasks"]),
    )


def run(zipapp: Path, work_dir: Path) -> None:
    """Run the fixed release-contract workflow in its owned artifact directory."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    shutil.copy2(FIXTURE_DIR / "distribution-workflow.json", work_dir)
    shutil.copy2(FIXTURE_DIR / "distribution-holidays.json", work_dir)
    shutil.copy2(FIXTURE_DIR / "gov-holidays.csv", work_dir)
    _run_sample_contract(zipapp.resolve(), work_dir)
    _run_contract(zipapp.resolve(), work_dir)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zipapp", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "output" / "distribution")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        run(args.zipapp, args.work_dir)
    except Exception as exc:
        print(f"verify_distribution: error: {exc}", file=sys.stderr)
        return 1
    print("verify_distribution: fixed zipapp CLI contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
