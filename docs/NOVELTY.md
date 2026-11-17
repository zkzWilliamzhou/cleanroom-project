# Novelty and grilling log

This file exists because the requirement was "the function of this program is not exist on the world already". That is a strong claim. The only honest way to approach it is to try to break it repeatedly.

## Independent generation (before evidence)

Ten candidate functions were generated before searching: documentation-claim verification, AI-slop linter, behavior receipts, implicit-default scanner, agent hallucination firewall, PR-description versus diff verification, environment bisection, command postcondition verification, fresh-clone falsification, and preservation runtime manifests.

## Round 1 — the recommended idea died

The first research pass recommended a documentation-claim verifier (`DocsTruth`). A targeted search found direct equivalents:

- `RealityLint` (PyPI, static deterministic README-vs-repository checker, no LLM, never executes README commands)
- `Grounded` (offline zero-dependency reference-integrity checker, Python/JS/Go/C, SARIF, HTML, agent hooks)
- `README-Checker` (undocumented env vars, dead links, invalid commands, version mismatch)
- `docs-drift` (VS Code extension, CLI, GitHub Action, git change tracking)
- `heyvhuang/review-doc-consistency` (agent skill for docs-versus-code review)
- `eshu-hq/eshu` `doctruth` (Go package for documentation claim verification)

**Manager verdict: REJECTED.** The function exists. Building it would be a duplicate with a new coat of paint.

## Round 2 — the pivot died too

The pivot was a deterministic "reality index" plus a pre-execution agent guard that rejects hallucinated paths, flags, and symbols with "did you mean" repairs. Search found:

- `gonisulaimann/Grounded` advertises itself as a "Reference Integrity Firewall for Codebases & AI Agents", offline, Python stdlib, with stale-symbol findings, "Did you mean", LSP 3.17 and stdio MCP servers, self-healing PRs, and AI-agent hooks.
- `failproof.ai` blocks invented files, tools, and commands at the `PreToolUse` hook and returns the closest real matches.
- `Open Mind` builds a source-traceable, deterministic knowledge index for agents with an MCP server.

**Manager verdict: REJECTED.** The function exists, down to the "did you mean" repair and the MCP server.

## Round 3 — the second research recommendation died

The second research pass recommended a command postcondition verifier (`enshure`). Its own report only checked `mvdan/sh` and `set -e`, which was too shallow. The grilling found the actual category:

- `goss` / `dgoss`: YAML contracts asserting file existence, file content, command output, and ports.
- `serverspec`, `inspec`, `testinfra`: resource assertions over files, packages, and command output.
- `bats-core`: assertions on command exit status and stdout.
- Ordinary test frameworks: `assert os.path.exists(...)`.

**Manager verdict: REJECTED.** "Declare expected effects, run command, assert them" is a mature category. The research score of 4.40/5 for novelty was wrong, and the manager overrides it.

## What survived

| Adjacent tool | What it does | What it does not do |
|---|---|---|
| `env -i` / `nix-shell --pure` / `guix environment --pure` | Start with a clean environment | Attribute a failure to the smallest set of host-state items |
| `docker`, `act`, ephemeral CI runners | Reproduce a clean machine | Work offline, rootless, container-free, and explain the delta |
| `reprotest` | Vary environment to detect build reproducibility problems | Produce a minimal causal set of hidden dependencies for an arbitrary command, with per-item evidence and fix suggestions |
| `direnv`, `mise` | Load declared environment | Detect undeclared environment |
| `git bisect` | Binary-search code history for a regression | Operate on machine state instead of commits |
| `strace`, `bubblewrap`, eBPF | Observe or sandbox syscalls | Give a portable, zero-dep, no-root verdict for a normal developer |

**The bounded novelty claim.** No located tool combines (a) hermetic same-machine execution without containers or root, (b) delta-debugging minimization over independently restorable host-state knobs, (c) second-level attribution down to named environment variables, config files, `PATH` entries, and leftover artifacts, and (d) a portable CI-ready evidence report. The claim is about this combination and artifact, not about "nobody ever ran a command in a clean environment".

**How to falsify it.** Find a prior generally available CLI that takes an arbitrary command, runs it in a clean room without containers or root, and prints the minimal set of host-state items responsible for a clean-run failure. If that exists, this claim is void.

## Where the claim is weakest

1. Search is incomplete; private, recent, or poorly indexed repos will not appear.
2. `reprotest` plus a hand-written bisect script could approximate the workflow. No dedicated product was located, but "could be assembled" is a real objection.
3. Some star counts and repo descriptions in the search results came from aggregator sites with inconsistent figures. They are treated as evidence of existence, not as authoritative metrics.
4. Best-effort network controls are not a security boundary. The tool says so in its output.
5. 105k stars is a distribution outcome. Nothing in the novelty claim predicts it.

## Decision

Proceed with the clean-room verifier. Keep the claim narrow, state the adjacency table in the README, and let the working demo carry the argument.
