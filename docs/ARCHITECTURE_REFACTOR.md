# Architecture refactor

Skill applied: `improve-codebase-architecture` (vendored from `mattpocock/skills`). Vocabulary: `docs/GLOSSARY.md` plus the skill's module / interface / depth / seam / adapter / locality / leverage terms. HTML candidate report: `architecture-review-<timestamp>.html`, written to the OS temp directory so nothing lands in the repo.

## 1. Explore

No git history exists yet, so hot spots came from the nine review rounds. `engine.py` changed in rounds 3, 5, 7, and 8; it was the most-edited module. `security.py`, `workspace.py`, `runner.py`, `config.py`, and `report.py` each changed once or twice.

Friction found:

- Understanding one concept (a trial's accounting) required bouncing between `_Budget`, `_skipped`, `trial()`, `build()`, `NOTES`, and `evaluate()`.
- `evaluate()` had a small interface but mixed four concerns inside one implementation: budget policy, memoized execution, minimization orchestration, and receipt assembly.
- Every review-round fix touched the middle of `evaluate()`. That is the signal of low locality.

Deletion test on the suspected shallow seam: deleting the proposed `TrialSession` would not make the complexity vanish; it would reappear inside `evaluate()` and leak toward `cli.py` and `demo.py`. The module earns its keep.

## 2. Candidates

| # | Candidate | Strength | Verdict |
|---|---|---|---|
| 1 | Deepen the Trial session (`session.py`) | Strong | Selected |
| 2 | Split `security.py` into a `Redactor` module | Worth exploring | Deferred: second adapter at the same seam, YAGNI |
| 3 | Add `Config.overrides(...)` for CLI merging | Speculative | Rejected by the deletion test: shallow pass-through |

The skill's process asks the user to pick a candidate. This run was told to continue to completion without further questions, so the manager named in `AGENT_WORKFLOW.md` acted as decision owner and selected candidate 1. The HTML report records the same top recommendation.

## 3. Grilling loop

| Question | Decision |
|---|---|
| What must not change? | Every observable function. `docs/GOLDEN.json` pins it. |
| What sits behind the seam? | `runner.run_trial` plus a local `_Budget`. One adapter today, so the seam is hypothetical; the session makes it real. |
| What is the interface? | `run(spec)`, `build(...)`, `hit`, `remaining_trials()`. Nothing else escapes. |
| Does the session decide knob ownership? | No. ADR-0001 owns that. The session schedules trials only. |
| Which tests survive unchanged? | All 82. They call `engine.evaluate(config, source)`, not the session. |
| What if the golden hash changes? | Reject the refactor and restore. A changed hash means a function changed. |
| Did the domain model gain a term? | Yes: **Trial session**, added to `GLOSSARY.md`. |
| Is an ADR needed? | Yes: ADR-0002 records the seam so a future review does not re-litigate it. |

Side effects applied inline: `GLOSSARY.md` gained the term, `docs/adr/0002-trial-session-seam.md` was created. No ADR conflicts exist.

## 4. What moved

`cleanroom/engine.py` went from 168 lines to 117. `cleanroom/session.py` is 106 lines and owns:

- `NOTES`
- `_Budget` (trial count, wall-clock deadline, hit flag, remaining trials/seconds)
- `_skipped`
- the memoized trial cache and trial order
- timeout clamping against the remaining budget
- truncation-note assembly
- receipt construction with limits

`evaluate()` is now a short linear decision: full trial, clean trial, `ddmin` over knobs, per-knob attribution, verdict. `ITEM_CAP`, `_lo_evidence`, and `_attribute` stay in the engine because they are attribution policy, not trial policy.

## 5. Proof that no function changed

Before the refactor:

```
python tools/freeze.py make
golden written: docs/GOLDEN.json
sha256: e986644a49bd3be1fc69371c42cbefb6257b72443d0ff40b2a06a12d90683fe7
```

After the refactor:

```
python tools/freeze.py check
golden  sha256: e986644a49bd3be1fc69371c42cbefb6257b72443d0ff40b2a06a12d90683fe7
current sha256: e986644a49bd3be1fc69371c42cbefb6257b72443d0ff40b2a06a12d90683fe7
function freeze: PASS (byte-identical)
```

`canonical_json` strips volatile timings and sorts trials and findings, so the hash changes only when behavior changes. The golden receipt covers a `hidden` verdict with four trials, one finding (`DEMO_LICENSE_KEY`), `minimal_set=["env"]`, and three notes.

Additional verification after the refactor:

- `python -m unittest discover -s tests` → 82 tests, OK.
- `python tools/review_rounds.py all` → 9/9 rounds passed.
- `python tools/freeze.py check` → byte-identical.
- Red-green reversal harness → PASS.

## 6. Manager verdict

`ACCEPT`. The modules deepened, the seam got a name and an ADR, and the frozen receipt proves the program still does exactly what it did before. No feature was added, removed, or tuned during the architecture pass.
