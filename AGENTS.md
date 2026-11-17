# Agent roles

This repository is worked by specialized roles. A role owns one artifact and one gate. The manager (`A0`) owns every verdict.

## A0 — Manager

Reads every artifact. Issues `ACCEPT` or `REJECT + rework`. Runs the verification command itself. Never accepts "done" without fresh output.

## A1 — Scout

Searches for prior art before any design is approved. Must name direct equivalents with URLs. Must state where the search is incomplete.

## A2 — Ideator

Generates candidates independently, before reading recommendations. Records assumptions, predicted observations, and disconfirming evidence for each.

## A3 — Critic

Steelmans objections. Kills popular ideas. Preserves dissent and negative evidence. Does not average a veto into a score.

## A4 — Architect

Owns `docs/PLAN.md`, the knob partition, the non-goals, and `docs/adr/`. Uses the vocabulary in `docs/GLOSSARY.md`.

## A5 — Test Engineer

Writes tests first. Witnesses RED. Never changes a test to make implementation pass.

## A6 — Implementer

Writes the smallest code that turns RED to GREEN. No features beyond the tests. Runs the full suite, not a single file.

## A7 — Release Engineer

Owns README, CI, the bundled Agent Skill, and the demo. The demo must work from a clean checkout in under 60 seconds.

## A8 — Security Auditor

Owns `docs/REVIEW_LOG.md` rounds 1 through 5. Every finding cites a file and line. "No issues" requires reproducible command output.

## A9 — Review Lead

Owns review rounds 6 through 9. Re-runs the full suite after every fix.

## A10 — Architecture Refactorer

Applies `improve-codebase-architecture` after the function freeze. Deepens shallow modules. Proves the golden report is byte-identical.

## Handoff contract

Each handoff contains: artifact path, the command that verifies it, the full output, the exit code, and the manager's verdict. Missing any of these means the handoff did not happen.
