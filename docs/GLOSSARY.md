# Glossary

Domain vocabulary first, then the architecture vocabulary used by `improve-codebase-architecture`.

## Domain

- **Host state** — everything on the developer's machine that the repository does not declare: environment variables, dotfiles, `PATH` entries, generated artifacts, locale, network settings, timezone.
- **Knob** — one independently restorable category of host state. Seven exist in v1: `env`, `dotfiles`, `path`, `artifacts`, `locale`, `network`, `clock`.
- **Clean state** — the minimal environment: an allowlisted env, an empty temp `HOME`, system-only `PATH`, a workspace copy with generated artifacts removed, `C` locale, best-effort blocked network proxies, and a fixed clock hint.
- **Trial** — one execution of the command under one knob set, inside a temp workspace. A trial is evidence, never a claim.
- **Verdict** — `clean`, `hidden`, `inconclusive`, or `blocked`.
- **Hidden dependency** — a host-state item whose absence makes a passing command fail.
- **Minimal sufficient set** — the smallest knob set whose restoration makes the clean trial pass. Produced by delta debugging.
- **Attribution** — the second-level minimization that names the specific variables, files, `PATH` entries, or artifact directories inside a surviving knob.
- **Evidence** — exit code, redacted stderr tail, duration, and knob set for a trial.
- **Receipt** — the portable machine-readable report bundling verdict, evidence, attribution, and confidence.
- **Trial session** — the module behind the seam between orchestration and execution. It owns the trial budget, the memoized trial cache, trial order, timeout clamping, truncation notes, and receipt assembly. Its interface is `run(spec)`, `build(...)`, `hit`, and `remaining_trials()`. Callers decide what to run; the session decides how a run is accounted for.

## Architecture vocabulary

- **Module** — anything with an interface and an implementation.
- **Interface** — everything a caller must know.
- **Depth** — leverage at the interface: a small interface hiding a lot of behavior.
- **Seam** — where an interface lives.
- **Adapter** — the concrete thing satisfying an interface at a seam.
- **Locality** — related behavior sitting close enough that a change does not scatter.
- **Leverage** — how much behavior a caller gets for how little interface it must learn.
- **Deletion test** — delete the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it earns its keep.
