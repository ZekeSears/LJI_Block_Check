# Planning workflow

> **Authoritative rule:** [`.cursor/rules/planning-workflow.mdc`](../rules/planning-workflow.mdc) (`alwaysApply: true`)

This page is a short human index. Cursor agents load the `.mdc` rule automatically.

## Standard pipeline

1. **Synthesize** → `.cursor/specs/proposed_plan.md` (draft v1) — skill: `session-synthesizer`
2. **Critique** → `.cursor/specs/pre_mortem.md` — skill: `pre-mortem-critic` (includes §7 clarifications)
3. **Plan v2** → update `proposed_plan.md` to address pre-mortem; **ask user first** only if §7 has blockers; otherwise summarize findings then write v2 for verification
4. **Implement** → read both specs, mitigations, TDD, then code (user approval)

## Context files (autoload — no manual `@` required)

| File | Path |
|------|------|
| Project context | `.cursor/docs/PROJECT_CONTEXT.md` |
| Proposed plan | `.cursor/specs/proposed_plan.md` |
| Pre-mortem | `.cursor/specs/pre_mortem.md` |

## Suggested chat shortcuts

- `/plan` — synthesize or refresh the proposed plan
- `/premortem` — generate pre-mortem from the current plan
- `/implement` — gate: specs → mitigations → tests → code

Skills: `~/.cursor/skills/session-synthesizer/` and `~/.cursor/skills/pre-mortem-critic/`.
