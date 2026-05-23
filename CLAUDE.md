# LJI Histology Automation System - Development Guidelines

## Command Reference
- Build/Check: `python -m flake8 code/`
- Test Execution: `pytest tests/`

## Cursor (preferred in this IDE)
- Rules: `.cursor/rules/`
- Planning workflow: `.cursor/docs/planning-workflow.md`
- Specs: `.cursor/specs/proposed_plan.md`, `.cursor/specs/pre_mortem.md`
- See also: `AGENTS.md`

## Agent Operational Constraints (Anti-Bias Gate)
- **Mandatory Read**: Before executing any file generation or modification requested for a new feature, you MUST read the active spec pair: `.cursor/specs/` (Cursor) or `.claude/specs/` (Claude Code).
- **Mitigation Requirement**: You are strictly prohibited from writing implementation code until you have explicitly generated a file-by-file mitigation strategy in your terminal output addressing every failure mode identified in the pre-mortem.
- **Hardware & Environment Reality**: This project targets deterministic execution. Prioritize strict memory management, explicit OpenCV matrix deallocations, input shape assertions, and robust error handling for hardware I/O over abstract design patterns.
- **TDD Requirement**:
Write deterministic unit/integration tests for the exact edge cases or 
failure modes flagged in the pre-mortem file before modifying any core 
source code. Core source code is defined as any function that is called 
by another function (i.e. has dependents). Tests for these functions are 
mandatory and must be written before implementation.

TDD is optional for terminal/leaf functions — functions whose sole purpose 
is producing human-readable output (visualizations, printed summaries, 
diagnostic PNGs, CSV reports intended for human review). These may be 
implemented without prior tests, but must not contain logic that other 
functions depend on. If a leaf function grows to contain branching logic 
or is later called by another function, it is promoted to core and 
requires tests retroactively.
