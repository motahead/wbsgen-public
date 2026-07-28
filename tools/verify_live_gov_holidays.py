"""Optionally verify the live Cabinet Office holiday CSV."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from wbsgen.gov_holidays import DEFAULT_GOV_HOLIDAYS_URL, load_gov_holidays


def run(*, url: str | None = None) -> int:
    sources = (("default", None), ("explicit", url or DEFAULT_GOV_HOLIDAYS_URL))
    for label, source_url in sources:
        holidays = load_gov_holidays(url=source_url, csv_path=None)["holidays"]
        if not holidays:
            raise RuntimeError(f"Cabinet Office holiday CSV contained no holidays ({label})")
        print(f"verify_live_gov_holidays: {label} fetched {len(holidays)} holidays")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="HTTPS holiday CSV URL to verify.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(url=parse_args().url))
