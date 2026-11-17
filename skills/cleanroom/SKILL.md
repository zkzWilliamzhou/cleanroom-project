---
name: cleanroom
description: Verify that a command works on a clean machine and name the hidden host state it depends on. Use before claiming a build, migration, install, or test command works, or when CI fails but the command passes locally.
license: MIT
---

# cleanroom

Run this before you say "the tests pass". A zero exit code on your laptop proves nothing about a fresh machine.

## When to use

- CI fails but the same command passes locally.
- You are about to write a README install step, CI workflow, or Dockerfile.
- You are about to claim a task is complete based on a passing command.
- A coding agent has just generated a shell command and you want to know what it silently assumes.

## Commands

```bash
python -m cleanroom test 'npm test'
python -m cleanroom test 'python -m unittest discover -s tests' --format json --out .cleanroom
python -m cleanroom knobs
python -m cleanroom demo
python -m cleanroom explain .cleanroom/report.json
```

## Reading the verdict

- `clean` — the command passes with no host state. Safe to put in CI.
- `hidden` — the command needs undeclared host state. Read the attribution list and fix the project, not the report.
- `inconclusive` — the command fails even with full host state in a temp workspace. It may need a TTY, network, or a service. Do not claim success.
- `blocked` — a safety limit stopped the run. Read the reason.

## Rules

1. Never pipe untrusted remote scripts into `cleanroom` with `--shell`. Use `--shell` only for a command you wrote.
2. Reports redact secret values but print variable names. Treat the names as sensitive in public logs.
3. Network controls are best-effort proxy settings, not a sandbox. Do not describe them as isolation.
4. Evidence beats intuition. Attach the JSON receipt when you report a verdict.
5. `cleanroom` never edits your repository. Apply the suggested fixes yourself.

## Exit codes

`0` clean, `1` hidden dependencies, `2` inconclusive or error, `3` blocked by a safety limit.
