#!/usr/bin/env python3
"""Reproducible audit commands for the nine review rounds.

Usage:
    python tools/audit.py static
    python tools/audit.py fuzz --seed 7 --cases 400
    python tools/audit.py suite
    python tools/audit.py demo
    python tools/audit.py selftest
    python tools/audit.py dogfood
    python tools/audit.py all
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cleanroom import bisect, config, knobs, model, report, security, workspace  # noqa: E402
from cleanroom.hostsnapshot import capture  # noqa: E402

import ast  # noqa: E402

BANNED_CALLS = ("eval", "exec", "__import__", "system")
BANNED_IMPORTS = ("pickle", "marshal", "shelve")

SOURCE_DIR = os.path.join(ROOT, "cleanroom")


def _py_files():
    for dirpath, _dirs, files in os.walk(SOURCE_DIR):
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def static() -> int:
    findings = []
    for path in _py_files():
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    findings.append("%s:%d: shell=True" % (
                        os.path.relpath(path, ROOT), node.lineno))
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in BANNED_CALLS:
                    findings.append("%s:%d: call to %s()" % (
                        os.path.relpath(path, ROOT), node.lineno, name))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in BANNED_IMPORTS:
                        findings.append("%s:%d: import %s" % (
                            os.path.relpath(path, ROOT), node.lineno, alias.name))
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in BANNED_IMPORTS:
                    findings.append("%s:%d: from %s import" % (
                        os.path.relpath(path, ROOT), node.lineno, node.module))
    print("static: %d dangerous-construct findings" % len(findings))
    for item in findings:
        print("  " + item)
    compiled = 0
    for path in _py_files():
        with open(path, "rb") as fh:
            compile(fh.read(), path, "exec")
        compiled += 1
    print("static: %d modules compiled cleanly" % compiled)
    return 1 if findings else 0


def fuzz(seed: int, cases: int) -> int:
    rng = random.Random(seed)
    alphabet = "abcXYZ019_-=:/. \n\t\"'$`{}[]()<>@#%&*!?~\x00é中"
    unexpected = []

    def check(label, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the point is to catch anything
            unexpected.append("%s: %s: %s" % (label, type(exc).__name__, exc))

    for i in range(cases):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 400)))
        check("redact", lambda t=text: security.redact(t))
        env = {("K%d" % j): "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
               for j in range(rng.randint(0, 8))}
        check("redact_env", lambda e=env: security.redact_env(e))
        cfg_data = {"command": "make"}
        for key in rng.sample(["timeout", "repeat", "format", "knobs", "inject_env", "shell"],
                              rng.randint(0, 3)):
            cfg_data[key] = rng.choice([0, -1, "x", [], {}, None, True, 10 ** 9, ["env"]])
        check("parse_config", lambda d=cfg_data: _config_ok(d))
        items = tuple("i%d" % j for j in range(rng.randint(0, 12)))
        check("ddmin", lambda it=items: bisect.ddmin(
            it, lambda s: "i3" in s, max_tests=rng.randint(1, 40)))
        rep = model.Report(verdict=rng.choice(["clean", "hidden", "inconclusive"]),
                           command=text[:60], knobs=("env",))
        check("render", lambda r=rep: (report.render_terminal(r), report.canonical_json(r),
                                       json.dumps(report.render_sarif(r))))

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as fh:
            fh.write("ok")
        cfg = config.parse_config({"command": "make"})
        snap = capture(tmp, cfg)
        for i in range(min(cases, 30)):
            spec = model.TrialSpec(
                frozenset(rng.sample(list(model.KNOB_NAMES), rng.randint(0, 4))),
                env_names=frozenset(rng.sample(list(knobs.extra_env_names(snap)),
                                               min(2, len(knobs.extra_env_names(snap)))))
                if knobs.extra_env_names(snap) else None,
            )
            check("prepare", lambda s=spec: _prepare_ok(s, snap, cfg))

    print("fuzz: seed=%d cases=%d unexpected_exceptions=%d" % (seed, cases, len(unexpected)))
    for item in unexpected[:20]:
        print("  " + item)
    return 1 if unexpected else 0


def _config_ok(data):
    try:
        config.parse_config(data)
    except config.ConfigError:
        pass


def _prepare_ok(spec, snap, cfg):
    prepared = workspace.prepare(spec, snap, cfg)
    try:
        security.contained(prepared.root, prepared.cwd)
    finally:
        prepared.cleanup()


def _run(label, args):
    proc = subprocess.run(args, cwd=ROOT, env={**os.environ, "PYTHONPATH": ROOT},
                          capture_output=True, text=True, timeout=300)
    lines = proc.stdout.strip().splitlines()
    print("%s: exit=%d %s" % (label, proc.returncode, lines[-1] if lines else ""))
    if proc.returncode != 0:
        print("\n".join(lines[-25:]))
        print("\n".join(proc.stderr.strip().splitlines()[-15:]))
    return proc.returncode


def suite():
    return _run("suite", [sys.executable, "-m", "unittest", "discover", "-s", "tests"])


def demo():
    code = _run("demo", [sys.executable, "-m", "cleanroom", "demo"])
    print("demo: CLI exit 1 means the hidden dependency was found (expected)")
    return 0 if code == 1 else 1


def selftest():
    return _run("selftest", [sys.executable, "-m", "cleanroom", "selftest"])


def dogfood():
    return _run("dogfood", [sys.executable, "-m", "cleanroom", "test",
                            "--config", ".cleanroom.json"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=("static", "fuzz", "suite", "demo", "selftest",
                                        "dogfood", "all"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cases", type=int, default=400)
    args = parser.parse_args()
    if args.cmd == "static":
        return static()
    if args.cmd == "fuzz":
        return fuzz(args.seed, args.cases)
    if args.cmd == "suite":
        return suite()
    if args.cmd == "demo":
        return demo()
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "dogfood":
        return dogfood()
    results = [static(), fuzz(args.seed, args.cases), suite(), selftest(), dogfood()]
    return 1 if any(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
