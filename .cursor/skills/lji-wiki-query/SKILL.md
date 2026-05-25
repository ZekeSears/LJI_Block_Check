---
name: lji-wiki-query
description: >
  Answer questions using Zeke's LJI Obsidian vault (second brain). Reads hot cache,
  wiki index, then relevant notes; cites wikilinks; prefers saved insights over generic CV lore.
  Triggers on: from my notes, what do I know about, based on my wiki, second brain,
  Obsidian, query quick, wiki query, what did I save about, remind me what I learned.
---

# lji-wiki-query — Read the LJI second brain

## Vault path

```
C:\Users\zekes\Obsidian Vault\LJI Histology Project
```

## Query modes

| Mode | Trigger | Read |
|------|---------|------|
| **Quick** | `query quick:` or trivial fact | `wiki/hot.md` + `wiki/index.md` only |
| **Standard** | default | hot + index + 3–7 relevant pages |
| **Deep** | `query deep:` or "everything I know about" | hot + index + all related pages + `wiki/insights/` |

## Standard workflow

1. Read `wiki/hot.md`
2. Read `wiki/index.md` — pick pages by title/description
3. Read matched pages:
   - `Learning/`, `Concepts/`, `Project Code/`
   - `wiki/insights/`, `wiki/questions/`
   - `Questions & Debugging/Solved.md` if debugging
4. Follow `[[wikilinks]]` one level deep when needed
5. **Synthesize** using **Zeke's saved framing first**; add repo detail from `lji_blockcheck` only when the wiki is thin
6. **Cite:** `(from [[Note Title]])` for each major claim from vault
7. If gap: say what is missing; offer to file after Zeke explains

## Priority order

1. `## My insights` sections (Zeke's own words)
2. `wiki/insights/` and `wiki/questions/`
3. `Learning/` roadmaps
4. `Concepts/` and `Project Code/` stubs
5. `Full Run-Down.md`
6. Repo `PROJECT_CONTEXT.md` only for **current phase status** not duplicated in vault

## Token discipline

Stop reading when the question is answered. Do not read the entire vault for narrow questions.

## If vault empty on topic

Say clearly: "No saved note on X yet." Do not pretend prior insights exist. Offer `lji-wiki-save` after Zeke explains.

## Pair with code questions

When explaining code **and** vault has related insight, lead with the saved insight, then point to `code/` files.
