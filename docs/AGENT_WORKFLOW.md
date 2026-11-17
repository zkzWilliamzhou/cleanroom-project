# Workflow and manager gates

The work is split into specialized roles. Each role has one input, one output, and a hard acceptance gate. The manager reviews every artifact before the next role starts. A role does not mark its own work complete.

## Roles

| ID | Role | Input | Output | Acceptance gate |
|---|---|---|---|---|
| A1 | Scout | The brief | Landscape + competitor evidence | Direct equivalents named with URLs; no recommendation without a falsification test |
| A2 | Ideator | Scout report | Independent candidate list | At least 8 candidates generated before evidence review |
| A3 | Critic | Candidate list | Rejections and dissents | At least one popular idea killed; dissent recorded, not averaged away |
| A4 | Architect | Surviving concept | `PLAN.md`, knob model, non-goals | Scope is buildable in Python 3.10 stdlib; every non-goal named |
| A5 | Test Engineer | Plan | Failing test suite | Suite fails for the expected reason; RED is witnessed |
| A6 | Implementer | Plan + tests | Working package | Full suite green; no test modified to pass |
| A7 | Release Engineer | Green package | README, CI, skill, demo | The 60-second demo reproduces from a clean checkout |
| A8 | Security Auditor | Package | Findings with file and line | Every finding either fixed or explicitly accepted with a reason |
| A9 | Review Lead | Package | Nine review rounds | Each round has a command, a finding, a fix, and a re-verification |
| A10 | Architecture Refactorer | Reviewed package | Deepened modules | Golden report byte-identical before and after |
| A0 | Manager | Every artifact | Verdict | `ACCEPT` or `REJECT + rework`. No exceptions. |

## Gates

```
A1 -> A2 -> A3 -> [manager: reject weak ideas] -> A4 -> [manager: sign scope]
   -> A5 -> [manager: witness RED] -> A6 -> [manager: witness GREEN]
   -> A7 -> [manager: run demo] -> A8 -> A9 (9 rounds, each re-verified)
   -> [manager: freeze golden report] -> A10 -> [manager: compare hashes] -> ship
```

## Manager rules

1. Evidence before claims. "Should pass" is not a status. Run the command, read the full output, check the exit code.
2. No self-certification. An agent's report of success is an input, not a verdict.
3. Reject on: missing parts, fake results, tests written after code, silent scope changes, unbounded I/O, unguarded subprocesses, unredacted secrets, and any claim that a tool is novel without a competitor table.
4. Rework is unbounded. A rejected role repeats its part until the artifact meets the gate. The rejection reason is written into the log.
5. Freeze function before architecture. The final refactor may change modules and seams only. Behavior is pinned by a golden report hash.

## Rejections issued in this run

| Target | Reason | Rework |
|---|---|---|
| A1's `DocsTruth` recommendation | `RealityLint`, `Grounded`, `README-Checker`, `docs-drift` already exist | A1 rerun with an explicit competitor search; direction abandoned |
| The agent-firewall pivot | `Grounded`, `failproof`, `Open Mind` own the function | Pivot abandoned |
| A3's `enshure` recommendation | `goss`, `serverspec`, `testinfra`, `bats` own postcondition contracts | Manager overrode the decision matrix; direction abandoned |
| Review round 1 static auditor | Flagged the phrase `shell=True` inside a docstring as a real keyword. A false positive in the auditor itself | Rewritten as an AST walk; round re-run to `0 findings` |
| Review rounds 3-8 | Real defects: knob confounding, symlinked cleanup, unbounded child writes, leaked command secrets, dead config key, silent workspace truncation, overstated budget verdict | Each defect got a fix and a regression test; every round re-run to `PASS` |
| Review round 9 packaging check | Passed an `UNKNOWN-0.0.0` wheel because the check only asserted a file existed | Metadata moved to `setup.cfg`; check strengthened to inspect filename and `METADATA`; round re-run to `PASS` |

No round was closed on an agent's word. The red-green reversal harness in `REVIEW_LOG.md` proves the regression tests fail when the fixes are reversed.

## Review rounds

Nine rounds, each with a distinct failure mode: static dangerous constructs, fuzz robustness, knob partition correctness, path and symlink safety, subprocess and timeout safety, secret redaction, config and CLI edges, resource limits and determinism, and full regression plus packaging. 53 checks in total. Details and command output live in `REVIEW_LOG.md`.

## Note on execution

These roles are execution passes with explicitly separated responsibilities and hard gates, not independently running background processes. The manager carries out each pass, records its artifact and verdict, and rejects its own output when a gate fails. That is the honest description of what this environment can do.
