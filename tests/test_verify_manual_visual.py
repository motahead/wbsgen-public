from pathlib import Path


def test_viewports_are_the_approved_widths():
    from tools.verify_manual_visual import VIEWPORTS

    assert tuple(viewport.width for viewport in VIEWPORTS) == (375, 768, 1024, 1366)


def test_main_returns_one_when_layout_checks_report_a_violation(monkeypatch):
    from tools import verify_manual_visual

    monkeypatch.setattr(
        verify_manual_visual,
        "check_manual",
        lambda _path: ["375px: page_overflow"],
    )

    assert verify_manual_visual.main(["--manual", "MANUAL.html"]) == 1


def test_main_returns_zero_when_layout_checks_pass(monkeypatch):
    from tools import verify_manual_visual

    monkeypatch.setattr(verify_manual_visual, "check_manual", lambda _path: [])

    assert verify_manual_visual.main(["--manual", "MANUAL.html"]) == 0


def test_parse_args_reads_manual_path():
    from tools.verify_manual_visual import parse_args

    assert parse_args(["--manual", "docs/manual.html"]).manual == Path("docs/manual.html")
