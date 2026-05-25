---
name: planning-gate
description: >
  Run the full LJI planning quality gate with isolated subagents: synthesize proposed_plan.md v1
  (this session may use brainstorm context), then a fresh subagent for pre-mortem, then a
  fresh subagent for plan v2. Use when the user says "create the plan," "run the planning gate,"
  or approves synthesis after brainstorming. Essential: pre-mortem and v2 MUST NOT run in the
  same context as brainstorming.
---

# Planning Gate (one-shot, isolated critics)

Orchestrates:

```text
Brainstorm (this chat, may include bias)
    → Stage 1: proposed_plan.md v1 (parent or subagent WITH evidence paths)
    → Stage 2: pre_mortem.md (NEW subagent — plan + context ONLY)
    → Stage 3: proposed_plan.md v2 (NEW subagent — v1 + pre_mortem + context ONLY)
    → Handoff (parent summarizes for user)
```

Does **not** implement code unless the user then says implement.

---

## Why subagents are mandatory

The `pre-mortem-critic` skill assumes a **fresh, unbiased** reader who never saw the brainstorming session. If the same agent writes v1 and runs the pre-mortem, it will defend its own choices instead of breaking them.

**Required:**

| Stage | Who runs it | May see brainstorm? |
|-------|-------------|---------------------|
| 1 v1 synthesizer | Parent or `generalPurpose` subagent | **Yes** — evidence + chat |
| 2 pre-mortem | **Separate** `Task` subagent | **No** — only `proposed_plan.md` v1 + `PROJECT_CONTEXT.md` |
| 3 plan v2 | **Separate** `Task` subagent | **No** — only v1 plan + `pre_mortem.md` + `PROJECT_CONTEXT.md` |

Use the **Task** tool (`subagent_type=generalPurpose`). Do **not** inline pre-mortem or v2 in the parent after writing v1.

---

## Substantiality check

Run full gate only if work touches core code, ROI/pipeline behavior, or acceptance criteria. Trivial edits → tell user to implement directly.

---

## Stage 0 — Parent prepares

1. Read `.cursor/docs/PROJECT_CONTEXT.md`.
2. Collect **evidence file paths** (audit reports, design drafts) — these go into v1, not into critic prompts.
3. Confirm user topic + any approved defaults from brainstorm.

---

## Stage 1 — Synthesizer (v1)

**Runner:** Parent (or one subagent) with brainstorm + evidence.

Follow `session-synthesizer` skill. Write `.cursor/specs/proposed_plan.md` — **Status: Draft v1**.

Wait until file is saved before Stage 2.

---

## Stage 2 — Pre-mortem (isolated subagent)

**Runner:** New Task — prompt must **not** include brainstorm transcript, chat history, or evidence paths unless they are already quoted inside `proposed_plan.md`.

**Prompt template (copy and adapt):**

```text
You are the pre-mortem critic ONLY. Follow the pre-mortem-critic skill at
~/.cursor/skills/pre-mortem-critic/SKILL.md (or .cursor/skills if project-linked).

Read ONLY:
- .cursor/docs/PROJECT_CONTEXT.md
- .cursor/specs/proposed_plan.md

Do NOT read: conversation history, fix*d audit reports, brainstorm design docs, or code.

Write .cursor/specs/pre_mortem.md with full template including §7 Clarifications.
Do NOT edit proposed_plan.md.

Return: 3-sentence summary + whether §7 blocks plan v2.
```

**Parent after Stage 2:**

- Read `pre_mortem.md` §7.
- If blocking → ask user numbered questions; **stop** until answered.
- If not blocking → proceed to Stage 3 (note defaults from §7 for v2 subagent).

---

## Stage 3 — Plan v2 (isolated subagent)

**Runner:** New Task — separate from Stage 2. Must **not** see brainstorm.

**Prompt template:**

```text
You are the plan v2 reviser ONLY. Follow .cursor/rules/planning-workflow.mdc Stage 3.

Read ONLY:
- .cursor/docs/PROJECT_CONTEXT.md
- .cursor/specs/proposed_plan.md (v1)
- .cursor/specs/pre_mortem.md

Do NOT read: brainstorm chats, audit reports not cited in the plan, or code.

Tasks:
1. Resolve every 🔴 CRITICAL item from pre_mortem §6 into explicit plan text.
2. Apply §7 defaults unless pre_mortem lists blockers (parent will have confirmed).
3. Rewrite .cursor/specs/proposed_plan.md as Status: Plan v2 — approved for implementation.
4. Include Asynchronous Execution Macro if parallel tests apply.

Return: bullet list of major v2 changes vs v1.
```

**Parent after Stage 3:**

- Brief user summary (positives, top risks, v2 deltas).
- Point to spec paths and `/multitask` if present.
- Say **implement** is a separate step.

---

## What this does NOT automate

| Step | Why separate |
|------|----------------|
| Brainstorm | Human + parent chat; bias is intentional |
| Implement | Requires mitigations, TDD, code — different gate |
| Commit | User policy |

---

## New chat one-liner

```text
@PROJECT_CONTEXT.md run planning gate for [topic].
Evidence for v1 only: [paths]
```

Parent runs Stages 0→1→2 (Task)→3 (Task)→handoff.

---

## Failure modes (parent must enforce)

- **Same agent does v1 + pre-mortem** → INVALID; restart Stage 2 with Task.
- **Critic reads `fix1d_roi_audit_report.md` directly** → INVALID unless v1 quotes it; audit belongs in v1 synthesis only.
- **v2 written without reading pre_mortem** → INVALID.

---

## Optional: parallel critics

Do **not** parallelize pre-mortem and v2 (v2 depends on pre_mortem). Stage 1 test-stub tasks in plan macro may still use `/multitask` at **implement** time, not during gate.
