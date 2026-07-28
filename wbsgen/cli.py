"""Command-line entry point for WBS-GEN."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Sequence

from .parser import load_json
from .gov_holidays import load_gov_holidays
from .planner import build_project_model
from .render.html import render_html
from .source import (
    SourceFormat,
    atomic_write_text,
    atomic_write_text as write_text,
    ensure_output_available,
    format_source_json,
    load_source,
    paths_refer_to_same_file,
    read_generator_version,
    with_generated_at,
    with_generator_version,
)
from .version import VERSION
from .update import (
    PROJECT_CLEAR_FIELDS,
    PROJECT_FIELD_OPTIONS,
    TASK_CLEAR_FIELDS,
    TASK_FIELD_OPTIONS,
    add_holiday,
    add_milestone,
    add_task,
    format_diff,
    format_json,
    move_task,
    remove_holiday,
    remove_milestone,
    remove_task,
    show_milestones,
    show_holidays,
    show_display,
    show_task,
    show_project,
    update_holiday,
    update_milestone,
    update_project,
    update_task,
    update_display_analysis,
    update_display_layers,
    update_display_standard,
    merge_holidays,
)
from .validation import format_validation_messages, validation_report_to_dict


def add_holidays_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared external-holidays option to a command parser."""

    parser.add_argument(
        "--holidays",
        type=Path,
        metavar="HOLIDAYS_JSON",
        help=(
            "External holidays JSON file. Fully replaces the input JSON "
            "holidays value."
        ),
    )


def add_task_field_arguments(
    parser: argparse.ArgumentParser, *, name_required: bool = False
) -> None:
    parser.add_argument("--name", required=name_required, help="Task name.")
    parser.add_argument("--assignee", help="Task assignee name.")
    parser.add_argument("--planned-start", help="Planned start date (YYYY-MM-DD).")
    parser.add_argument(
        "--planned-duration", type=int, help="Planned duration in working days."
    )
    parser.add_argument("--actual-start", help="Actual start date (YYYY-MM-DD).")
    parser.add_argument("--actual-end", help="Actual end date (YYYY-MM-DD).")
    parser.add_argument("--progress", type=int, help="Progress percentage from 0 to 100.")
    parser.add_argument("--issue", type=int, help="Issue number linked from the report.")
    parser.add_argument("--comment", help="Free-form task comment.")


def add_project_field_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="Project name.")
    parser.add_argument("--start-date", help="Project start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", help="Project end date (YYYY-MM-DD).")
    parser.add_argument("--status-date", help="Project status date (YYYY-MM-DD).")
    parser.add_argument(
        "--issue-base-url", help="Base URL used to link issue numbers in the report."
    )


def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the JSON diff without writing the input file.",
    )


