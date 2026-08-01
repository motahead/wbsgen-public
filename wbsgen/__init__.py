"""WBS-GEN package public compatibility surface."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from html import escape
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from . import models as _models
from . import parser as _parser
from . import planner as _planner
from .render import html as _render_html
from . import update as _update
from . import validation as _validation
from .cli import main, parse_args, write_text
from .models import (
    BuildResult,
    ChartScale,
    ComputedTask,
    DisplayRow,
    Holiday,
    Milestone,
    Project,
    ProgressAnalysis,
    Task,
    WorkCalendar,
)
from .parser import *  # noqa: F401,F403
from .planner import *  # noqa: F401,F403
from .render.html import *  # noqa: F401,F403
from .update import *  # noqa: F401,F403
from .validation import *  # noqa: F401,F403

__all__ = sorted(
    {
        name
        for name in (
            "Any",
            "Path",
            "Sequence",
            "annotations",
            "argparse",
            "dataclass",
            "date",
            "escape",
            "field",
            "json",
            "main",
            "parse_args",
            "re",
            "sys",
            "timedelta",
            "urlparse",
            "write_text",
            *_models.__all__,
            *_parser.__all__,
            *_planner.__all__,
            *_render_html.__all__,
            *_update.__all__,
            *_validation.__all__,
        )
        if not name.startswith("_")
    }
)
