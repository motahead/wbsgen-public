"""Manual regression checks for verify_agent_evaluation.py.

Run explicitly with ``.venv/bin/python tools/test_verify_agent_evaluation.py``.
This file intentionally stays under tools/ because the evaluator is not a
pytest/CI quality gate.
"""

from __future__ import annotations

import unittest

from verify_agent_evaluation import _assert_expected_source


class ExpectedSourceComparisonTests(unittest.TestCase):
    def test_omitted_optional_source_containers_are_not_compared(self) -> None:
        expected = {
            "project": {"name": "既存プロジェクト"},
            "tasks": [
                {
                    "id": "1",
                    "name": "準備",
                    "plannedStart": "2026-08-03",
                    "plannedDuration": 3,
                }
            ],
        }
        actual = {
            "project": {"name": "既存プロジェクト"},
            "tasks": [
                {
                    "id": "1",
                    "name": "準備",
                    "plannedStart": "2026-08-03",
                    "plannedDuration": 3,
                }
            ],
        }

        _assert_expected_source(expected, actual)


if __name__ == "__main__":
    unittest.main()
