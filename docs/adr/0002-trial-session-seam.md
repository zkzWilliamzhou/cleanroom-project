# ADR-0002 — Move trial-execution policy behind a Trial session seam

Date: 2026-11-12. Status: accepted. Supersedes nothing. Relates to ADR-0001.

## Decision

Trial-execution policy lives in `cleanroom/session.py` as `TrialSession`. The module owns the trial budget, the memoized trial cache, trial order, timeout clamping, truncation notes, and receipt assembly. `engine.evaluate` keeps only orchestration: full trial, clean trial, knob minimization, per-knob attribution, and verdict selection.

The interface is `run(spec)`, `build(verdict, findings, minimal_set, confidence, extra_notes)`, `hit`, and `remaining_trials()`. The adapter behind the seam is `runner.run_trial` plus a local `_Budget`.

## Why

Before the change, `evaluate()` held four closures and six module-level helpers. A change to budget policy, caching, or report notes required editing the orchestration function itself. Understanding one concept meant bouncing between `_Budget`, `_skipped`, `trial()`, `build()`, `NOTES`, and `evaluate()`. That is low locality for a module whose interface is otherwise small.

The deletion test settles it: deleting `TrialSession` does not make the complexity vanish. Budget, cache, order, clamping, and note assembly reappear inside `evaluate()` and leak toward `cli.py` and `demo.py`. The module earns its keep.

## Consequences

- The function is pinned by `docs/GOLDEN.json`. A refactor that changes a single byte of the canonical receipt is rejected. After this refactor the SHA-256 is unchanged: `e986644a49bd3be1fc69371c42cbefb6257b72443d0ff40b2a06a12d90683fe7`.
- Tests keep calling `engine.evaluate(config, source)`. No public interface changed.
- Future policy changes (adaptive budgets, different cache keys, richer receipts) touch one module.
- ADR-0001 still owns the knob partition. The session does not decide knob ownership; it only schedules trials.

## Alternatives rejected

- Split `security.py` into a `Redactor` module: creates a second adapter at the same seam without removing a caller's need to know the limits. A naming win, not a depth win. YAGNI for v1.
- Add `Config.overrides(...)` for CLI flag merging: deleting it would move twelve lines, not concentrate complexity. A shallow pass-through.
- Leave `evaluate()` as it was: rejects the deletion test and keeps six places to touch for one policy change.
