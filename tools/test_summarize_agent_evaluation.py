"""Manual regression checks for summarize_agent_evaluation.py.

Run explicitly with ``.venv/bin/python tools/test_summarize_agent_evaluation.py``.
This file intentionally stays under tools/ because the summarizer is not a
pytest/CI quality gate.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import summarize_agent_evaluation as subject


class SummarizeEventJsonlTests(unittest.TestCase):
    def _write_jsonl(self, directory: Path, records: list[object]) -> Path:
        path = directory / "events.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        return path

    def test_event_jsonl_counts_commands_help_failures_retries_and_dry_run(self) -> None:
        records = [
            {"type": "command", "argv": ["python3", "wbsgen.pyz", "--help"], "exitCode": 0},
            {
                "type": "command",
                "argv": ["python3", "wbsgen.pyz", "task", "update", "project.html"],
                "exitCode": 2,
            },
            {
                "type": "command",
                "argv": [
                    "python3",
                    "wbsgen.pyz",
                    "task",
                    "update",
                    "project.html",
                    "--dry-run",
                ],
                "exitCode": 0,
            },
            {
                "type": "command",
                "argv": ["python3", "wbsgen.pyz", "validate", "project.html"],
                "exitCode": None,
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_jsonl(Path(temp_dir), records)
            events, unsupported_lines = subject.load_events(path, "event-jsonl")

        summary = subject.summarize_events(
            events, scenario_id="recovery-workflow-v1", unsupported_lines=unsupported_lines
        )

        self.assertEqual(summary["commandCount"], 4)
        self.assertEqual(summary["helpCommandCount"], 1)
        self.assertEqual(summary["failedCommandCount"], 1)
        self.assertEqual(summary["retryCount"], 1)
        self.assertIs(summary["dryRunUsed"], True)
        self.assertEqual(summary["unknownExitCodeCount"], 1)
        self.assertEqual(summary["unsupportedLines"], 0)

    def test_event_jsonl_counts_unknown_records_and_rejects_invalid_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            unknown_path = self._write_jsonl(directory, [{"type": "note", "text": "ignored"}])
            events, unsupported_lines = subject.load_events(unknown_path, "event-jsonl")
            invalid_path = self._write_jsonl(
                directory, [{"type": "command", "argv": "not-an-array", "exitCode": 0}]
            )

            self.assertEqual(events, [])
            self.assertEqual(unsupported_lines, 1)
            with self.assertRaisesRegex(ValueError, "argv"):
                subject.load_events(invalid_path, "event-jsonl")


class SummarizeClaudeJsonlTests(unittest.TestCase):
    def test_claude_jsonl_counts_bash_tool_use_without_retaining_content(self) -> None:
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "Bash",
                            "input": {"command": "python3 wbsgen.pyz --help"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tool-1", "is_error": False}
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "claude.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            events, unsupported_lines = subject.load_events(path, "claude-jsonl")

        summary = subject.summarize_events(
            events, scenario_id="major-workflow-v1", unsupported_lines=unsupported_lines
        )

        self.assertEqual(summary["commandCount"], 1)
        self.assertEqual(summary["helpCommandCount"], 1)
        self.assertEqual(summary["unknownExitCodeCount"], 1)
        self.assertEqual(summary["unsupportedLines"], 0)

    def test_claude_jsonl_uses_an_explicit_exit_code_when_available(self) -> None:
        records = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool-2",
                            "name": "Bash",
                            "input": {"command": "python3 wbsgen.pyz validate project.html"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-2",
                            "is_error": False,
                            "content": "validation failed\nexit=2",
                        }
                    ]
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "claude.jsonl"
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            events, unsupported_lines = subject.load_events(path, "claude-jsonl")

        summary = subject.summarize_events(
            events, scenario_id="recovery-workflow-v1", unsupported_lines=unsupported_lines
        )

        self.assertEqual(summary["failedCommandCount"], 1)
        self.assertEqual(summary["unknownExitCodeCount"], 0)


if __name__ == "__main__":
    unittest.main()