def _parse_column_widths_arg(value: str) -> dict[str, int]:
    widths: dict[str, int] = {}
    for item in value.split(","):
        key, sep, raw_value = item.partition("=")
        if not sep:
            raise argparse.ArgumentTypeError(
                f"invalid --width entry: {item!r} (expected key=value)"
            )
        try:
            widths[key] = int(raw_value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"invalid --width value: {item!r} (expected integer)"
            ) from None
    return widths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wbsgen",
        description="Create, update, validate, generate, and export WBS projects.",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=160),
    )
    parser.add_argument("--version", action="version", version=f"wbsgen {VERSION}")
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        title="commands",
        description="Choose a command. Run 'wbsgen COMMAND --help' for command details.",
    )

    init_parser = commands.add_parser(
        "init",
        help="Create a minimal project JSON file.",
        description="Create a minimal project JSON file.",
    )
    init_parser.add_argument(
        "output", type=Path, metavar="OUTPUT_JSON", help="New project JSON file to write."
    )
    init_parser.add_argument("--name", default="新しいプロジェクト", help="Project name for the new JSON file.")
    init_parser.set_defaults(handler=run_init)

    template_parser = commands.add_parser(
        "template",
        help="Create a full project JSON skeleton for editing.",
        description="Create a full project JSON skeleton for editing.",
    )
    template_parser.add_argument(
        "output", type=Path, metavar="OUTPUT_JSON", help="Output path for the JSON skeleton."
    )
    template_parser.set_defaults(handler=run_template)

    generate_parser = commands.add_parser("generate", help="Generate an HTML source-of-truth from JSON.")
    generate_parser.add_argument("input_json", type=Path, metavar="INPUT_JSON")
    generate_parser.add_argument("-o", "--output", required=True, type=Path, metavar="OUTPUT_HTML")
    generate_parser.add_argument("--overwrite", action="store_true")
    add_holidays_argument(generate_parser)
    generate_parser.set_defaults(handler=run_generate)

    refresh_parser = commands.add_parser("refresh", help="Regenerate an HTML source-of-truth in place.")
    refresh_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    refresh_parser.set_defaults(handler=run_refresh)

    validate_parser = commands.add_parser("validate", help="Validate JSON or WBS-GEN HTML source data.")
    validate_parser.add_argument("input_path", type=Path, metavar="INPUT")
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(handler=run_validate)

    version_parser = commands.add_parser("version", help="Show CLI or source generator version.")
    version_parser.add_argument("input_path", type=Path, metavar="INPUT", nargs="?")
    version_parser.set_defaults(handler=run_version)

    export_parser = commands.add_parser("export", help="Export a report in another format.")
    export_commands = export_parser.add_subparsers(dest="export_command", required=True, title="commands")
    json_parser = export_commands.add_parser("json", help="Export embedded JSON from HTML.")
    json_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    json_parser.add_argument("-o", "--output", type=Path, metavar="OUTPUT_JSON")
    json_parser.add_argument("--overwrite", action="store_true")
    json_parser.set_defaults(handler=run_export_json)
    xlsx_parser = export_commands.add_parser("xlsx", help="Export JSON or HTML source data as XLSX.")
    xlsx_parser.add_argument("input_path", type=Path, metavar="INPUT")
    xlsx_parser.add_argument("-o", "--output", type=Path, required=True, metavar="OUTPUT_XLSX")
    xlsx_parser.add_argument("--day-split", type=int, choices=(1, 2, 4), default=1)
    xlsx_parser.add_argument("--overwrite", action="store_true")
    xlsx_parser.set_defaults(handler=run_export_xlsx)

    project_parser = commands.add_parser("project", help="Show or update project fields in HTML.")
    project_commands = project_parser.add_subparsers(dest="project_command", required=True, title="commands")
    project_show_parser = project_commands.add_parser("show", help="Print project fields as JSON.")
    project_show_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    project_show_parser.set_defaults(handler=run_html_command)
    project_update_parser = project_commands.add_parser("update", help="Update project fields in HTML.")
    project_update_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    add_project_field_arguments(project_update_parser)
    project_update_parser.add_argument("--clear", action="append", nargs="+", choices=sorted(PROJECT_CLEAR_FIELDS))
    add_dry_run_argument(project_update_parser)
    project_update_parser.set_defaults(handler=run_html_command)

    task_parser = commands.add_parser("task", help="Manage tasks in HTML.")
    task_commands = task_parser.add_subparsers(dest="task_command", required=True, title="commands")
    for name in ("add", "update", "show", "remove", "move"):
        task_command_parser = task_commands.add_parser(name, help=f"{name.title()} a task.")
        task_command_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
        task_command_parser.add_argument("--id", required=True)
        if name == "add":
            add_task_field_arguments(task_command_parser, name_required=True)
            add_dry_run_argument(task_command_parser)
        elif name == "update":
            add_task_field_arguments(task_command_parser)
            task_command_parser.add_argument("--clear", action="append", nargs="+", choices=sorted(TASK_CLEAR_FIELDS))
            add_dry_run_argument(task_command_parser)
        elif name == "show":
            task_command_parser.add_argument("--direct", action="store_true")
            task_command_parser.add_argument("--include-generated", action="store_true")
        elif name == "remove":
            task_command_parser.add_argument("--recursive", action="store_true")
            add_dry_run_argument(task_command_parser)
        else:
            task_command_parser.add_argument("--to", required=True, metavar="ID")
            add_dry_run_argument(task_command_parser)
        task_command_parser.set_defaults(handler=run_html_command)

    milestone_parser = commands.add_parser("milestone", help="Manage milestones in HTML.")
    milestone_commands = milestone_parser.add_subparsers(dest="milestone_command", required=True, title="commands")
    for name in ("add", "update", "show", "remove"):
        milestone_command_parser = milestone_commands.add_parser(name, help=f"{name.title()} a milestone.")
        milestone_command_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
        if name == "add":
            milestone_command_parser.add_argument("--date", required=True)
            milestone_command_parser.add_argument("--name", required=True)
            add_dry_run_argument(milestone_command_parser)
        elif name == "update":
            milestone_command_parser.add_argument("--name", required=True)
            milestone_command_parser.add_argument("--date")
            milestone_command_parser.add_argument("--new-date")
            milestone_command_parser.add_argument("--new-name")
            add_dry_run_argument(milestone_command_parser)
        elif name == "remove":
            milestone_command_parser.add_argument("--name", required=True)
            milestone_command_parser.add_argument("--date")
            add_dry_run_argument(milestone_command_parser)
        milestone_command_parser.set_defaults(handler=run_html_command)

    holiday_parser = commands.add_parser("holiday", help="Manage holidays in HTML.")
    holiday_commands = holiday_parser.add_subparsers(dest="holiday_command", required=True, title="commands")
    for name in ("add", "update", "show", "remove", "merge", "import-gov"):
        holiday_command_parser = holiday_commands.add_parser(name, help=f"{name.title()} holidays.")
        holiday_command_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
        if name == "add":
            holiday_command_parser.add_argument("--date", required=True)
            holiday_command_parser.add_argument("--name")
            add_dry_run_argument(holiday_command_parser)
        elif name == "update":
            holiday_command_parser.add_argument("--date", required=True)
            changes = holiday_command_parser.add_mutually_exclusive_group()
            changes.add_argument("--name")
            changes.add_argument("--clear", choices=("name",))
            holiday_command_parser.add_argument("--new-date")
            add_dry_run_argument(holiday_command_parser)
        elif name == "remove":
            holiday_command_parser.add_argument("--date", required=True)
            add_dry_run_argument(holiday_command_parser)
        elif name == "merge":
            holiday_command_parser.add_argument("--from", dest="holidays_json", required=True, type=Path, metavar="HOLIDAYS_JSON")
            add_dry_run_argument(holiday_command_parser)
        elif name == "import-gov":
            source = holiday_command_parser.add_mutually_exclusive_group()
            source.add_argument("--url")
            source.add_argument("--csv", dest="csv_path", type=Path, metavar="PATH")
            add_dry_run_argument(holiday_command_parser)
        holiday_command_parser.set_defaults(handler=run_html_command)

    display_parser = commands.add_parser("display", help="Show or update display settings in HTML.")
    display_commands = display_parser.add_subparsers(dest="display_command", required=True, title="commands")
    display_show_parser = display_commands.add_parser("show", help="Print display settings as JSON.")
    display_show_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    display_show_parser.set_defaults(handler=run_html_command)

    display_update_parser = display_commands.add_parser("update", help="Update display settings in HTML.")
    display_update_targets = display_update_parser.add_subparsers(
        dest="display_update_target", required=True, title="targets"
    )

    display_standard_parser = display_update_targets.add_parser(
        "standard", help="Update standard view column visibility, width, and order."
    )
    display_standard_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    display_standard_parser.add_argument("--visible")
    display_standard_parser.add_argument("--width", type=_parse_column_widths_arg)
    display_standard_parser.add_argument("--order")
    display_standard_parser.add_argument(
        "--clear", action="append", choices=("visible", "width", "order")
    )
    add_dry_run_argument(display_standard_parser)
    display_standard_parser.set_defaults(handler=run_html_command)

    display_analysis_parser = display_update_targets.add_parser(
        "analysis", help="Update analysis view column order."
    )
    display_analysis_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    display_analysis_parser.add_argument("--order")
    display_analysis_parser.add_argument("--clear", action="append", choices=("order",))
    add_dry_run_argument(display_analysis_parser)
    display_analysis_parser.set_defaults(handler=run_html_command)

    display_layers_parser = display_update_targets.add_parser(
        "layers", help="Update Gantt layer visibility."
    )
    display_layers_parser.add_argument("input_html", type=Path, metavar="INPUT_HTML")
    display_layers_parser.add_argument("--visible")
    display_layers_parser.add_argument("--clear", action="append", choices=("visible",))
    add_dry_run_argument(display_layers_parser)
    display_layers_parser.set_defaults(handler=run_html_command)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "export" and args.export_command == "json":
        if args.overwrite and args.output is None:
            parser.error("export json: --overwrite requires -o/--output")
    if args.command == "display" and args.display_command == "update":
        clear = set(args.clear or [])
        target = args.display_update_target
        if target in ("standard", "layers") and args.visible is not None and "visible" in clear:
            parser.error(f"display update {target}: --visible cannot be combined with --clear visible")
        if target == "standard" and args.width is not None and "width" in clear:
            parser.error("display update standard: --width cannot be combined with --clear width")
        if target in ("standard", "analysis") and args.order is not None and "order" in clear:
            parser.error(f"display update {target}: --order cannot be combined with --clear order")
    return args


