#!/usr/bin/env python3
"""Freeze the observable function of the program into a golden receipt.

    python tools/freeze.py make     # write docs/GOLDEN.json and print its sha256
    python tools/freeze.py check    # rebuild and compare byte-for-byte

The scenario is fully controlled: a fixed shell fixture, a fixed environment,
and a fixed knob set. Timings and trial order are stripped by canonical_json,
so the hash changes only when behavior changes.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cleanroom import engine, report  # noqa: E402
from cleanroom.config import parse_config  # noqa: E402

GOLDEN = os.path.join(ROOT, "docs", "GOLDEN.json")

FIXTURE = """#!/bin/sh
if [ "$DEMO_LICENSE_KEY" != "granted" ]; then
  echo "missing DEMO_LICENSE_KEY" >&2
  exit 1
fi
echo "build ok"
"""

CONFIG = {
    "command": "/bin/sh run.sh",
    "shell": False,
    "knobs": ["env"],
    "inject_env": {"DEMO_LICENSE_KEY": "granted"},
    "timeout": 10,
    "total_budget": 60,
    "max_trials": 40,
    "repeat": 1,
    "format": "terminal",
}


def build_canonical() -> str:
    with tempfile.TemporaryDirectory(prefix="cleanroom-freeze-") as work:
        with open(os.path.join(work, "run.sh"), "w", encoding="utf-8") as fh:
            fh.write(FIXTURE)
        home = os.path.join(work, "home")
        os.makedirs(home, exist_ok=True)
        cfg = parse_config(CONFIG)
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"PATH": "/usr/bin:/bin", "HOME": home})
            receipt = engine.evaluate(config=cfg, source=work)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        return report.canonical_json(receipt)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode not in ("make", "check"):
        print("usage: python tools/freeze.py [make|check]")
        return 2
    current = build_canonical()
    current_hash = digest(current)
    if mode == "make":
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            fh.write(current)
        print("golden written: %s" % GOLDEN)
        print("sha256: %s" % current_hash)
        return 0

    if not os.path.isfile(GOLDEN):
        print("FAIL: no golden receipt. Run `python tools/freeze.py make` first.")
        return 1
    with open(GOLDEN, "r", encoding="utf-8") as fh:
        saved = fh.read()
    saved_hash = digest(saved)
    print("golden  sha256: %s" % saved_hash)
    print("current sha256: %s" % current_hash)
    ok = saved == current
    print("function freeze: %s" % ("PASS (byte-identical)" if ok else "FAIL (behavior changed)"))
    if not ok:
        import difflib
        print("".join(list(difflib.unified_diff(
            saved.splitlines(True), current.splitlines(True),
            fromfile="golden", tofile="current"))[:60]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
