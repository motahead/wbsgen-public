import json
import re
from argparse import _SubParsersAction
from pathlib import Path

import wbsgen
from wbsgen.cli import build_parser


def _leaf_command_names() -> set[str]:
    names: set[str] = set()

    def walk(parser, prefix: str) -> None:
        subactions = [
            action for action in parser._actions
            if isinstance(action, _SubParsersAction)
        ]
        if not subactions:
            if prefix:
                names.add(prefix)
            return
        for action in subactions:
            for name, subparser in action.choices.items():
                walk(subparser, f"{prefix} {name}".strip())

    walk(build_parser(), "")
    return names


def _manual_markup() -> tuple[str, str]:
    manual = Path("MANUAL.html").read_text(encoding="utf-8")
    return manual, re.sub(r"<script>.*?</script>", "", manual, flags=re.S)


def test_manual_internal_anchors_resolve():
    _, markup = _manual_markup()
    hrefs = set(re.findall(r'href="#([^"]+)"', markup))
    ids = set(re.findall(r'id="([^"]+)"', markup))
    assert not sorted(hrefs - ids)


def test_all_cli_commands_have_reference_entries():
    _, markup = _manual_markup()
    entries = re.findall(r'<dl class="cmd">.*?</dl>', markup, flags=re.S)
    commands = _leaf_command_names()
    assert commands
    missing = [
        command
        for command in commands
        if not any(f">{command} " in entry for entry in entries)
    ]
    assert not missing


def test_manual_documents_gov_holiday_import_risks():
    manual, _ = _manual_markup()
    for text in (
        "holiday import-gov INPUT_HTML", "--url URL", "--csv PATH", "--dry-run",
        "https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html", "リダイレクト",
        "10秒", "1 MiB", "プロキシ", "将来分の掲載遅れ",
    ):
        assert text in manual
    assert "generate</code> 自体はネットワークへアクセスしない" in manual
    section = re.search(
        r'<section id="gov-holiday-import">(?P<content>.*?)</section>',
        manual,
        flags=re.S,
    )
    assert section is not None
    assert "<h2>内閣府CSVからの休日取込</h2>" in section.group("content")
    assert "--url URL" in section.group("content")

    caution = re.search(
        r'<div class="callout">\s*<span class="ic">!</span>\s*'
        r'<div><b>重要: 内閣府CSV取込の注意</b>(?P<content>.*?)</div>\s*</div>',
        section.group("content"),
        flags=re.S,
    )
    assert caution is not None
    for text in ("--url URL", "HTTPS", "--dry-run", "--csv PATH", "HTMLを変更しない"):
        assert text in caution.group("content")


def test_manual_does_not_include_obsolete_v1_migration_section():
    manual, _ = _manual_markup()
    assert 'id="commands-migration"' not in manual
    assert "v1からの移行" not in manual


def test_manual_figures_are_embedded_without_external_images():
    manual, markup = _manual_markup()
    for figure in ("fig1", "fig2"):
        assert f'data-manual-figure="{figure}"' in markup
        assert f"<!-- manual-figure:{figure}:start -->" in manual
        assert f"<!-- manual-figure:{figure}:end -->" in manual

    assert "<svg" in re.search(
        r'<figure data-manual-figure="fig1">.*?</figure>', markup, flags=re.S
    ).group(0)
    figure2 = re.search(
        r'<figure data-manual-figure="fig2">.*?</figure>', markup, flags=re.S
    )
    assert figure2 is not None
    assert re.search(r'data:image/png;base64,[A-Za-z0-9+/=]+', figure2.group(0))
    assert not re.search(r'<img[^>]+src="https?://', markup)


def test_manual_examples_validate_with_current_schema():
    for path in (
        Path("examples/sample.json"),
        Path("examples/visual-test.json"),
        Path("examples/manual-figures-fig2.json"),
    ):
        result = wbsgen.build_project_model(json.loads(path.read_text(encoding="utf-8")))
        assert not result.validation.errors, result.validation.errors
