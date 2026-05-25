# Agent instructions (LJI blockcheck)

Cursor loads project context from:

| Path | Role |
|------|------|
| [`.cursor/rules/`](.cursor/rules/) | Always-on and file-scoped rules (`.mdc`) |
| [`.cursor/docs/PROJECT_CONTEXT.md`](.cursor/docs/PROJECT_CONTEXT.md) | Full project overview — attach with `@PROJECT_CONTEXT.md` in new chats |
| [`.cursor/rules/planning-workflow.mdc`](.cursor/rules/planning-workflow.mdc) | Synthesize → pre-mortem → plan v2 → implement (always on) |
| [`.cursor/docs/planning-workflow.md`](.cursor/docs/planning-workflow.md) | Human index for the planning gate |
| [`.cursor/specs/`](.cursor/specs/) | `proposed_plan.md` and `pre_mortem.md` |
| [`.cursor/skills/planning-gate/`](.cursor/skills/planning-gate/SKILL.md) | One-shot: **create the plan** → v1 + pre-mortem + v2 |
| [`.cursor/skills/`](.cursor/skills/) | Other project skills (e.g. Obsidian second brain) |
| Obsidian vault | `C:\Users\zekes\Obsidian Vault\LJI Histology Project` — `wiki/hot.md`, `wiki/index.md` |

### Second brain (Obsidian)

| Skill | Use when |
|-------|----------|
| `lji-wiki-query` | "From my notes…", "what do I know about…", recalling saved learnings |
| `lji-wiki-save` | Zeke states an insight, `/save`, `/save insight` |

Rule: `.cursor/rules/lji-obsidian-brain.mdc` (always on). Human index in vault: `WIKI.md`.

`CLAUDE.md` is **not** required in Cursor — its content lives in `.cursor/rules/lji-conventions.mdc`. Keep `CLAUDE.md` at the repo root only if you still use Claude Code.

**Living doc:** After each phase milestone, update `.cursor/docs/PROJECT_CONTEXT.md` Sections 4 and 10 (and the “Last updated” date).

**Quick commands**: `pytest tests/` · `python -m flake8 code/`
