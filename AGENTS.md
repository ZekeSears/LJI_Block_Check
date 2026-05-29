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

## Cursor Cloud specific instructions

This repo is a **batch Python CV pipeline** (no web server, Docker, or `docker compose`). Standard commands are in `.cursor/rules/lji-conventions.mdc` and `CLAUDE.md`.

### Dependencies

- **Python 3.10+** with `pip install -r requirements.txt` (OpenCV, NumPy, SciPy, pandas, pytest, barcode libs).
- Optional **venv** at `venv/`: `code/project_runtime.py` re-execs into it when present; Cloud VMs can use system Python + `~/.local` installs instead.
- **`iphone_images/`** JPEG library is **gitignored**. Default `pytest tests/` uses synthetic fixtures only; two tests fail without real JPEGs (`test_set04_golden_bbox`, `test_list_jpeg_paths_includes_uppercase_extension`). Full CV E2E needs populated `iphone_images/` per `iphone_images/README.md`.
- **System barcode libs** (`libdmtx`, `libzbar`) are optional for most unit tests; run `python code/phase35_setup_check.py` to verify. Linux: `sudo apt install libdmtx0b libzbar0`.

### Lint and tests

| Command | Notes |
|---------|--------|
| `python3 -m flake8 code/` | Often exits **1** due to many pre-existing E501 line-length warnings; still the project lint entrypoint. |
| `pytest tests/` | Default suite; `pytest.ini` ignores `tests/integration/`. Expect **~179 passed**, **2 failed** without `iphone_images/`. |
| `pytest tests/ tests/integration/ -v` | Full integration; skips when no iPhone JPEGs. |

### Running the application

There is no long-running service. Main batch entry points:

- `python code/phase3_pipeline.py` or `python run_phase3_pipeline.py` — cross-modal matching (requires `iphone_images/`).
- `python generate_test_images.py` — synthetic `test_images/` for offline demos.
- `python test_real_images.py` — legacy matcher smoke test (needs `test_images/real/` BIRL JPEGs).

**Quick hello-world without iPhone photos:** `python generate_test_images.py`, then run `shape_matcher.run_comparison` on `test_images/realistic_0_block.png` vs `test_images/realistic_0_slide_HE.png` (MATCH) vs a `wrong_*` pair (REJECT).

Committed artifacts under `phase3_outputs/pipeline_run/` let some integration tests run without re-running the pipeline.
