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

Planning steps are documented in `.cursor/docs/planning-workflow.md`. Add skills here only if you want repo-local copies of synthesizer / critic behavior instead of relying on global skills.
