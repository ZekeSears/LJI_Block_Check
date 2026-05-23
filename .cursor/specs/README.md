# Specs directory

Active planning artifacts for the quality gate:

- **`proposed_plan.md`** — what to build (draft until reviewed)
- **`pre_mortem.md`** — what could go wrong and how to mitigate

Implementation agents must read both before changing core code.

## Git

These files are **tracked** by default so plans can be shared. To keep plans local-only, add to `.gitignore`:

```
.cursor/specs/proposed_plan.md
.cursor/specs/pre_mortem.md
```

## Starting a new feature

1. Clear or archive the previous pair (or rename to `proposed_plan_YYYY-MM-DD_feature.md`).
2. Run synthesize (stage 1) → fill `proposed_plan.md`.
3. Run pre-mortem (stage 2) → fill `pre_mortem.md`.
4. Implement only after you approve both documents.