def _clear_fields(args: argparse.Namespace) -> set[str]:
    raw = getattr(args, "clear", None) or []
    return {
        field
        for group in raw
        for field in (group if isinstance(group, list) else [group])
    }


def _display_values(args: argparse.Namespace) -> dict[str, object]:
    values: dict[str, object] = {}
    visible = getattr(args, "visible", None)
    if visible is not None:
        values["visible"] = ["*" if item == "all" else item for item in visible.split(",")]
    width = getattr(args, "width", None)
    if width is not None:
        values["width"] = width
    order = getattr(args, "order", None)
    if order is not None:
        values["order"] = order.split(",")
    return values


def _finalize_html_update(
    args: argparse.Namespace, data: dict[str, object], candidate: dict[str, object]
) -> int:
    candidate = with_generator_version(candidate)
    candidate = with_generated_at(candidate)
    html, result = render_validated_html(candidate)
    _print_validation(result, as_json=False)
    if html is None:
        return 1
    if args.dry_run:
        print(format_diff(format_source_json(data), format_source_json(candidate), args.input_html) or "No changes.")
        return 0
    atomic_write_text(args.input_html, html)
    return 0


def run_html_command(args: argparse.Namespace) -> int:
    """Run a v2 HTML show or update command through one source boundary."""

    source = _load_source_or_error(
        args.input_html, allowed=frozenset({SourceFormat.HTML})
    )
    data = source.data
    subcommand = getattr(args, f"{args.command}_command")
    if subcommand == "show":
        if args.command == "project":
            payload = show_project(data)
        elif args.command == "task":
            payload = show_task(data, args.id, direct=args.direct, include_generated=args.include_generated)
        elif args.command == "milestone":
            payload = show_milestones(data)
        elif args.command == "holiday":
            payload = show_holidays(data)
        else:
            payload = show_display(data)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    clear_fields = _clear_fields(args)
    if args.command == "project":
        candidate, _ = update_project(data, selected_update_values(args), clear_fields)
    elif args.command == "task":
        if subcommand == "add":
            candidate, _ = add_task(data, args.id, selected_update_values(args))
        elif subcommand == "update":
            candidate, _ = update_task(data, args.id, selected_update_values(args), clear_fields)
        elif subcommand == "remove":
            candidate, _ = remove_task(data, args.id, recursive=args.recursive)
        else:
            candidate, _ = move_task(data, args.id, args.to)
    elif args.command == "milestone":
        if subcommand == "add":
            candidate, _ = add_milestone(data, args.date, args.name)
        elif subcommand == "update":
            candidate, _ = update_milestone(data, args.name, args.date, args.new_date, args.new_name)
        else:
            candidate, _ = remove_milestone(data, args.name, args.date)
    elif args.command == "holiday":
        if subcommand == "add":
            candidate, _ = add_holiday(data, args.date, args.name)
        elif subcommand == "update":
            candidate, _ = update_holiday(data, args.date, args.name, args.clear == "name", new_date=args.new_date)
        elif subcommand == "remove":
            candidate, _ = remove_holiday(data, args.date)
        elif subcommand == "merge":
            supplemental = load_json(args.holidays_json, label="holidays")
            candidate, _ = merge_holidays(data, supplemental)
        else:
            supplemental = load_gov_holidays(url=args.url, csv_path=args.csv_path)
            result = build_project_model(data)
            if result.validation.has_errors:
                _print_validation(result, as_json=False)
                return 1
            if result.display_start_date is None or result.display_end_date is None:
                raise ValueError("cannot determine display range for holiday import")
            filtered = [
                item for item in supplemental["holidays"]
                if result.display_start_date <= date.fromisoformat(item["date"]) <= result.display_end_date
            ]
            candidate, _ = merge_holidays(data, {"holidays": filtered})
    else:
        target = args.display_update_target
        values = _display_values(args)
        if target == "standard":
            candidate, _ = update_display_standard(data, values, clear_fields)
        elif target == "analysis":
            candidate, _ = update_display_analysis(data, values, clear_fields)
        else:
            candidate, _ = update_display_layers(data, values, clear_fields)
    return _finalize_html_update(args, data, candidate)


