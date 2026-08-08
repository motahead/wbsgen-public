from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


LOCAL_BROWSER_CACHE = ".cache/ms-playwright"


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int


VIEWPORTS = (
    Viewport(375, 812),
    Viewport(768, 1024),
    Viewport(1024, 768),
    Viewport(1366, 900),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify MANUAL.html layout at approved viewport widths.",
    )
    parser.add_argument("--manual", type=Path, required=True)
    return parser.parse_args(argv)


def require_browser_cache() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") != LOCAL_BROWSER_CACHE:
        raise ValueError(
            "PLAYWRIGHT_BROWSERS_PATH must be .cache/ms-playwright. "
            "Run `mise run visual-install` first."
        )


def check_viewport(page, viewport: Viewport) -> list[str]:
    page.set_viewport_size({"width": viewport.width, "height": viewport.height})
    page.reload()
    page.wait_for_timeout(100)
    state = page.evaluate(
        """(width) => {
          const toc = document.querySelector('#toc');
          const toggle = document.querySelector('#toc-toggle');
          const steps = [...document.querySelectorAll('.guide-step')];
          const scrollable = [...document.querySelectorAll('pre, table')];
          const guideCodeBlocks = [...document.querySelectorAll('.guide-step pre')];
          const content = document.querySelector('.content');
          return {
            pageFits: document.documentElement.scrollWidth <= window.innerWidth,
            tocMode: width >= 1024
              ? getComputedStyle(toc).position === 'sticky'
              : Boolean(toggle),
            mobileTocToggleSticky: width >= 1024
              || getComputedStyle(toggle).position === 'sticky',
            mobileOpenTocFixed: width >= 1024 || (() => {
              toggle.click();
              const isFixed = getComputedStyle(toc).position === 'fixed';
              toggle.click();
              return isFixed;
            })(),
            visibleSteps: steps.length === 3 && steps.every(
              (step) => step.getBoundingClientRect().width > 0
            ),
            guideCodeFitsContent: guideCodeBlocks.every(
              (node) => node.clientWidth <= content.clientWidth
            ),
            scrollableContent: scrollable.every((node) => {
              const style = getComputedStyle(node);
              return node.scrollWidth <= node.clientWidth || style.overflowX === 'auto';
            }),
          };
        }""",
        viewport.width,
    )
    violations = [
        f"{viewport.width}px: {name}"
        for name, passed in state.items()
        if not passed
    ]
    return violations


def check_manual(manual_path: Path) -> list[str]:
    if not manual_path.is_file():
        raise ValueError(f"manual not found: {manual_path}")
    require_browser_cache()

    from playwright.sync_api import sync_playwright

    violations: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page()
            page.goto(manual_path.resolve().as_uri())
            for viewport in VIEWPORTS:
                violations.extend(check_viewport(page, viewport))
        finally:
            browser.close()
    return violations


def main(argv: list[str] | None = None) -> int:
    try:
        violations = check_manual(parse_args(argv).manual)
    except Exception as exc:
        print(f"verify_manual_visual: error: {exc}", file=sys.stderr)
        return 1
    if violations:
        print("verify_manual_visual: layout violations found", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    print("verify_manual_visual: 4 approved viewport widths passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
