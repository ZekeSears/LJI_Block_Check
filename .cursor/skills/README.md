# Project skills (optional)

Cursor skills teach the agent **how** to run a workflow. Each skill is a folder with a `SKILL.md` file.

## Layout

```
.cursor/skills/
  session-synthesizer/
    SKILL.md
  pre-mortem-critic/
    SKILL.md
```

## Project vs personal

| Location | Scope |
|----------|--------|
| `.cursor/skills/` (this repo) | Shared with anyone who clones the project |
| `~/.cursor/skills/` | All your projects on this machine |

Do not copy built-in Cursor skills from `~/.cursor/skills-cursor/` — that directory is reserved.

## Migrating from Claude Code

1. Copy skill folders from `~/.claude/skills/<name>/` to `.cursor/skills/<name>/`.
2. Update paths in each `SKILL.md` (e.g. `.claude/specs/` → `.cursor/specs/`).
3. Keep the YAML `description` field — Cursor uses it to decide when to apply the skill.

## This project

| Skill | Purpose |
|-------|---------|
| `lji-wiki-save` | File stated learnings into Obsidian (`LJI Histology Project` vault) |
| `lji-wiki-query` | Answer from saved notes (hot → index → pages) |

Planning steps: `.cursor/docs/planning-workflow.md`. Global copies: `~/.cursor/skills/session-synthesizer`, `pre-mortem-critic`.