def build_effective_data(input_json: Path, holidays: Path | None) -> dict:
    """Load JSON input and merge optional supplemental holidays by date."""

    source = load_source(input_json, allowed=frozenset({SourceFormat.JSON}))
    if holidays is None:
        return source.data
    supplemental = load_json(holidays, label="holidays")
    candidate, _ = merge_holidays(source.data, supplemental)
    return candidate


def render_validated_html(data: dict[str, object]):
    """Validate *data* and render its complete derived HTML document."""

    result = build_project_model(data)
    if result.validation.has_errors:
        return None, result
    return render_html(data, result), result


def _print_validation(result, *, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                validation_report_to_dict(result.validation), ensure_ascii=False, indent=2
            )
        )
        return
    for message in format_validation_messages(result.validation):
        print(message, file=sys.stderr)


def _load_source_or_error(
    path: Path, *, allowed: frozenset[SourceFormat] | None = None
):
    try:
        return load_source(path, allowed=allowed)
    except FileNotFoundError as exc:
        raise ValueError(f"input file not found: {path}") from exc


def _atomic_save_workbook(workbook, output: Path) -> None:
    """Save an XLSX workbook via a same-directory temporary file."""

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        workbook.save(temporary)
        os.replace(temporary, output)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def run_init(args: argparse.Namespace) -> int:
    name = args.name.strip()
    if not name:
        raise ValueError("project name must not be blank")
    if not args.output.parent.is_dir():
        raise ValueError(f"parent directory does not exist: {args.output.parent}")
    ensure_output_available(None, args.output, overwrite=False)
    initial_data = with_generator_version(
        {"project": {"name": name}, "tasks": []}
    )
    write_text(
        args.output,
        f"{format_source_json(initial_data)}\n",
    )
    return 0


