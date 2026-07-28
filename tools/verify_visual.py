"""Generate the visual fixture and verify its structural parity with the design SSOT."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import check_mockup_parity  # noqa: E402
from tools.workflow_verification import run_zipapp  # noqa: E402

VISUAL_FIXTURE = PROJECT_ROOT / "examples" / "visual-test.json"
DEFAULT_REFERENCE = PROJECT_ROOT / "mockups" / "visual-reference.html"
DEFAULT_WORK_DIR = Path("output/visual")
GENERATED_HTML_NAME = "visual-test.html"


def _parse_html(path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "html.parser", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(
            "generated visual HTML is not parseable:\n"
            + completed.stdout
            + completed.stderr
        )


def run(zipapp: Path, work_dir: Path, reference_html: Path) -> None:
    """Recreate only the owned visual artifact directory and compare structures."""
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    generated_html = work_dir / GENERATED_HTML_NAME
    run_zipapp(zipapp.resolve(), ["validate", str(VISUAL_FIXTURE), "--json"], PROJECT_ROOT)
    run_zipapp(
        zipapp.resolve(),
        [
            "generate",
            str(VISUAL_FIXTURE),
            "-o",
            str(generated_html.resolve()),
            "--overwrite",
        ],
        PROJECT_ROOT,
    )
    _parse_html(generated_html)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ".cache/ms-playwright"
    args = check_mockup_parity.parse_args(
        [
            "--generated-html",
            str(generated_html),
            "--reference-html",
            str(reference_html),
        ]
    )
    if check_mockup_parity.run(args) != 0:
        raise AssertionError("generated visual HTML differs from the design reference")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zipapp", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--reference-html", type=Path, default=DEFAULT_REFERENCE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        run(args.zipapp, args.work_dir, args.reference_html)
    except Exception as exc:
        print(f"verify_visual: error: {exc}", file=sys.stderr)
        return 1
    print("verify_visual: structural parity passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
