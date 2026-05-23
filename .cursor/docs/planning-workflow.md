# Planning workflow (Claude Code → Cursor)

This project uses a **quality gate** before implementation. Customize this file with your team’s exact prompts and triggers.

## Artifacts

| File | Purpose |
|------|---------|
| `.cursor/specs/proposed_plan.md` | Engineering spec from a brainstorm or design session |
| `.cursor/specs/pre_mortem.md` | Adversarial review: failure modes, gaps, mitigations |

Legacy Claude Code path (gitignored): `.claude/specs/`. Prefer `.cursor/specs/` in Cursor.

## Stages

### 1. Synthesize → `proposed_plan.md`

**When**: After brainstorming; user says “turn this into a plan,” “write the spec,” “synthesize,” etc.

**Skill**: `session-synthesizer` (personal skill in `~/.cursor/skills/`)

**Agent behavior**:

- Produce or update `.cursor/specs/proposed_plan.md` only (no implementation).
- Include: goal, scope, architecture, dependencies, test strategy, risks, open questions.
- Mark status as **Draft — pending critic review**.


### 2. Critique → `pre_mortem.md`

**When**: Plan exists; user says “pre-mortem,” “review this plan,” “run the critic,” etc.

**Skill**: `pre-mortem-critic` (personal skill in `~/.cursor/skills/`)

**Agent behavior**:

- Read the full `.cursor/specs/proposed_plan.md` first.
- Write `.cursor/specs/pre_mortem.md` only — do **not** edit the proposed plan in place.
- Prioritize real failure modes; acknowledge what is already sound.
- End with a prioritized mitigation checklist implementers must address.


### 3. Implement

**When**: Both spec files exist and user approves implementation.

**Agent behavior**:

1. Read both spec files.
2. Output file-by-file mitigations for every pre-mortem item.
3. Write tests for flagged edge cases (core code).
4. Implement with minimal scope.

## Skills location

| Location | Use |
|----------|-----|
| `~/.cursor/skills/<name>/SKILL.md` | Personal skills (all projects) — **put synthesizer & critic here** |
| `.cursor/skills/<name>/SKILL.md` | Repo-local copy (optional; update paths to `.cursor/specs/`) |

Do **not** use `~/.cursor/skills-cursor/` — that folder is reserved for Cursor built-ins.

In each skill’s `SKILL.md`, prefer `.cursor/specs/` over `.claude/specs/` for this repo.

## Cursor chat shortcuts (suggested)

- `/plan` — synthesize or refresh `proposed_plan.md` from the current thread
- `/premortem` — generate `pre_mortem.md` from the current plan
- `/implement` — run the gate: read specs → mitigations → TDD → code

(Add your own slash commands or rule text above.)
