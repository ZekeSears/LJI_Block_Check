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

- **`create the plan`** (or **run planning gate**) — one chat orchestrates three steps: v1 here (with brainstorm evidence), then **two fresh subagents** (pre-mortem, then v2) that must not see the brainstorm. Skill: [`.cursor/skills/planning-gate/SKILL.md`](../skills/planning-gate/SKILL.md). Attach `@PROJECT_CONTEXT.md` + audit paths for v1 only.
- `/plan` — synthesize v1 only (`session-synthesizer`)
- `/premortem` — critique only (`pre-mortem-critic`)
- `/implement` — read v2 specs → mitigations → tests → code (after plan v2)

**Substantial work only:** trivial edits skip the full gate (see `planning-gate` skill).

Skills: `session-synthesizer`, `pre-mortem-critic`, project `planning-gate`.
