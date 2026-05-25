---
name: lji-wiki-save
description: >
  File Zeke's stated learnings and chat insights into the LJI Obsidian vault.
  Updates concept pages or creates wiki/insights notes; maintains index, log, hot.
  Triggers on: save insight, I learned, remember this, file this to Obsidian,
  save to my notes, /save, /save insight, add to second brain, update my Obsidian notes.
---

# lji-wiki-save — File learnings to Obsidian

## Vault (required)

```
C:\Users\zekes\Obsidian Vault\LJI Histology Project
```

If missing, tell Zeke to open Obsidian vault **LJI Histology Project** or fix the path in `.cursor/rules/lji-obsidian-brain.mdc`.

## When to run

- User **states an insight** in their own words during learning
- User says `/save`, `/save insight [name]`, "save this", "add to my notes"
- After teaching, user confirms the "retain this concept" list should be persisted
- User corrects or refines an existing insight → **update** the note, do not duplicate

**Skip:** pure code tasks with no learning; content already identical in vault.

## Workflow

1. **Extract** the insight in Zeke's phrasing (preserve his words for the core bullet).
2. **Search** for existing coverage:
   - `wiki/insights/*.md`
   - `Concepts/*.md`, `Project Code/*.md`, `Learning/*.md`
   - Grep vault for key terms
3. **Choose target** (see `wiki/meta/conventions.md` in vault):
   - Best match concept/module → append under `## My insights` (create section if absent)
   - Else → `wiki/insights/<Short Title>.md`
   - Full Q&A worth keeping → `wiki/questions/<Short Title>.md`
4. **Write** with frontmatter (`type: insight`, `related`, optional `repo_file`).
5. **Update** `wiki/index.md` (add link under Insights or Questions)
6. **Prepend** `wiki/log.md`
7. **Rewrite** `wiki/hot.md` (≤500 words; latest facts + active threads)
8. **Confirm:** `Saved to [[Note Title]]` (path in vault)

## Insight section format (on concept pages)

```markdown
## My insights

### YYYY-MM-DD — one-line title

> Zeke's wording or close paraphrase.

- **Repo:** `code/phase3_router.py` → `route_comparison_hybrid` (optional)
- **Related:** [[Codebase Study Roadmap]]
```

## Duplicate policy

Merge into existing note if same topic. Offer diff summary if replacing wrong understanding.

## Do not

- Modify `lji_blockcheck` code unless asked
- Invent insights Zeke did not state or confirm
- Create duplicate roadmap pages
