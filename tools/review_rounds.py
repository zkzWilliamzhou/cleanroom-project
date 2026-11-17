#!/usr/bin/env python3
"""Nine reproducible review rounds, one focused battery per round.

    python tools/review_rounds.py 1      # static dangerous constructs
    ...
    python tools/review_rounds.py 9      # full regression and integration
    python tools/review_rounds.py all    # run all nine

Each round prints its checks, findings, and a PASS/FAIL verdict. A round with
any finding exits 1. Fix the finding, then re-run the round.
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cleanroom import (bisect, cli, config, engine, knobs, model, report,  # noqa: E402
                       security, workspace)
from cleanroom.hostsnapshot import capture  # noqa: E402

PKG = os.path.join(ROOT, "cleanroom")


class Round:
    def __init__(self, number, title):
        self.number = number
        self.title = title
        self.checks = []
        self.findings = []

    def check(self, name, fn):
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 - an exception is a finding
            ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
        self.checks.append((name, bool(ok), detail or ""))
        if not ok:
            self.findings.append("%s: %s" % (name, detail))

    def report(self):
        print("ROUND %d — %s" % (self.number, self.title))
        for name, ok, detail in self.checks:
            print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                   (" — " + detail) if detail and not ok else ""))
        print("  checks=%d findings=%d verdict=%s" %
              (len(self.checks), len(self.findings), "PASS" if not self.findings else "FAIL"))
        return 1 if self.findings else 0


def _py_files():
    for dirpath, _dirs, files in os.walk(PKG):
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def _run_cli(args, cwd=None):
    return subprocess.run([sys.executable, "-m", "cleanroom"] + args,
                          cwd=cwd or ROOT,
                          env={**os.environ, "PYTHONPATH": ROOT},
                          capture_output=True, text=True, timeout=300)


def _snap(d, env=None, cfg=None):
    cfg = cfg or config.parse_config({"command": "make"})
    with mock.patch.dict(os.environ, env or {"PATH": "/usr/bin:/bin"}, clear=True):
        return capture(d, cfg)


# ---------------------------------------------------------------- round 1
def round1() -> int:
    r = Round(1, "Static dangerous constructs and subprocess hygiene")

    def banned():
        bad = []
        for path in _py_files():
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg == "shell":
                    if isinstance(node.value, ast.Constant) and node.value.value is True:
                        bad.append("%s:%d shell=True" % (os.path.basename(path), node.lineno))
                if isinstance(node, ast.Call):
                    name = node.func.id if isinstance(node.func, ast.Name) else (
                        node.func.attr if isinstance(node.func, ast.Attribute) else None)
                    if name in ("eval", "exec", "__import__", "system"):
                        bad.append("%s:%d %s()" % (os.path.basename(path), node.lineno, name))
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""])
                    for n in names:
                        if n.split(".")[0] in ("pickle", "marshal", "shelve", "requests",
                                               "urllib.request", "socket"):
                            bad.append("%s:%d import %s" % (os.path.basename(path), node.lineno, n))
        return not bad, ", ".join(bad)

    def popen_hygiene():
        bad = []
        for path in _py_files():
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("Popen", "run", "check_output", "call"):
                        kws = {k.arg for k in node.keywords}
                        if "shell" in kws:
                            bad.append("%s:%d shell kwarg" % (os.path.basename(path), node.lineno))
                        if node.func.attr == "Popen":
                            for needed in ("stdin", "stdout", "stderr", "start_new_session"):
                                if needed not in kws:
                                    bad.append("%s:%d Popen missing %s" %
                                               (os.path.basename(path), node.lineno, needed))
        return not bad, ", ".join(bad)

    def compiles():
        for path in _py_files():
            compile(open(path, "rb").read(), path, "exec")
        return True, "%d modules" % len(list(_py_files()))

    def no_network():
        hits = []
        for path in _py_files():
            text = open(path, encoding="utf-8").read()
            if re.search(r"urllib|http\.client|socket\.|requests\.|urlopen\(", text):
                hits.append(os.path.basename(path))
        return not hits, ", ".join(hits)

    r.check("no eval/exec/system/pickle/socket imports", banned)
    r.check("every Popen pins stdio and a new session", popen_hygiene)
    r.check("all modules compile", compiles)
    r.check("no network client code in the package", no_network)
    return r.report()


# ---------------------------------------------------------------- round 2
def round2() -> int:
    r = Round(2, "Fuzz robustness across parsers, minimizer, renderers, workspaces")
    rng = random.Random(20261112)
    alphabet = "abcXYZ019_-=:/. \n\t\"'$`{}[]()<>@#%&*!?~\x00é中"
    errors = []

    def one(i):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 500)))
        try:
            security.redact(text)
            security.redact_env({"K": text, "TOKEN": text})
            cfg = {"command": "make"}
            for key in rng.sample(["timeout", "repeat", "format", "knobs", "inject_env",
                                   "shell", "artifact_dirs"], rng.randint(0, 4)):
                cfg[key] = rng.choice([0, -1, "x", [], {}, None, True, 10 ** 9,
                                       ["env"], {"A": 1}])
            try:
                config.parse_config(cfg)
            except config.ConfigError:
                pass
            items = tuple("i%d" % j for j in range(rng.randint(0, 14)))
            res = bisect.ddmin(items, lambda s: "i3" in s, max_tests=rng.randint(1, 60))
            assert isinstance(res.items, tuple)
            rep = model.Report(verdict=rng.choice(["clean", "hidden", "inconclusive"]),
                               command=text[:80], knobs=("env",))
            json.dumps(report.render_sarif(rep))
            report.render_terminal(rep)
            report.canonical_json(rep)
            model.TrialSpec(frozenset(rng.sample(list(model.KNOB_NAMES), rng.randint(0, 5))))
        except Exception as exc:  # noqa: BLE001
            errors.append("case %d %s: %s" % (i, type(exc).__name__, exc))
        return True

    for i in range(1000):
        one(i)

    def no_exceptions():
        return not errors, "; ".join(errors[:3])

    def secret_never_survives():
        leaked = []
        secrets = ["ghp_abcdefghijklmnopqrstuvwxyz0123456789",
                   "Bearer abcdefgh1234567890abcdef", "https://u:hunter2@h/x",
                   "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"]
        for s in secrets:
            if s in security.redact("prefix " + s + " suffix"):
                leaked.append(s[:20])
        return not leaked, ", ".join(leaked)

    def unknown_knob_rejected():
        try:
            model.TrialSpec(frozenset({"nope"}))
            return False, "unknown knob accepted"
        except ValueError:
            return True, ""

    r.check("1000 fuzz cases raise no unexpected exceptions", no_exceptions)
    r.check("known secret shapes never survive redaction", secret_never_survives)
    r.check("TrialSpec rejects unknown knobs", unknown_knob_rejected)
    return r.report()


# ---------------------------------------------------------------- round 3
def round3() -> int:
    r = Round(3, "Knob partition correctness and hidden coupling")
    paths = {"root": "/tmp/cr", "cwd": "/tmp/cr/workspace",
             "home": "/tmp/cr/home", "cache": "/tmp/cr/cache"}
    env = {"PATH": "/usr/bin:/bin:/opt/bin", "LANG": "de_DE.UTF-8",
           "LC_TIME": "fr_FR.UTF-8", "TZ": "Asia/Shanghai",
           "SOURCE_DATE_EPOCH": "1700000000", "HTTP_PROXY": "http://proxy:3128",
           "npm_config_registry": "https://r.example", "EXTRA_VAR": "yes"}

    with tempfile.TemporaryDirectory() as d:
        snap = _snap(d, env)
        clean = knobs.build_env(snap, model.TrialSpec(frozenset()), paths)

        def locale_no_forced_C():
            got = knobs.build_env(snap, model.TrialSpec(frozenset({"locale"})), paths)
            bad = (got.get("LANG") != "de_DE.UTF-8" or "LC_ALL" in got
                   or got.get("LC_TIME") != "fr_FR.UTF-8")
            return not bad, "LANG=%r LC_ALL=%r" % (got.get("LANG"), got.get("LC_ALL"))

        def clock_no_forced_UTC():
            got = knobs.build_env(snap, model.TrialSpec(frozenset({"clock"})), paths)
            bad = got.get("TZ") != "Asia/Shanghai" or "SOURCE_DATE_EPOCH" not in got
            return not bad, "TZ=%r" % got.get("TZ")

        def reserved_invariant():
            for subset in (frozenset({"env"}), frozenset(model.KNOB_NAMES)):
                got = knobs.build_env(snap, model.TrialSpec(subset), paths)
                if got["HOME"] != clean["HOME"] or got["TMPDIR"] != clean["TMPDIR"]:
                    return False, "HOME/TMPDIR escaped under %s" % sorted(subset)
            return True, ""

        def pairwise_independence():
            owners = {"locale": knobs.LOCALE_VARS, "clock": knobs.CLOCK_VARS,
                      "network": knobs.NETWORK_VARS, "path": ("PATH",)}
            problems = []
            for a, a_vars in owners.items():
                got_a = knobs.build_env(snap, model.TrialSpec(frozenset({a})), paths)
                for b, b_vars in owners.items():
                    if a == b:
                        continue
                    for var in b_vars:
                        if var in a_vars:
                            continue
                        if clean.get(var) != got_a.get(var):
                            problems.append("%s changed %s" % (a, var))
            return not problems, "; ".join(problems[:5])

        def owned_vars_excluded_from_env_knob():
            names = knobs.extra_env_names(snap)
            leaked = [n for n in names if n in knobs.OWNED_ALL]
            return not leaked, ", ".join(leaked)

        def path_extras():
            extras = knobs.non_system_path_entries(snap)
            return extras == ("/opt/bin",), repr(extras)

        r.check("locale restoration drops the forced C defaults", locale_no_forced_C)
        r.check("clock restoration drops the forced UTC defaults", clock_no_forced_UTC)
        r.check("HOME/TMPDIR stay owned by the clean room", reserved_invariant)
        r.check("no knob changes another knob's variables", pairwise_independence)
        r.check("env knob excludes owned variables", owned_vars_excluded_from_env_knob)
        r.check("path extras filter the system PATH", path_extras)
    return r.report()


# ---------------------------------------------------------------- round 4
def round4() -> int:
    r = Round(4, "Path, symlink, and output-directory safety")

    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
        secret = os.path.join(outside, "secret.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("must not be copied")
        os.symlink(secret, os.path.join(d, "link.txt"))
        os.symlink(outside, os.path.join(d, "linkdir"))
        os.makedirs(os.path.join(d, "sub"))
        with open(os.path.join(d, "sub", "keep.txt"), "w", encoding="utf-8") as fh:
            fh.write("keep")
        cfg = config.parse_config({"command": "make"})
        snap = _snap(d)
        p = workspace.prepare(model.TrialSpec(frozenset()), snap, cfg)
        try:
            def symlinks_skipped():
                bad = [n for n in ("link.txt", "linkdir")
                       if os.path.lexists(os.path.join(p.cwd, n))]
                return not bad, ", ".join(bad)

            def tree_contained():
                escaped = []
                for dirpath, _dirs, files in os.walk(p.cwd):
                    for f in files:
                        if not security.contained(p.root, os.path.join(dirpath, f)):
                            escaped.append(f)
                return not escaped, ", ".join(escaped)

            def kept_regular_file():
                return os.path.isfile(os.path.join(p.cwd, "sub", "keep.txt")), "missing"

            r.check("symlinks and symlink dirs are skipped", symlinks_skipped)
            r.check("every copied file resolves inside the temp root", tree_contained)
            r.check("regular nested files are copied", kept_regular_file)
        finally:
            p.cleanup()

        def cleanup_removes_root():
            return not os.path.exists(p.root), p.root

        r.check("cleanup removes the whole temp tree", cleanup_removes_root)

    def symlink_escape_contained():
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as o:
            os.symlink(o, os.path.join(d, "escape"))
            return not security.contained(d, os.path.join(d, "escape", "x")), "escape accepted"

    def out_escape_cli():
        proc = _run_cli(["test", "python3 -c 'print(1)'", "--out", "../../escape"])
        return proc.returncode == 2 and "Traceback" not in proc.stdout, \
            "exit=%d" % proc.returncode

    def init_escape_cli():
        proc = _run_cli(["init", "make", "--out", "../escape.json"])
        return proc.returncode == 2, "exit=%d" % proc.returncode

    def symlinked_root_cleanup():
        # A command could replace the temp root with a symlink to somewhere else.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            root = os.path.join(d, "rootlink")
            os.symlink(other, root)
            with open(os.path.join(other, "must_survive"), "w", encoding="utf-8") as fh:
                fh.write("yes")
            fake = workspace.PreparedTrial(root=root, cwd=d, home=d, env={}, complete=True)
            fake.cleanup()
            return (not os.path.lexists(root)
                    and os.path.isfile(os.path.join(other, "must_survive"))), \
                "symlink removal damaged the target"

    r.check("contained() rejects a symlink escape", symlink_escape_contained)
    r.check("--out outside cwd is rejected", out_escape_cli)
    r.check("init --out outside cwd is rejected", init_escape_cli)
    r.check("cleanup tolerates a replaced temp root", symlinked_root_cleanup)
    return r.report()


# ---------------------------------------------------------------- round 5
def round5() -> int:
    r = Round(5, "Subprocess, timeout, and child resource safety")
    from cleanroom import runner

    def argv_explicit():
        cfg = config.parse_config({"command": "echo a | grep a", "shell": True})
        return runner._argv(cfg) == ["/bin/sh", "-c", "echo a | grep a"], repr(runner._argv(cfg))

    def no_shell_default():
        cfg = config.parse_config({"command": "echo a | grep a"})
        return runner._argv(cfg) == ["echo", "a", "|", "grep", "a"], repr(runner._argv(cfg))

    def missing_binary():
        with tempfile.TemporaryDirectory() as d:
            cfg = config.parse_config({"command": "/no/such/binary", "timeout": 5})
            snap = _snap(d)
            t = runner.run_trial(model.TrialSpec(frozenset()), snap, cfg)
            return (not t.passed and bool(t.error) and "Traceback" not in (t.stderr_tail or "")), \
                "error=%r" % t.error

    def timeout_kills_group():
        marker = "CLEANROOM_R5_MARKER_9f31"
        cmd = (sys.executable + " -c \"import subprocess,sys,time;"
               "subprocess.Popen([sys.executable,'-c','import time; time.sleep(25) # " + marker + "']);"
               "time.sleep(25)\"")
        with tempfile.TemporaryDirectory() as d:
            cfg = config.parse_config({"command": cmd, "timeout": 1, "repeat": 1})
            snap = _snap(d)
            t = runner.run_trial(model.TrialSpec(frozenset()), snap, cfg)
        survived = []
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % pid, "rb") as fh:
                    if marker.encode() in fh.read():
                        survived.append(pid)
            except OSError:
                continue
        return (t.timed_out and not survived), "timed_out=%s survivors=%s" % (
            t.timed_out, survived)

    def child_file_limit():
        if os.name != "posix":
            return True, "skipped"
        code = ("import sys,json,resource;sys.path.insert(0,%r);"
                "from cleanroom.runner import _limit_child;_limit_child();"
                "print(json.dumps(resource.getrlimit(resource.RLIMIT_FSIZE)[0]))" % ROOT)
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, timeout=20)
        return (proc.returncode == 0 and
                json.loads(proc.stdout.strip()) == security.CHILD_FILE_LIMIT), \
            proc.stderr.strip()

    def output_bounded():
        cmd = sys.executable + " -c \"print('x'*500000)\""
        with tempfile.TemporaryDirectory() as d:
            cfg = config.parse_config({"command": cmd, "timeout": 20})
            snap = _snap(d)
            t = runner.run_trial(model.TrialSpec(frozenset()), snap, cfg)
        return t.passed and len(t.stdout_tail) <= security.MAX_OUTPUT_BYTES + 200, \
            "len=%d" % len(t.stdout_tail)

    r.check("--shell uses an explicit /bin/sh -c argv", argv_explicit)
    r.check("default argv never invokes a shell", no_shell_default)
    r.check("missing binary becomes a trial error, not a crash", missing_binary)
    r.check("timeout kills the whole process group", timeout_kills_group)
    r.check("child file-size limit is installed", child_file_limit)
    r.check("captured stdout is bounded", output_bounded)
    return r.report()


# ---------------------------------------------------------------- round 6
def round6() -> int:
    r = Round(6, "Secret redaction across every output surface")
    token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"

    def shapes():
        cases = [
            ("gh token", "Bearer " + token),
            ("url creds", "https://bob:hunter2@example.com/x"),
            ("pem", "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----"),
            ("env assignment", "API_KEY=supersecretvalue123"),
            ("slack", "xoxb-123456789012-abcdefghijkl"),
        ]
        leaked = [name for name, text in cases if text.split("=")[-1] in security.redact(text)
                  or (name == "pem" and "QUJD" in security.redact(text))
                  or (name == "gh token" and token in security.redact(text))
                  or (name == "url creds" and "hunter2" in security.redact(text))
                  or (name == "slack" and "xoxb-" in security.redact(text))]
        return not leaked, ", ".join(leaked)

    def env_values():
        out = security.redact_env({"PATH": "/usr/bin", "NPM_TOKEN": token, "CI": "true"})
        return out["NPM_TOKEN"] == security.REDACTED and out["PATH"] == "/usr/bin", repr(out)

    def report_surfaces():
        rep = model.Report(verdict="clean", command="deploy --token " + token,
                           knobs=("env",), notes=())
        texts = [report.render_terminal(rep), report.render_markdown(rep),
                 json.dumps(report.render_json(rep)), report.canonical_json(rep),
                 report.render_annotations(rep), json.dumps(report.render_sarif(rep))]
        return all(token not in t for t in texts), "token leaked"

    def demo_leaks_name_not_value():
        proc = _run_cli(["demo"])
        out = proc.stdout
        return ("DEMO_LICENSE_KEY" in out and "granted" not in out
                and proc.returncode == 1), "exit=%d" % proc.returncode

    def names_only_in_findings():
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "run.py"), "w", encoding="utf-8") as fh:
                fh.write("import os,sys;sys.exit(0 if os.environ.get('A_SECRET_TOKEN')=='yes' else 1)\n")
            cfg = config.parse_config({"command": sys.executable + " run.py",
                                       "knobs": ["env"],
                                       "inject_env": {"A_SECRET_TOKEN": "yes"},
                                       "timeout": 10})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
            text = json.dumps(report.render_json(rep))
            return ("A_SECRET_TOKEN" in text and '"yes"' not in text), "value leaked"

    r.check("known secret shapes are redacted", shapes)
    r.check("redact_env masks secret values only", env_values)
    r.check("no renderer leaks a secret from the command", report_surfaces)
    r.check("demo prints the variable name, never its value", demo_leaks_name_not_value)
    r.check("findings name the variable but never its value", names_only_in_findings)
    return r.report()


# ---------------------------------------------------------------- round 7
def round7() -> int:
    r = Round(7, "Config, CLI, and exit-code edges")

    def bad_configs():
        bad = [
            {"timeout": 0}, {"command": ""}, {"command": "make", "out_dir": "x"},
            {"command": "make", "knobs": ["bogus"]}, {"command": "make", "format": "xml"},
            {"command": "make", "inject_env": {"BAD NAME": "x"}},
            {"command": "make", "repeat": -1}, {"command": "make", "shell": "yes"},
        ]
        failed = []
        for cfg in bad:
            try:
                config.parse_config(cfg)
                failed.append(repr(cfg))
            except config.ConfigError:
                pass
        return not failed, "; ".join(failed)

    def non_string_key():
        try:
            config.parse_config({"command": "make", 7: "x"})
            return False, "accepted"
        except config.ConfigError:
            return True, ""

    def cli_never_tracebacks():
        cases = [
            ["test", "--config", "/no/such.json"],
            ["test", "python3 -c 'print(1)'", "--format", "bogus"],
            ["test", "python3 -c 'print(1)'", "--out", "../../x"],
            ["explain", "/no/such.json"],
            ["knobs", "--bogus"],
        ]
        bad = []
        for args in cases:
            proc = _run_cli(args)
            if "Traceback" in (proc.stdout + proc.stderr) or proc.returncode not in (0, 2):
                bad.append("%s exit=%d" % (" ".join(args[:2]), proc.returncode))
        return not bad, "; ".join(bad)

    def exit_codes():
        codes = {}
        codes["clean"] = _run_cli(["test", "python3 -c 'print(1)'", "--knobs", "env"]).returncode
        codes["inconclusive"] = _run_cli(
            ["test", "python3 -c 'import sys;sys.exit(7)'", "--knobs", "env"]).returncode
        proc = _run_cli(["demo"])
        codes["hidden"] = proc.returncode
        codes["blocked"] = _run_cli(
            ["test", "python3 -c 'import time;time.sleep(0.2)'", "--max-trials", "1",
             "--total-budget", "1", "--knobs", "env"]).returncode
        expected = {"clean": 0, "hidden": 1, "inconclusive": 2, "blocked": 3}
        bad = [k for k, v in expected.items() if codes.get(k) != v]
        return not bad, "got=%r expected=%r" % (codes, expected)

    def init_writes_valid_config():
        with tempfile.TemporaryDirectory() as d:
            proc = _run_cli(["init", "make test", "--out", os.path.join(d, "c.json")], cwd=d)
            try:
                cfg = config.load_config(os.path.join(d, "c.json"))
                return proc.returncode == 0 and cfg.command == "make test", "bad config"
            except config.ConfigError as exc:
                return False, str(exc)

    def formats_parse():
        with tempfile.TemporaryDirectory() as d:
            for fmt in ("terminal", "json", "markdown", "sarif", "annotations"):
                proc = _run_cli(["test", "python3 -c 'print(1)'", "--knobs", "env",
                                 "--format", fmt], cwd=d)
                if proc.returncode != 0 or not proc.stdout.strip():
                    return False, "%s exit=%d" % (fmt, proc.returncode)
            return True, ""

    r.check("strict config rejects 8 malformed shapes", bad_configs)
    r.check("non-string config keys raise ConfigError", non_string_key)
    r.check("CLI never prints a traceback for bad input", cli_never_tracebacks)
    r.check("exit codes 0/1/2/3 map to the four verdicts", exit_codes)
    r.check("init writes a loadable config", init_writes_valid_config)
    r.check("all five output formats render", formats_parse)
    return r.report()


# ---------------------------------------------------------------- round 8
def round8() -> int:
    r = Round(8, "Resource limits, determinism, and report integrity")

    def truncation_flag():
        with tempfile.TemporaryDirectory() as d:
            for i in range(6):
                with open(os.path.join(d, "f%d" % i), "w", encoding="utf-8") as fh:
                    fh.write("x")
            cfg = config.parse_config({"command": "make"})
            snap = _snap(d)
            with mock.patch.object(workspace, "MAX_FILES", 3):
                p = workspace.prepare(model.TrialSpec(frozenset()), snap, cfg)
            try:
                return not p.complete and len(os.listdir(p.cwd)) <= 3, \
                    "complete=%s files=%d" % (p.complete, len(os.listdir(p.cwd)))
            finally:
                p.cleanup()

    def canonical_stability():
        import time as _t
        def make(delay, reverse):
            a = model.Trial(spec=model.TrialSpec(frozenset()), exit_code=0, passed=True,
                            timed_out=False, error=None, stdout_tail="a", stderr_tail="",
                            duration_ms=delay)
            b = model.Trial(spec=model.TrialSpec(frozenset({"env"})), exit_code=1,
                            passed=False, timed_out=False, error=None, stdout_tail="",
                            stderr_tail="", duration_ms=delay + 5)
            trials = [a, b]
            if reverse:
                trials.reverse()
            return model.Report(verdict="hidden", command="make", knobs=("env",),
                                trials=trials)
        return report.canonical_json(make(1, False)) == report.canonical_json(make(9999, True)), \
            "canonical changed"

    def ddmin_budget():
        res = bisect.ddmin(tuple("abcdefghijklmnopqrstuvwxyz"),
                           lambda s: "z" in s, max_tests=5)
        return not res.complete and res.tests <= 5, "tests=%d complete=%s" % (
            res.tests, res.complete)

    def ddmin_minimal():
        res = bisect.ddmin(tuple("abcdef"), lambda s: "c" in s or ("a" in s and "e" in s),
                           max_tests=200)
        # Whatever it returns must itself satisfy the predicate.
        ok = ("c" in res.items) or ("a" in res.items and "e" in res.items)
        return ok, repr(res.items)

    def report_files():
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            proc = _run_cli(["test", "python3 -c 'print(1)'", "--knobs", "env",
                             "--out", out], cwd=d)
            if proc.returncode != 0:
                return False, "exit=%d" % proc.returncode
            try:
                data = json.load(open(os.path.join(out, "report.json"), encoding="utf-8"))
                sarif = json.load(open(os.path.join(out, "report.sarif"), encoding="utf-8"))
                md = open(os.path.join(out, "report.md"), encoding="utf-8").read()
                return (data["schema_version"] == model.SCHEMA_VERSION
                        and sarif["version"] == "2.1.0"
                        and md.startswith("# cleanroom report")), "content mismatch"
            except (OSError, ValueError, KeyError) as exc:
                return False, str(exc)

    def sarif_shape():
        sarif = report.render_sarif(model.Report(verdict="clean", command="make", knobs=()))
        run = sarif["runs"][0]
        return (sarif["version"] == "2.1.0" and "driver" in run["tool"]
                and isinstance(run["results"], list)
                and all("ruleId" in x for x in run["results"])), "bad shape"

    def explain_roundtrip():
        data = report.render_json(model.Report(verdict="hidden", command="make", knobs=("env",),
                                               findings=[model.Finding(
                                                   knob="env", detail="A", evidence="e",
                                                   fix="f", confidence="full")]))
        return "A" in report.explain(data), "detail missing"

    r.check("truncated workspace copy is flagged", truncation_flag)
    r.check("canonical freeze ignores timing and order", canonical_stability)
    r.check("minimizer honours a hard trial budget", ddmin_budget)
    r.check("minimizer returns a satisfying subset", ddmin_minimal)
    r.check("--out writes valid JSON, SARIF, and Markdown", report_files)
    r.check("SARIF 2.1.0 shape is valid", sarif_shape)
    r.check("explain renders a saved receipt", explain_roundtrip)
    return r.report()


# ---------------------------------------------------------------- round 9
def round9() -> int:
    r = Round(9, "Full regression, integration, dogfooding, and packaging")

    def suite():
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                              cwd=ROOT, env={**os.environ, "PYTHONPATH": ROOT},
                              capture_output=True, text=True, timeout=300)
        tail = proc.stderr.strip().splitlines()
        return proc.returncode == 0, tail[-1] if tail else "no output"

    def selftest():
        proc = _run_cli(["selftest"])
        return proc.returncode == 0 and "5/5" in proc.stdout, proc.stdout.strip()

    def demo():
        proc = _run_cli(["demo"])
        return proc.returncode == 1 and "DEMO_LICENSE_KEY" in proc.stdout, \
            "exit=%d" % proc.returncode

    def dogfood():
        proc = _run_cli(["test", "--config", ".cleanroom.json"])
        return proc.returncode == 0 and "CLEAN" in proc.stdout, "exit=%d" % proc.returncode

    def all_knobs_dogfood():
        proc = _run_cli(["test", "python3 -m unittest discover -s tests",
                         "--knobs", "env,dotfiles,path,artifacts,locale,network,clock",
                         "--timeout", "60", "--max-trials", "60"])
        return proc.returncode == 0, "exit=%d %s" % (proc.returncode, proc.stdout[-160:])

    def wheel_build():
        import shutil
        import zipfile
        generated = [os.path.join(ROOT, "build"),
                     os.path.join(ROOT, "cleanroom.egg-info"),
                     os.path.join(ROOT, "UNKNOWN.egg-info")]
        try:
            with tempfile.TemporaryDirectory() as d:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
                     "--no-build-isolation", "-w", d],
                    cwd=ROOT, capture_output=True, text=True, timeout=300)
                wheels = ([f for f in os.listdir(d) if f.endswith(".whl")]
                          if os.path.isdir(d) else [])
                if proc.returncode != 0 or not wheels:
                    return False, "; ".join((proc.stdout + proc.stderr).strip().splitlines()[-3:])
                wheel = os.path.join(d, wheels[0])
                if not wheels[0].startswith("cleanroom-1.0.0-"):
                    return False, "wrong wheel name: %s" % wheels[0]
                with zipfile.ZipFile(wheel) as z:
                    metadata = [n for n in z.namelist() if n.endswith("/METADATA")]
                    if not metadata:
                        return False, "no METADATA in wheel"
                    text = z.read(metadata[0]).decode("utf-8", "replace")
                    if "Name: cleanroom" not in text or "Version: 1.0.0" not in text:
                        return False, "wrong METADATA: %s" % text[:120]
                return True, ""
        finally:
            for path in generated:
                shutil.rmtree(path, ignore_errors=True)

    def no_dependencies():
        pyproject = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
        setupcfg = open(os.path.join(ROOT, "setup.cfg"), encoding="utf-8").read()
        bad = []
        for label, text in (("pyproject", pyproject), ("setup.cfg", setupcfg)):
            for match in re.finditer(r"(?m)^\s*(dependencies|install_requires)\s*[:=]\s*(.+)$",
                                     text):
                value = match.group(2).strip()
                if value and value not in ("[]", "=", ""):
                    bad.append("%s: %s=%s" % (label, match.group(1), value))
        return not bad, "; ".join(bad)

    def stdlib_only():
        bad = []
        for path in _py_files():
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                         else ([node.module or ""] if isinstance(node, ast.ImportFrom) else []))
                for n in names:
                    top = n.split(".")[0]
                    if top in ("yaml", "requests", "rich", "click", "pytest", "numpy",
                               "pydantic", "jsonschema", "tomllib"):
                        bad.append("%s: %s" % (os.path.basename(path), top))
        return not bad, ", ".join(bad)

    r.check("full unittest suite passes", suite)
    r.check("selftest passes", selftest)
    r.check("demo finds its hidden dependency", demo)
    r.check("cleanroom verifies its own repo as clean", dogfood)
    r.check("dogfood with all seven knobs", all_knobs_dogfood)
    r.check("wheel builds offline with no build isolation", wheel_build)
    r.check("pyproject declares zero runtime dependencies", no_dependencies)
    r.check("package imports only the standard library", stdlib_only)
    return r.report()


ROUNDS = {i: fn for i, fn in enumerate(
    [round1, round2, round3, round4, round5, round6, round7, round8, round9], start=1)}


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        codes = []
        for i in sorted(ROUNDS):
            codes.append(ROUNDS[i]())
            print("")
        failed = [i for i, c in zip(sorted(ROUNDS), codes) if c]
        print("ALL ROUNDS: %d/9 passed%s" %
              (9 - len(failed), "" if not failed else ", FAILED: %s" % failed))
        return 1 if failed else 0
    if arg.isdigit() and int(arg) in ROUNDS:
        return ROUNDS[int(arg)]()
    print("usage: python tools/review_rounds.py [1-9|all]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
