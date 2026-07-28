#!/usr/bin/env python3
"""Build the WBS-GEN zipapp artifact with bundled runtime dependencies."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipapp
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "dist" / "wbsgen.pyz"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def install_runtime_dependencies(staging: Path) -> None:
    """Install pinned runtime dependencies (and their licenses) into staging."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(staging),
            "--requirement",
            str(REQUIREMENTS),
            "--quiet",
            "--disable-pip-version-check",
        ],
        check=True,
    )


def build_zipapp(target: Path = DEFAULT_TARGET, *, version: str = "development") -> Path:
    """Build a self-contained zipapp and return its path."""
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "app"
        package_target = staging / "wbsgen"
        shutil.copytree(PROJECT_ROOT / "wbsgen", package_target)
        (package_target / "version.py").write_text(
            f'"""Build-time WBS-GEN version."""\n\nVERSION = {version!r}\n',
            encoding="utf-8",
        )
        install_runtime_dependencies(staging)
        zipapp.create_archive(
            staging,
            target=target,
            main="wbsgen.__main__:main",
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="development")
    args = parser.parse_args()
    target = build_zipapp(version=args.version)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
