# Agent instructions (LJI blockcheck)

Cursor loads project context from:

| Path | Role |
|------|------|
| [`.cursor/rules/`](.cursor/rules/) | Always-on and file-scoped rules (`.mdc`) |
| [`.cursor/docs/PROJECT_CONTEXT.md`](.cursor/docs/PROJECT_CONTEXT.md) | Full project overview — attach with `@PROJECT_CONTEXT.md` in new chats |
| [`.cursor/docs/planning-workflow.md`](.cursor/docs/planning-workflow.md) | Synthesize → pre-mortem → implement |
| [`.cursor/specs/`](.cursor/specs/) | `proposed_plan.md` and `pre_mortem.md` |
| [`.cursor/skills/`](.cursor/skills/) | Optional project-specific skills |

`CLAUDE.md` is **not** required in Cursor — its content lives in `.cursor/rules/lji-conventions.mdc`. Keep `CLAUDE.md` at the repo root only if you still use Claude Code.

**Living doc:** After each phase milestone, update `.cursor/docs/PROJECT_CONTEXT.md` Sections 4 and 10 (and the “Last updated” date).

**Quick commands**: `pytest tests/` · `python -m flake8 code/`