def build_template_data() -> dict[str, object]:
    return {
        "project": {
            "name": "新しいプロジェクト",
            "startDate": "YYYY-MM-DD",
            "endDate": "YYYY-MM-DD",
            "statusDate": "YYYY-MM-DD",
            "issueBaseUrl": "https://github.com/your_account/your_repo/issues/",
        },
        "display": {
            "standard": {"columns": {"visible": ["*"], "width": {"name": 220, "assignee": 56, "comment": 220}}},
            "analysis": {"columns": {}},
            "layers": {"visible": ["*"]},
        },
        "holidays": [{"date": "YYYY-MM-DD", "name": "休日名"}],
        "milestones": [{"date": "YYYY-MM-DD", "name": "マイルストーン名"}],
        "tasks": [
            {
                "id": "1",
                "name": "タスク名",
                "assignee": "担当者名",
                "plannedStart": "YYYY-MM-DD",
                "plannedDuration": 1,
                "actualStart": "YYYY-MM-DD",
                "actualEnd": None,
                "progress": 0,
                "issue": 1,
                "comment": "タスクの補足",
            }
        ],
    }


def run_template(args: argparse.Namespace) -> int:
    if not args.output.parent.is_dir():
        raise ValueError(f"parent directory does not exist: {args.output.parent}")
    ensure_output_available(None, args.output, overwrite=False)
    template_data = with_generator_version(build_template_data())
    write_text(
        args.output,
        f"{format_source_json(template_data)}\n",
    )
    return 0


