# cleanroom

Your build passes on your laptop and fails in CI. `cleanroom` tells you which undeclared thing on your laptop the build needs.

```bash
python -m cleanroom test 'npm test'
```

```
VERDICT: HIDDEN
HIDDEN DEPENDENCIES FOUND (2)
  [env] NPM_TOKEN
  evidence: removing this knob makes the command fail; clean run exited 1
  fix: Declare the named variables in your CI workflow and in the project README.

  [path] /opt/homebrew/bin
  evidence: removing this knob makes the command fail; clean run exited 1
  fix: Add the tool to devDependencies or pin it in the project toolchain file.

minimal knob set: env, path
```

No containers, no root, no daemon, no network, no config file to write first. Python 3.10+ standard library only.

## What it does

`cleanroom` copies your repository into a temp directory, strips host state, and runs your command. Host state falls into seven knobs:

| Knob | What your laptop hides |
|---|---|
| `env` | Environment variables nobody declared |
| `dotfiles` | `~/.npmrc`, `~/.gitconfig`, and other user config |
| `path` | Global binaries available only through extra `PATH` entries |
| `artifacts` | `dist/`, `node_modules/`, and other untracked build leftovers |
| `locale` | `LANG` and `LC_*` that change parsing and sorting |
| `network` | Proxy and registry settings |
| `clock` | `TZ` and `SOURCE_DATE_EPOCH` |

The clean run uses a minimal environment, an empty temp home, a system-only `PATH`, a copy without generated artifacts, `C` locale, a fixed clock hint, and proxy variables pointed at a dead loopback port. The host run restores all seven knobs. When the host run passes and the clean run fails, delta debugging finds the smallest knob set that restores the pass. A second pass names the specific variables, config files, `PATH` entries, and artifact directories inside each surviving knob.

Every trial leaves evidence: exit code, redacted stderr, duration, and the knob set. Reports come as terminal text, JSON, Markdown, SARIF 2.1.0, and GitHub Actions annotations.

## Install and run

```bash
pip install -e .
cleanroom test 'make test'
cleanroom test 'python -m pytest' --format sarif --out .cleanroom
cleanroom knobs
cleanroom demo
cleanroom explain .cleanroom/report.json
```

`cleanroom init 'make test'` writes `.cleanroom.json`. You can skip config entirely: flags on the CLI override config values.

| Exit code | Meaning |
|---|---|
| 0 | `clean` — the command passes with no host state |
| 1 | `hidden` — undeclared host state found |
| 2 | `inconclusive` or an input error |
| 3 | `blocked` — a safety limit stopped the run |

## CI

```yaml
- name: Check for hidden machine state
  run: |
    pip install -e .
    cleanroom test 'make test' --format annotations
```

`--format annotations` prints `::error` lines that GitHub surfaces in the pull request. `--format sarif` writes results for code scanning when you pass `--out`.

## Use it from a coding agent

`skills/cleanroom/SKILL.md` follows the open Agent Skills format. An agent can read it and run `cleanroom test` before it claims a command works. The tool prints variable names, not values, and redacts known secret shapes from captured output.

## What this is not

| Tool | What it does | Where cleanroom differs |
|---|---|---|
| `docker`, `act`, `nix-shell --pure` | Isolate a build | They need a container, a daemon, or root, and they do not name the hidden dependency |
| `env -i` | Start with an empty environment | It gives no diagnosis |
| `reprotest` | Vary environment for build reproducibility studies | It does not minimize an arbitrary command's host-state dependencies down to named items |
| `direnv`, `mise` | Load declared environment | They manage declarations; cleanroom finds missing ones |
| `goss`, `serverspec`, `testinfra`, `bats` | Assert a command's effects | They check postconditions; cleanroom attributes a failure to machine state |
| `RealityLint`, `Grounded`, `docs-drift` | Compare documentation or references to source | They read text; cleanroom runs the command |
| `git bisect` | Find the commit that broke the code | It searches history; cleanroom searches host state |

Read `docs/NOVELTY.md` for the full grilling log, three rejected directions, and the conditions that would falsify the novelty claim. Search is incomplete by nature. The claim covers the combination of offline clean-room execution, minimal-sufficient-set attribution, per-item evidence, and a portable receipt.

## Safety

- Every trial runs in a temp copy. Your repository and your real home directory stay untouched.
- The clean room always owns `HOME`, `TMPDIR`, and `XDG_*`. Restoring the `env` knob cannot redirect them.
- Symlinks are skipped, oversized files are skipped, file counts and total bytes are capped.
- Commands run with `shell=False` by default. `--shell` uses an explicit `/bin/sh -c` argv and belongs only on commands you wrote.
- Timeouts kill the whole process group. Stdout and stderr reads are capped.
- Secret-looking values are redacted from captured output. Reports print variable names, not values. Treat the names as sensitive in public logs.
- Proxy variables pointed at a dead loopback port are a best-effort control, not a security boundary. The tool says so in every report.
- `--out` must stay inside the current directory.

## Limits

Windows support is best-effort. Commands that need a TTY, a running service, or real network access may return `inconclusive`. Flaky commands get a `flaky` flag and fail the verdict rather than producing a guess. Attribution stops at a hard trial budget and marks its confidence `partial`.

A 105k-star outcome depends on distribution, timing, and luck. This project optimizes for a 60-second demo and a clear verdict. It makes no promise about stars.

## Development

```bash
python -m unittest discover -s tests -v
python -m cleanroom demo
python -m cleanroom selftest
python -m cleanroom test 'python3 -m unittest discover -s tests'
```

Verification harnesses:

```bash
python tools/review_rounds.py all   # nine rounds, 53 checks
python tools/audit.py all           # static scan, fuzz, suite, selftest, dogfood
python tools/freeze.py check        # proves a refactor changed no function
```

`tools/freeze.py` rebuilds a canonical receipt and compares it byte-for-byte with `docs/GOLDEN.json`. Timings and trial order are stripped, so the hash changes only when behavior changes. The architecture refactor kept the hash at `e986644a49bd3be1fc69371c42cbefb6257b72443d0ff40b2a06a12d90683fe7`.

Documentation: `docs/PLAN.md`, `docs/NOVELTY.md`, `docs/AGENT_WORKFLOW.md`, `docs/REVIEW_LOG.md`, `docs/ARCHITECTURE_REFACTOR.md`, `docs/GLOSSARY.md`, `docs/adr/`, `SKILLS.md`, `AGENTS.md`.

MIT licensed.
