# WBS-GEN Skill installation

`wbsgen-skill.zip` contains a single `wbsgen/` Skill directory. WBS-GEN is
available as both the CLI zipapp (`wbsgen.pyz`) and this AI-agent Skill.

## Install

1. Download `wbsgen.pyz` and `wbsgen-skill.zip` into an empty working directory.
2. Extract the archive into the Skill search path selected by your AI product.
3. Restart or reload that product if its official instructions require it.
4. Give the agent the working directory containing `wbsgen.pyz` and the project files it will operate on.

The Skill itself is environment-independent. Follow the current official
installation instructions for your Codex or Claude Code environment when they
differ from the examples below.

## Temporary project examples

For a temporary working directory, these project-local paths were used in the
WBS-GEN evaluation: use `.codex/skills` for Codex or `.claude/skills` for
Claude Code.

```sh
# Codex
mkdir -p .codex/skills
unzip wbsgen-skill.zip -d .codex/skills

# Claude Code
mkdir -p .claude/skills
unzip wbsgen-skill.zip -d .claude/skills
```

Do not copy this archive into a WBS-GEN repository's internal `.codex/` or `.claude/` directory. Those directories are development assets, not the portable distribution interface.

After installation, the agent uses `wbsgen describe` and command-specific
`--help` from that zipapp to determine the available operations.
