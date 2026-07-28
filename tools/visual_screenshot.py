from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_VIEWPORT = "1360x900"
GENERATED_SCREENSHOT_NAME = "visual-test.png"
GENERATED_WORKSPACE_BOTTOM_SCREENSHOT_NAME = "visual-test-workspace-bottom.png"
GENERATED_ANALYSIS_SCREENSHOT_NAME = "visual-test-analysis.png"
DEVICE_SCALE_FACTOR = 1
LOCAL_BROWSER_CACHE = ".cache/ms-playwright"


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int


def parse_viewport(value: str) -> Viewport:
    parts = value.lower().split("x", 1)
    if len(parts) != 2:
        raise ValueError("viewport must be WIDTHxHEIGHT")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise ValueError("viewport must be WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise ValueError("viewport must be WIDTHxHEIGHT")
    return Viewport(width=width, height=height)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate visual check screenshots for WBS-GEN.",
    )
    parser.add_argument("--generated-html", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--viewport", default=DEFAULT_VIEWPORT)
    parser.add_argument(
        "--input-json",
        type=Path,
        default=Path("examples/visual-test.json"),
    )
    return parser.parse_args(argv)


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")


def require_project_browser_cache() -> None:
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if browsers_path == LOCAL_BROWSER_CACHE:
        return
    raise ValueError(
        "PLAYWRIGHT_BROWSERS_PATH must be .cache/ms-playwright. "
        "Run `mise run visual-install`, or prefix the command with "
        "`PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright`."
    )


def apply_default_view_state(page: Any) -> None:
    page.evaluate(
        """() => {
          document.querySelectorAll('details.view-menu').forEach((menu) => { menu.open = true; });
          const holidayToggle = document.querySelector('#holiday-toggle');
          if (holidayToggle && !holidayToggle.checked) {
            holidayToggle.checked = true;
            holidayToggle.dispatchEvent(new Event('change', {bubbles: true}));
          }
        }"""
    )


def apply_clean_view_state(page: Any) -> None:
    page.evaluate(
        """() => {
          document.querySelectorAll('details.view-menu').forEach((menu) => { menu.open = false; });
          const holidayToggle = document.querySelector('#holiday-toggle');
          if (holidayToggle && holidayToggle.checked) {
            holidayToggle.checked = false;
            holidayToggle.dispatchEvent(new Event('change', {bubbles: true}));
          }
          const warningToggle = document.querySelector('#warning-toggle')
            || document.querySelector('#warning-window-toggle');
          if (warningToggle && warningToggle.checked) {
            warningToggle.checked = false;
            warningToggle.dispatchEvent(new Event('change', {bubbles: true}));
          }
        }"""
    )


def apply_workspace_bottom_view_state(page: Any) -> None:
    page.evaluate(
        """() => {
          const warningToggle = document.querySelector('#warning-toggle')
            || document.querySelector('#warning-window-toggle');
          if (warningToggle) {
            warningToggle.checked = false;
          }
          const workspace = document.querySelector('.workspace');
          if (workspace) {
            workspace.scrollTop = workspace.scrollHeight;
            workspace.scrollLeft = 0;
          }
        }"""
    )


def apply_analysis_view_state(page: Any) -> None:
    page.evaluate(
        """() => {
          const analysisTab = document.querySelector('[data-wbs-view-target="analysis"]');
          if (analysisTab) {
            analysisTab.click();
          }
        }"""
    )


def screenshot_html(
    html_path: Path,
    screenshot_path: Path,
    viewport: Viewport,
    *,
    view_state: str = "default",
    clip: dict[str, int] | None = None,
) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page(
                viewport={"width": viewport.width, "height": viewport.height},
                device_scale_factor=DEVICE_SCALE_FACTOR,
            )
            page.goto(html_path.resolve().as_uri())
            if view_state == "default":
                apply_default_view_state(page)
            elif view_state == "clean":
                apply_clean_view_state(page)
            elif view_state == "workspace-bottom":
                apply_workspace_bottom_view_state(page)
            elif view_state == "analysis":
                apply_analysis_view_state(page)
            else:
                raise ValueError(f"unknown view state: {view_state}")
            page.wait_for_timeout(250)
            screenshot_options: dict[str, Any] = {
                "path": str(screenshot_path),
                "full_page": False,
            }
            if clip is not None:
                screenshot_options["clip"] = clip
            page.screenshot(**screenshot_options)
        finally:
            browser.close()


def run(args: argparse.Namespace) -> None:
    viewport = parse_viewport(args.viewport)
    require_file(args.generated_html, "generated HTML")
    require_project_browser_cache()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    generated_screenshot = args.output_dir / GENERATED_SCREENSHOT_NAME
    generated_workspace_bottom_screenshot = (
        args.output_dir / GENERATED_WORKSPACE_BOTTOM_SCREENSHOT_NAME
    )
    generated_analysis_screenshot = args.output_dir / GENERATED_ANALYSIS_SCREENSHOT_NAME

    screenshot_html(args.generated_html, generated_screenshot, viewport)
    screenshot_html(
        args.generated_html,
        generated_workspace_bottom_screenshot,
        viewport,
        view_state="workspace-bottom",
    )
    screenshot_html(
        args.generated_html,
        generated_analysis_screenshot,
        viewport,
        view_state="analysis",
    )


def main(argv: list[str] | None = None) -> int:
    try:
        run(parse_args(argv))
    except Exception as exc:
        print(f"visual_screenshot: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
