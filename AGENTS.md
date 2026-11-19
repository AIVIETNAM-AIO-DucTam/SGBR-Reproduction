
# Agent Instructions — SGBR Reproduction

## Project Goal
Reproduce the algorithm and experiments described in the
research paper, using Kaggle as the execution environment.

## Source of Truth
1. The original research paper.
2. The authors' official source code, when available.
3. docs/paper_spec.md
4. docs/experiment_plan.md

Do not invent missing algorithmic details.

## Responsibilities
- Claude: paper analysis, experimental design, scientific review.
- Codex: implementation, tests, notebook preparation, debugging.
- Human: approvals, execution decisions, final validation.

## Coding Rules
- Read docs/paper_spec.md before implementation.
- Prefer reproducible experiments.
- Record random seeds and dependencies.
- Never fabricate experimental results.
- Do not silently modify experimental methodology.
- Write tests for important algorithmic components.
- Keep implementation changes small and reviewable.

## Handoff Rules
After each task, report:
- Files changed
- What was implemented
- Tests executed
- Outstanding questions
- Next recommended task

## Approval Rules
Ask for human approval before changing the
algorithm specification or experimental protocol.
  