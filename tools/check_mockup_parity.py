from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.visual_screenshot import (  # noqa: E402
    Viewport,
    apply_analysis_view_state,
    apply_default_view_state,
    parse_viewport,
    require_file,
    require_project_browser_cache,
)
from tools.workflow_verification import (  # noqa: E402
    assert_pane_boundary_states,
    capture_pane_boundary_states,
)

DEFAULT_VIEWPORT = "1360x900"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check DOM/computed-style parity between generated HTML and the mockup.",
    )
    parser.add_argument("--generated-html", type=Path, required=True)
    parser.add_argument("--reference-html", type=Path, required=True)
    parser.add_argument("--viewport", default=DEFAULT_VIEWPORT)
    return parser.parse_args(argv)


EXTRACTION_SCRIPT = """() => {
  const rows = Array.from(document.querySelectorAll('.left-rows .wbs-row'));
  const taskRows = rows.map((row) => {
    const progressPill = row.querySelector('[data-column="progress"] .progress-pill');
    const deltaCell = row.querySelector('[data-column="delta"]');
    const delayCell = row.querySelector('[data-column="delay"]');
    const paceCell = row.querySelector('[data-column="pace"]');
    return {
      taskId: row.getAttribute('data-task-id'),
      name: (row.querySelector('.task-label') || {}).textContent || null,
      assignee: (row.querySelector('.assignee-label') || {}).textContent || null,
      comment: (row.querySelector('.comment-label') || {}).textContent || null,
      progressText: progressPill ? progressPill.textContent : null,
      progressClass: progressPill ? progressPill.className : null,
      deltaText: deltaCell ? deltaCell.textContent : null,
      deltaClass: deltaCell ? deltaCell.className : null,
      delayText: delayCell ? delayCell.textContent : null,
      paceText: paceCell ? paceCell.textContent : null,
      paceClass: paceCell ? paceCell.className : null,
    };
  });

  const headerToggles = Array.from(
    document.querySelectorAll('header.topbar .warning-toggle, header.topbar .holiday-toggle')
  ).map((el) => el.className);

  const commentHeadLabel = document.querySelector('.comment-head .column-label');
  const commentHeadTextAlign = commentHeadLabel
    ? getComputedStyle(commentHeadLabel).textAlign
    : null;

  const firstPlanBar = document.querySelector('[data-tooltip-role="plan-bar"]');
  const firstPlanBarRect = firstPlanBar
    ? {
        left: firstPlanBar.style.left,
        top: firstPlanBar.style.top,
        width: firstPlanBar.style.width,
        height: firstPlanBar.style.height,
        delayState: firstPlanBar.getAttribute('data-delay-state'),
      }
    : null;

  const analysisOnlyCell = document.querySelector('.wbs-cell.analysis-only');
  const analysisOnlyVisible = analysisOnlyCell
    ? getComputedStyle(analysisOnlyCell).display !== 'none'
    : null;

  const columnVisibilityControl = document.querySelector(
    '[data-column-visibility-toggle], [data-column-visibility-action]'
  );
  const columnVisibilityControlsDisabled = columnVisibilityControl
    ? columnVisibilityControl.disabled
    : null;

  return {
    taskRowCount: taskRows.length,
    taskRows,
    headerToggleOrder: headerToggles,
    commentHeadTextAlign,
    firstPlanBarRect,
    analysisOnlyVisible,
    columnVisibilityControlsDisabled,
  };
}"""


def extract_structured_state(page: Any) -> dict[str, Any]:
    return page.evaluate(EXTRACTION_SCRIPT)


def capture_view_states(html_path: Path, viewport: Viewport) -> dict[str, dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page(
                viewport={"width": viewport.width, "height": viewport.height},
            )
            page.goto(html_path.resolve().as_uri())
            page.wait_for_selector(".left-rows .wbs-row", timeout=5000)

            apply_default_view_state(page)
            default_state = extract_structured_state(page)

            apply_analysis_view_state(page)
            page.wait_for_function(
                "document.documentElement.dataset.wbsView === 'analysis'", timeout=5000
            )
            analysis_state = extract_structured_state(page)
        finally:
            browser.close()

    return {"default": default_state, "analysis": analysis_state}


def diff_states(
    generated: dict[str, dict[str, Any]],
    reference: dict[str, dict[str, Any]],
) -> list[str]:
    differences: list[str] = []
    for view_name in ("default", "analysis"):
        gen = generated[view_name]
        ref = reference[view_name]

        if gen["taskRowCount"] != ref["taskRowCount"]:
            differences.append(
                f"[{view_name}] task row count differs: "
                f"generated={gen['taskRowCount']} reference={ref['taskRowCount']}"
            )
            continue

        if gen["taskRowCount"] == 0:
            differences.append(f"[{view_name}] both sides have 0 task rows (cannot compare)")
            continue

        for index, (gen_row, ref_row) in enumerate(zip(gen["taskRows"], ref["taskRows"])):
            if gen_row != ref_row:
                differences.append(
                    f"[{view_name}] task row {index} differs: "
                    f"generated={gen_row} reference={ref_row}"
                )

        if gen["headerToggleOrder"] != ref["headerToggleOrder"]:
            differences.append(
                f"[{view_name}] header toggle order differs: "
                f"generated={gen['headerToggleOrder']} reference={ref['headerToggleOrder']}"
            )

        if gen["commentHeadTextAlign"] != ref["commentHeadTextAlign"]:
            differences.append(
                f"[{view_name}] comment head text-align differs: "
                f"generated={gen['commentHeadTextAlign']} reference={ref['commentHeadTextAlign']}"
            )

        if gen["firstPlanBarRect"] != ref["firstPlanBarRect"]:
            differences.append(
                f"[{view_name}] first plan bar rect differs: "
                f"generated={gen['firstPlanBarRect']} reference={ref['firstPlanBarRect']}"
            )

        if gen["analysisOnlyVisible"] != ref["analysisOnlyVisible"]:
            differences.append(
                f"[{view_name}] analysis-only column visibility differs: "
                f"generated={gen['analysisOnlyVisible']} reference={ref['analysisOnlyVisible']}"
            )

        if gen["columnVisibilityControlsDisabled"] != ref["columnVisibilityControlsDisabled"]:
            differences.append(
                f"[{view_name}] column visibility controls disabled-state differs: "
                f"generated={gen['columnVisibilityControlsDisabled']} "
                f"reference={ref['columnVisibilityControlsDisabled']}"
            )

    return differences


def run(args: argparse.Namespace) -> int:
    viewport = parse_viewport(args.viewport)
    require_file(args.generated_html, "generated HTML")
    require_file(args.reference_html, "reference HTML")
    require_project_browser_cache()

    generated_state = capture_view_states(args.generated_html, viewport)
    reference_state = capture_view_states(args.reference_html, viewport)
    differences = diff_states(generated_state, reference_state)
    for label, html_path in (("generated", args.generated_html), ("reference", args.reference_html)):
        try:
            assert_pane_boundary_states(capture_pane_boundary_states(html_path))
        except AssertionError as exc:
            differences.append(f"{label} pane boundary differs: {exc}")

    if differences:
        print("check_mockup_parity: differences found:", file=sys.stderr)
        for difference in differences:
            print(f"  - {difference}", file=sys.stderr)
        return 1

    print("check_mockup_parity: no differences")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"check_mockup_parity: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
