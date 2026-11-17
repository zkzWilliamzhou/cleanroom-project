# ADR-0001 — Partition host state into independent knobs

Date: 2026-11-12. Status: accepted.

## Decision

Host state is split into seven knobs that can be restored independently: `env`, `dotfiles`, `path`, `artifacts`, `locale`, `network`, `clock`. Environment variables are partitioned by ownership so knobs do not confound each other. `locale` owns `LANG`/`LC_*`; `path` owns `PATH`; `network` owns proxy and registry variables; `clock` owns `TZ` and `SOURCE_DATE_EPOCH`; `env` owns everything else except `HOME` and `TMPDIR`, which the clean room always controls.

## Why

Attribution only works if restoring one knob does not silently restore another. A shared "full environment" flag would make every minimization result ambiguous. The partition makes a leave-one-out trial meaningful evidence.

## Consequences

- A trial is a pure function of a knob set plus a fixed workspace snapshot.
- Trial results can be cached by knob set.
- The clean room always owns `HOME`, `TMPDIR`, and `XDG_*`, so no trial can write to the real home directory.
- Best-effort network control sets proxies to a dead loopback port. It is not a security boundary and is documented that way.

## Alternatives rejected

- One boolean "pure" flag: cannot attribute.
- Containers or `unshare`: requires root or a daemon, breaks the zero-dependency promise.
- Restoring the real `HOME`: lets the command modify user config. Rejected on safety grounds. A bounded copy of an allowlisted dotfile set is used instead.
