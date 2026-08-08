from pathlib import Path
from zipfile import ZipFile

from tools.build_skill_archive import build_skill_archive


def test_build_skill_archive_contains_only_portable_skill_files(tmp_path):
    archive_path = build_skill_archive(tmp_path / "wbsgen-skill.zip")

    with ZipFile(archive_path) as archive:
        assert archive.namelist() == ["wbsgen/INSTALL.md", "wbsgen/SKILL.md"]
        assert archive.read("wbsgen/SKILL.md").decode("utf-8") == (
            Path("skills/wbsgen/SKILL.md").read_text(encoding="utf-8")
        )


def test_build_skill_archive_is_byte_reproducible(tmp_path):
    first = build_skill_archive(tmp_path / "first.zip")
    second = build_skill_archive(tmp_path / "second.zip")

    assert first.read_bytes() == second.read_bytes()


def test_portable_skill_explains_discovery_and_python_command_choice():
    skill = Path("skills/wbsgen/SKILL.md").read_text(encoding="utf-8")
    install = Path("skills/wbsgen/INSTALL.md").read_text(encoding="utf-8")

    assert "description: Use when" in skill
    assert "Python command available in the environment" in skill
    assert "`.codex/skills`" in install
    assert "`.claude/skills`" in install
