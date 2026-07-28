#!/usr/bin/env python3
"""Compatibility wrapper for WBS-GEN."""

from __future__ import annotations

from wbsgen.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
