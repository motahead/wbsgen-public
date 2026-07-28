from tools import verify_live_gov_holidays
import subprocess
import sys
from pathlib import Path


def test_live_verifier_delegates_to_default_loader(monkeypatch):
    monkeypatch.setattr(
        verify_live_gov_holidays, "load_gov_holidays",
        lambda **_kwargs: {"holidays": [{"date": "2026-07-20", "name": "海の日"}]},
    )
    assert verify_live_gov_holidays.run() == 0


def test_live_verifier_passes_explicit_url_to_loader(monkeypatch):
    calls = []
    monkeypatch.setattr(
        verify_live_gov_holidays, "load_gov_holidays",
        lambda **kwargs: calls.append(kwargs) or {"holidays": [{"date": "2026-07-20", "name": "海の日"}]},
    )

    assert verify_live_gov_holidays.run(url="https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv") == 0
    assert calls == [
        {"url": None, "csv_path": None},
        {"url": "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv", "csv_path": None},
    ]


def test_live_verifier_checks_default_and_explicit_default_url(monkeypatch):
    calls = []
    monkeypatch.setattr(
        verify_live_gov_holidays, "load_gov_holidays",
        lambda **kwargs: calls.append(kwargs) or {"holidays": [{"date": "2026-07-20", "name": "海の日"}]},
    )

    assert verify_live_gov_holidays.run() == 0
    assert calls == [
        {"url": None, "csv_path": None},
        {"url": verify_live_gov_holidays.DEFAULT_GOV_HOLIDAYS_URL, "csv_path": None},
    ]


def test_live_verifier_script_can_show_help_from_project_root():
    result = subprocess.run(
        [sys.executable, "tools/verify_live_gov_holidays.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
