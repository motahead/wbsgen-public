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


def test_manual_and_readme_link_to_portable_skill_archive():
    manual, _ = _manual_markup()
    readme = Path("README.md").read_text(encoding="utf-8")
    url = "https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-skill.zip"

    assert url in manual
    assert url in readme


def test_manual_and_readme_explain_ai_agent_skill_value_and_installation():
    manual, _ = _manual_markup()
    readme = Path("README.md").read_text(encoding="utf-8")

    for document in (manual, readme):
        for text in (
            "AIエージェント用Skill",
            "新規WBS作成",
            "既存HTMLの更新",
            "検証エラーの回復",
            "INSTALL.md",
        ):
            assert text in document

    assert "Skill名は`wbsgen`" in readme
    assert 'Skill名は<code class="inline">wbsgen</code>' in manual


def test_skill_guidance_uses_separate_zipapp_and_follows_getting_started_steps():
    manual, _ = _manual_markup()
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "同梱zipapp" not in readme
    assert "同じ作業ディレクトリに置いた`wbsgen.pyz`" in readme
    assert manual.index("<!-- manual-figure:fig1:end -->") < manual.index(
        'id="getting-started-ai-skill"'
    )
    assert 'href="#commands">4章のAI向け操作地図（describe）' in manual
    assert "JSON形式の記入例である" in manual
    assert "wbsgen-sample.json" in manual
    assert "AIエージェント用Skillを使う場合: Skillを導入できるAIエージェント環境" in readme
    assert "`wbsgen describe`と対象コマンドの`--help`" in readme


def test_getting_started_steps_share_one_markup_contract():
    _, markup = _manual_markup()
    section = re.search(
        r'<section id="getting-started">(?P<body>.*?)</section>',
        markup,
        flags=re.S,
    )
    assert section is not None

    steps = re.findall(
        r'<article class="guide-step">(?P<body>.*?)</article>',
        section.group("body"),
        flags=re.S,
    )
    assert len(steps) == 3

    for index, step in enumerate(steps, start=1):
        assert f'<span class="guide-step__number">{index}</span>' in step
        for class_name in (
            "guide-step__title",
            "guide-step__purpose",
            "guide-step__action",
        ):
            assert f'class="{class_name}"' in step


def test_manual_uses_generated_html_accent_colors_and_accessible_toc_toggle():
    manual, markup = _manual_markup()
    for token, value in {
        "--plan": "#92c8a6",
        "--progress": "#4f936e",
        "--parent-plan": "#a8bfd7",
        "--parent-progress": "#6689ad",
        "--warning": "#a9470a",
    }.items():
        assert f"{token}: {value};" in manual

    assert 'id="toc-toggle"' in markup
    assert 'aria-controls="toc"' in markup
    assert 'aria-expanded="false"' in markup


def test_manual_prevents_ios_from_auto_scaling_guide_step_text():
    manual, _ = _manual_markup()

    assert "-webkit-text-size-adjust: 100%;" in manual
    assert "text-size-adjust: 100%;" in manual


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


def test_manual_states_network_requirement_for_gov_holiday_import():
    manual, _ = _manual_markup()

    assert (
        'インターネット接続は不要です（<code class="inline">holiday import-gov</code>'
        "で内閣府CSVを自動取得する場合を除く）"
    ) in manual


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


def test_manual_documents_browser_printing():
    manual, _ = _manual_markup()
    for text in (
        "ブラウザの印刷", "PDFとして保存", "プロジェクト名",
        "表示範囲", "基準日", "凡例", "標準", "分析",
        "用紙サイズ", "縮小率", "背景の印刷",
    ):
        assert text in manual


def test_manual_documents_task_add_auto_id_forms():
    manual, _ = _manual_markup()

    for text in (
        "--id ID | --parent-id PARENT_ID",
        "--parent-id",
        "親未指定",
        "最大番号",
        "親タスクが存在しない",
    ):
        assert text in manual
