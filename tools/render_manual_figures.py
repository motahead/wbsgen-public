from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


MERMAID_CLI = "npm:@mermaid-js/mermaid-cli@11.12.0"
FIGURE_GENERATED_AT = "2026-01-01 00:00"
FIGURE_DIR = Path("docs/manual-figures")
MANUAL_PATH = Path("MANUAL.html")
MANIFEST_PATH = FIGURE_DIR / "manifest.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def figure_paths() -> dict[str, Path]:
    return {
        "fig1_mmd": FIGURE_DIR / "fig1.mmd",
        "fig1_svg": FIGURE_DIR / "fig1.svg",
        "fig2_json": Path("examples/manual-figures-fig2.json"),
        "fig2_html": FIGURE_DIR / "fig2.html",
        "fig2_png": FIGURE_DIR / "fig2.png",
    }


def source_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {
        name: hashlib.sha256(paths[name].read_bytes()).hexdigest()
        for name in ("fig1_mmd", "fig2_json")
    }


def embed_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def figure_markup(name: str, paths: dict[str, Path]) -> str:
    if name == "fig1":
        body = paths["fig1_svg"].read_text(encoding="utf-8")
        caption = "FIG. 1 — 編集経路と出力"
    elif name == "fig2":
        body = (
            '<img alt="リリース計画の実際のWBS・ガント全体画面。メニューとウィンドウを閉じた状態" '
            f'src="{embed_data_uri(paths["fig2_png"])}">'
        )
        caption = "FIG. 2 — 実HTMLによる画面全体"
    else:
        raise ValueError(f"unknown manual figure: {name}")

    return (
        f'  <figure data-manual-figure="{name}">\n'
        f'    <div class="fig-body">{body}</div>\n'
        f'    <figcaption><span>{caption}</span></figcaption>\n'
        "  </figure>"
    )


def embed_figures(manual: str, paths: dict[str, Path]) -> str:
    for name in ("fig1", "fig2"):
        start = f"<!-- manual-figure:{name}:start -->"
        end = f"<!-- manual-figure:{name}:end -->"
        pattern = rf"({re.escape(start)})\n.*?\n(\s*{re.escape(end)})"
        replacement = rf"\1\n{figure_markup(name, paths)}\n\2"
        manual, count = re.subn(pattern, replacement, manual, count=1, flags=re.S)
        if count != 1:
            raise ValueError(f"manual figure marker is missing or duplicated: {name}")
    return manual


def write_manifest(paths: dict[str, Path]) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(source_hashes(paths), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def outputs_are_current(paths: dict[str, Path]) -> bool:
    required = (
        paths["fig1_mmd"], paths["fig2_json"],
        paths["fig1_svg"], paths["fig2_html"], paths["fig2_png"],
        MANIFEST_PATH, MANUAL_PATH,
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        expected_manual = embed_figures(MANUAL_PATH.read_text(encoding="utf-8"), paths)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return manifest == source_hashes(paths) and expected_manual == MANUAL_PATH.read_text(encoding="utf-8")


def mermaid_command(source: Path, output: Path) -> list[str]:
    return [
        "mise", "exec", MERMAID_CLI, "--", "mmdc",
        "-i", str(source), "-o", str(output),
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the self-contained manual figures.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def generate_html(input_json: Path, output_html: Path) -> None:
    from wbsgen import build_project_model, render_html
    from wbsgen.source import with_generated_at

    data = json.loads(input_json.read_text(encoding="utf-8"))
    result = build_project_model(data)
    if result.validation.has_errors:
        raise ValueError("manual figure source JSON is invalid")
    html = render_html(with_generated_at(data, FIGURE_GENERATED_AT), result)
    output_html.write_text(
        "\n".join(line.rstrip() for line in html.splitlines()) + "\n",
        encoding="utf-8",
    )


def generate_screenshot(
    input_html: Path,
    output_png: Path,
    *,
    width: int = 1360,
    height: int,
) -> None:
    from tools.visual_screenshot import Viewport, screenshot_html

    screenshot_html(
        input_html,
        output_png,
        Viewport(width=1360, height=900),
        view_state="clean",
        clip={"x": 0, "y": 0, "width": width, "height": height},
    )


def run(args: argparse.Namespace) -> int:
    paths = figure_paths()
    if args.check:
        return 0 if outputs_are_current(paths) else 1

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(mermaid_command(paths["fig1_mmd"], paths["fig1_svg"]), check=True)
    generate_html(paths["fig2_json"], paths["fig2_html"])
    generate_screenshot(paths["fig2_html"], paths["fig2_png"], height=500)
    MANUAL_PATH.write_text(
        embed_figures(MANUAL_PATH.read_text(encoding="utf-8"), paths),
        encoding="utf-8",
    )
    write_manifest(paths)
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
