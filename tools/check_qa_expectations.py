from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.visual_screenshot import require_file, require_project_browser_cache  # noqa: E402
from tools.workflow_verification import (  # noqa: E402
    capture_dom_state,
    compare_dom_expectations as compare_expectations,
    derive_expected_leaf_plan_bar_ids,
    derive_expected_leaf_unplanned_ids,
    derive_expected_warning_ids,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check generated HTML against expectations derived from its input JSON.",
    )
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--input-json", type=Path, required=True)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    require_file(args.html, "HTML")
    require_file(args.input_json, "input JSON")
    require_project_browser_cache()

    import json

    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    dom_state = capture_dom_state(args.html)
    differences = compare_expectations(data, dom_state)

    if differences:
        print("check_qa_expectations: differences found:", file=sys.stderr)
        for difference in differences:
            print(f"  - {difference}", file=sys.stderr)
        return 1

    print("check_qa_expectations: no differences (QA確認OK)")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"check_qa_expectations: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