def selected_update_values(args: argparse.Namespace) -> dict[str, object]:
    field_options = (
        TASK_FIELD_OPTIONS if args.command == "task" else PROJECT_FIELD_OPTIONS
    )
    return {
        json_key: value
        for option, json_key in field_options.items()
        if (value := getattr(args, option.replace("-", "_"))) is not None
    }


def run_generate(args: argparse.Namespace) -> int:
    """Generate a new HTML source-of-truth from JSON input."""

    data = with_generator_version(build_effective_data(args.input_json, args.holidays))
    data = with_generated_at(data)
    html, result = render_validated_html(data)
    _print_validation(result, as_json=False)
    if html is None:
        return 1
    ensure_output_available(args.input_json, args.output, overwrite=args.overwrite)
    atomic_write_text(args.output, html)
    return 0


def run_refresh(args: argparse.Namespace) -> int:
    """Validate and regenerate an HTML source-of-truth in place."""

    source = _load_source_or_error(
        args.input_html, allowed=frozenset({SourceFormat.HTML})
    )
    data = with_generator_version(source.data)
    data = with_generated_at(data)
    html, result = render_validated_html(data)
    _print_validation(result, as_json=False)
    if html is None:
        return 1
    atomic_write_text(args.input_html, html)
    return 0


def run_validate(args: argparse.Namespace) -> int:
    source = _load_source_or_error(args.input_path)
    read_generator_version(source.data)
    result = build_project_model(source.data)
    _print_validation(result, as_json=args.json)
    return 1 if result.validation.has_errors else 0


def run_version(args: argparse.Namespace) -> int:
    """Print the CLI version or the source's generator metadata."""

    if args.input_path is None:
        print(VERSION)
        return 0
    source = _load_source_or_error(args.input_path)
    print(
        json.dumps(
            {
                "cliVersion": VERSION,
                "generatorVersion": read_generator_version(source.data),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def run_export_json(args: argparse.Namespace) -> int:
    source = _load_source_or_error(
        args.input_html, allowed=frozenset({SourceFormat.HTML})
    )
    restored_json = format_source_json(source.data)
    if args.output is not None:
        ensure_output_available(
            args.input_html, args.output, overwrite=args.overwrite
        )
        atomic_write_text(args.output, f"{restored_json}\n")
    else:
        print(restored_json)
    return 0


def run_export_xlsx(args: argparse.Namespace) -> int:
    source = _load_source_or_error(args.input_path)
    read_generator_version(source.data)
    result = build_project_model(source.data)
    _print_validation(result, as_json=False)
    if result.validation.has_errors:
        return 1
    ensure_output_available(args.input_path, args.output, overwrite=args.overwrite)
    from .render.xlsx import build_workbook

    workbook = build_workbook(
        result, source_label=str(args.input_path), day_split=args.day_split
    )
    _atomic_save_workbook(workbook, args.output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as exc:
        print(f"wbsgen: error: {exc}", file=sys.stderr)
        return 1
