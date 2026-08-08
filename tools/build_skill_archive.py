#!/usr/bin/env python3
"""Build the portable WBS-GEN Skill archive with reproducible ZIP metadata."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "skills" / "wbsgen"
DEFAULT_TARGET = PROJECT_ROOT / "dist" / "wbsgen-skill.zip"
REQUIRED_FILES = ("INSTALL.md", "SKILL.md")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def build_skill_archive(target: Path = DEFAULT_TARGET) -> Path:
    """Build a portable, byte-reproducible Skill archive and return its path."""
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for filename in REQUIRED_FILES:
            source = SOURCE_DIR / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            entry = ZipInfo(f"wbsgen/{filename}", date_time=ZIP_TIMESTAMP)
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, source.read_bytes(), compress_type=ZIP_DEFLATED)
    return target


def main() -> int:
    print(build_skill_archive())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
