"""Run WBS-GEN as a package."""

from __future__ import annotations

from typing import Sequence

from . import cli


def main(argv: Sequence[str] | None = None) -> int:
    return cli.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
