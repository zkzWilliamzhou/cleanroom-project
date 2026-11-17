# Plan — cleanroom

Date: 2026-11-12. Decision owner: the manager (the user's delegate). Status: approved for implementation.

## North star

Build a program that could plausibly pass 105k GitHub stars. Treat that as a distribution ambition, not a promise. Stars follow instant legibility, a universal pain, and a one-command demo, in that order.

## The one-line problem

Builds pass on a developer's laptop and fail in CI because the laptop carries hidden state: an environment variable nobody declared, a global binary on `PATH`, a `~/.npmrc`, a leftover `dist/`, a warm cache, a locale, a timezone. Nobody has a tool that names that state.

## Product definition

`cleanroom` runs one command twice: once in a hermetic clean room built on the same machine (no container, no root, no network dependency), and once with host state restored. If the clean run fails while the host run passes, it minimizes the difference with delta debugging and names the smallest set of hidden dependencies that make the command pass. It reports the variable names, config files, `PATH` entries, and leftover artifacts the build silently relies on, with per-trial evidence and fix suggestions. It never modifies the user's repository or home directory.

One-command demo:

```bash
cleanroom test 'npm test'
```

Expected first-run output: `PASS`, or `HIDDEN DEPENDENCIES: env:NPM_TOKEN, path:/usr/local/bin (yarn)` plus a CI workflow snippet.

## Why this function is not already a product

See `docs/NOVELTY.md` for the full grilling log and the falsification conditions. Short version:

- Documentation-truth tools (`RealityLint`, `Grounded`, `README-Checker`, `docs-drift`) compare prose to source. Rejected.
- Agent hallucination firewalls (`Grounded`, `failproof`, `Open Mind`) validate names against a repo index. Rejected.
- Effect verifiers (`goss`, `serverspec`, `testinfra`, `bats`, `set -e`) assert postconditions. Rejected.
- Isolation tools (`docker`, `nix-shell --pure`, `act`, `env -i`, `reprotest`) isolate or perturb, but do not attribute. `reprotest` varies environment to test build reproducibility; it does not produce a minimal causal set of machine-state dependencies for an arbitrary command, offline, without containers.

The bounded claim: no located tool performs offline, rootless, container-free clean-room execution plus minimal-sufficient-set attribution of host state for arbitrary commands. This is falsifiable by finding a prior artifact with the same contract.

## Scope

In v1:

- Seven independently restorable knobs: `env`, `dotfiles`, `path`, `artifacts`, `locale`, `network`, `clock`.
- Safe workspace copies with size, count, and symlink limits. No writes to the real repo or real `HOME`.
- Delta-debugging minimizer over knobs, then second-level attribution over the items inside `env`, `dotfiles`, `artifacts`, and `path`.
- Evidence for every trial: exit code, redacted stderr tail, duration, knob set.
- Reports: terminal, JSON, Markdown, SARIF 2.1.0, GitHub Actions annotations.
- CI gate with stable exit codes; a project-local Agent Skill so coding agents can use it; a 30-second self-contained demo.
- Python 3.10+, standard library only. Linux and macOS first; Windows is best-effort.

Out of v1:

- No LLM calls, no telemetry, no network installers, no container orchestration, no VM.
- No guaranteed kernel-level network or filesystem isolation. Best-effort controls are labelled as such.
- No automatic mutation of the user's project. All fixes are suggestions.

## Milestones and gates

| # | Milestone | Gate |
|---|---|---|
| 1 | Landscape and novelty hunt | Two independent research passes; at least one candidate rejected by the manager |
| 2 | Plan, workflow, agent roles | Manager signs off on scope and non-goals |
| 3 | Failing test suite (RED) | `python -m unittest discover -s tests` fails for the expected reason |
| 4 | Core implementation (GREEN) | Full suite green, demo green, dogfooding green |
| 5 | Nine review rounds | Each round has real commands, real findings, real fixes, and a re-verification |
| 6 | Architecture deepening | Byte-identical golden report before and after the refactor |
| 7 | Release artifacts | README, CI workflow, license, skill, packaged archive |

## Acceptance criteria

- `cleanroom demo` completes and reports a known hidden dependency.
- `cleanroom test` on the tool's own repository passes clean.
- Full test suite passes with zero failures.
- Nine review rounds documented with reproducible commands.
- The final refactor changes no observable function: golden JSON report hash unchanged.
- No hardcoded secrets, no `shell=True`, no unguarded subprocess, no unbounded reads.

## Main risks

| Risk | Mitigation |
|---|---|
| Commands are flaky | Repeat trials, require unanimous results, report `flaky` instead of guessing |
| Attribution needs many runs | Trial cache, bounded trial count and total budget, explicit `partial` confidence |
| A command destroys state | All runs happen in temp copies; real `HOME` is never writable; process groups are killed on timeout |
| Secrets leak into reports | Name-only env reporting plus deterministic redaction of output and manifests |
| Someone claims network isolation | Documented as best-effort proxy controls, never as a sandbox |
| Stars | Not controllable. Optimize for legibility and a 60-second demo, then be honest |
