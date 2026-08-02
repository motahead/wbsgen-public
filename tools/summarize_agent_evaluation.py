"""Summarize explicit AI-agent evaluation logs without running an agent."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import sys
from typing import Any


@dataclass(frozen=True)
class CommandEvent:
    """One WBS-GEN command attempt, without its output content."""

    argv: tuple[str, ...]
    exit_code: int | None


def _load_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"input log does not exist: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"line {line_number}: invalid JSON") from error
        if not isinstance(record, dict):
            raise ValueError(f"line {line_number}: JSON value must be an object")
        records.append(record)
    return records


def _validate_argv(value: Any, line_number: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"line {line_number}: argv must be a non-empty string array")
    return tuple(value)


def _validate_exit_code(value: Any, line_number: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"line {line_number}: exitCode must be an integer or null")
    return value


def _load_event_jsonl(records: list[dict[str, Any]]) -> tuple[list[CommandEvent], int]:
    events: list[CommandEvent] = []
    unsupported_lines = 0
    for line_number, record in enumerate(records, start=1):
        if record.get("type") != "command":
            unsupported_lines += 1
            continue
        events.append(
            CommandEvent(
                argv=_validate_argv(record.get("argv"), line_number),
                exit_code=_validate_exit_code(record.get("exitCode"), line_number),
            )
        )
    return events, unsupported_lines


def _command_argv(command: str) -> tuple[str, ...] | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for index, token in enumerate(tokens):
        if token == "wbsgen" or token.endswith("/wbsgen.pyz") or token == "wbsgen.pyz":
            return tuple(tokens[index:])
    return None


def _tool_result_exit_code(content: dict[str, Any]) -> int | None:
    result_content = content.get("content")
    if isinstance(result_content, str):
        match = re.search(r"(?:^|\n)exit=(-?\d+)\s*$", result_content)
        if match is not None:
            return int(match.group(1))
    tool_result = content.get("tool_use_result")
    if isinstance(tool_result, dict) and tool_result.get("is_error") is True:
        return 1
    if content.get("is_error") is True:
        return 1
    return None


def _load_claude_jsonl(records: list[dict[str, Any]]) -> tuple[list[CommandEvent], int]:
    pending_commands: dict[str, tuple[str, ...]] = {}
    events: list[CommandEvent] = []
    unsupported_lines = 0
    for record in records:
        message = record.get("message")
        if not isinstance(message, dict):
            if record.get("type") in {"system", "rate_limit_event"}:
                continue
            unsupported_lines += 1
            continue
        content_items = message.get("content")
        if not isinstance(content_items, list):
            unsupported_lines += 1
            continue
        for content in content_items:
            if not isinstance(content, dict):
                unsupported_lines += 1
                continue
            if content.get("type") == "tool_use" and content.get("name") == "Bash":
                tool_id = content.get("id")
                tool_input = content.get("input")
                command = tool_input.get("command") if isinstance(tool_input, dict) else None
                if not isinstance(tool_id, str) or not isinstance(command, str):
                    unsupported_lines += 1
                    continue
                argv = _command_argv(command)
                if argv is not None:
                    pending_commands[tool_id] = argv
                continue
            if content.get("type") == "tool_result":
                tool_id = content.get("tool_use_id")
                if isinstance(tool_id, str) and tool_id in pending_commands:
                    events.append(
                        CommandEvent(
                            argv=pending_commands.pop(tool_id),
                            exit_code=_tool_result_exit_code(content),
                        )
                    )
                continue
    unsupported_lines += len(pending_commands)
    return events, unsupported_lines


def load_events(path: Path, format_name: str) -> tuple[list[CommandEvent], int]:
    """Load supported JSONL without retaining command output or conversation text."""

    records = _load_json_lines(path)
    if format_name == "event-jsonl":
        return _load_event_jsonl(records)
    if format_name == "claude-jsonl":
        return _load_claude_jsonl(records)
    raise ValueError(f"unsupported format: {format_name}")


def _verb_key(argv: tuple[str, ...]) -> tuple[str, ...]:
    if not argv:
        return ()
    words = [word for word in argv[1:] if not word.startswith("-")]
    return tuple(words[:2])


def summarize_events(
    events: list[CommandEvent], *, scenario_id: str, unsupported_lines: int
) -> dict[str, object]:
    """Return comparable operation metrics for one isolated evaluation run."""

    failed_command_count = sum(
        event.exit_code is not None and event.exit_code != 0 for event in events
    )
    retry_count = 0
    pending_retry_keys: set[tuple[str, ...]] = set()
    for event in events:
        key = _verb_key(event.argv)
        if key in pending_retry_keys:
            retry_count += 1
            pending_retry_keys.remove(key)
        if event.exit_code is not None and event.exit_code != 0:
            pending_retry_keys.add(key)
    return {
        "scenarioId": scenario_id,
        "commandCount": len(events),
        "helpCommandCount": sum("--help" in event.argv for event in events),
        "failedCommandCount": failed_command_count,
        "retryCount": retry_count,
        "dryRunUsed": any("--dry-run" in event.argv for event in events),
        "unknownExitCodeCount": sum(event.exit_code is None for event in events),
        "unsupportedLines": unsupported_lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--format", choices=("claude-jsonl", "event-jsonl"), required=True)
    parser.add_argument("--scenario-id", required=True)
    args = parser.parse_args(argv)
    try:
        events, unsupported_lines = load_events(args.input, args.format)
        summary = summarize_events(
            events, scenario_id=args.scenario_id, unsupported_lines=unsupported_lines
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
