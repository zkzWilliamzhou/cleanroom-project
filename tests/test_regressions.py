"""Regression tests for bugs found in review rounds 1-8.

Each test names the production change that would make it fail. These are the
evidence that the review rounds actually changed the program.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from cleanroom import config, knobs, model, report, security, workspace
from cleanroom.config import ConfigError, parse_config
from cleanroom.hostsnapshot import capture
from cleanroom.model import KNOB_NAMES, Report, Trial, TrialSpec


def _snapshot(d, cfg=None, env=None):
    cfg = cfg or parse_config({"command": "make"})
    with mock.patch.dict(os.environ, env or {"PATH": "/usr/bin:/bin"}, clear=True):
        return capture(d, cfg)


def _paths():
    return {"root": "/tmp/cr", "cwd": "/tmp/cr/workspace",
            "home": "/tmp/cr/home", "cache": "/tmp/cr/cache"}


class LocaleClockIndependence(unittest.TestCase):
    """Round 3: restoring locale must not leave the clean room's forced values."""

    def test_locale_restoration_does_not_keep_forced_C_values(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({"command": "make"})
            snap = _snapshot(d, cfg, {"PATH": "/usr/bin:/bin", "LANG": "de_DE.UTF-8",
                                      "LC_TIME": "fr_FR.UTF-8"})
            clean = knobs.build_env(snap, TrialSpec(frozenset()), _paths())
            restored = knobs.build_env(snap, TrialSpec(frozenset({"locale"})), _paths())
            self.assertEqual(clean["LANG"], "C")
            self.assertEqual(restored["LANG"], "de_DE.UTF-8")
            self.assertEqual(restored["LC_TIME"], "fr_FR.UTF-8")
            # A host that sets only LANG must not keep the clean room's LC_ALL=C.
            self.assertNotIn("LC_ALL", restored)
            self.assertEqual(clean["LC_ALL"], "C")

    def test_clock_restoration_does_not_keep_forced_UTC(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snapshot(d, env={"PATH": "/usr/bin:/bin", "TZ": "Asia/Shanghai"})
            clean = knobs.build_env(snap, TrialSpec(frozenset()), _paths())
            restored = knobs.build_env(snap, TrialSpec(frozenset({"clock"})), _paths())
            self.assertEqual(clean["TZ"], "UTC")
            self.assertEqual(restored["TZ"], "Asia/Shanghai")
            self.assertNotIn("SOURCE_DATE_EPOCH", restored)

    def test_knob_restoration_is_independent_for_all_single_knobs(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snapshot(d, env={"PATH": "/usr/bin:/bin", "LANG": "de_DE.UTF-8",
                                     "TZ": "Asia/Shanghai", "HTTP_PROXY": "http://proxy:3128",
                                     "EXTRA_VAR": "yes"})
            clean = knobs.build_env(snap, TrialSpec(frozenset()), _paths())
            for knob in KNOB_NAMES:
                with self.subTest(knob=knob):
                    built = knobs.build_env(snap, TrialSpec(frozenset({knob})), _paths())
                    self.assertEqual(built["HOME"], clean["HOME"])
                    self.assertEqual(built["TMPDIR"], clean["TMPDIR"])
                    self.assertEqual(built["PWD"], clean["PWD"])


class ReservedEnvInvariant(unittest.TestCase):
    """Round 3/4: no knob can redirect HOME, TMPDIR, or XDG paths."""

    def test_full_restoration_still_owns_home_and_tmpdir(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snapshot(d, env={"PATH": "/usr/bin:/bin", "HOME": "/real/home",
                                     "TMPDIR": "/real/tmp", "XDG_CONFIG_HOME": "/real/xdg"})
            built = knobs.build_env(snap, TrialSpec(frozenset(KNOB_NAMES)), _paths())
            self.assertEqual(built["HOME"], "/tmp/cr/home")
            self.assertEqual(built["TMPDIR"], "/tmp/cr")
            self.assertEqual(built["XDG_CONFIG_HOME"], "/tmp/cr/home/.config")


class RedactionOfCommand(unittest.TestCase):
    """Round 6: a secret embedded in the command must not reach any report."""

    def test_command_token_is_redacted_in_every_renderer(self):
        token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        rep = Report(verdict="clean", command="deploy --token %s" % token,
                     knobs=("env",), notes=())
        renders = [report.render_terminal(rep), report.render_markdown(rep),
                   json.dumps(report.render_json(rep)), report.canonical_json(rep)]
        for text in renders:
            self.assertNotIn(token, text)
            self.assertIn(security.REDACTED, text)

    def test_author_is_not_treated_as_a_secret_name(self):
        self.assertFalse(security.is_secret_name("AUTHOR"))
        self.assertFalse(security.is_secret_name("AUTHORS"))
        self.assertTrue(security.is_secret_name("AUTH_TOKEN"))
        self.assertTrue(security.is_secret_name("GH_TOKEN"))


class ConfigEdgeCases(unittest.TestCase):
    """Round 7: strict config, no dead keys, no unexpected exceptions."""

    def test_dead_out_dir_key_is_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", "out_dir": ".cleanroom"})

    def test_non_string_keys_raise_config_error(self):
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", 7: "x"})
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", None: "x"})

    def test_every_allowed_key_has_an_effect(self):
        base = config.default_config_dict("make")
        cfg = parse_config(base)
        for key, value in (("shell", True), ("timeout", 11), ("total_budget", 50),
                           ("max_trials", 20), ("repeat", 2), ("exclude", [".git"]),
                           ("artifact_dirs", ["dist"]), ("dotfiles", [".npmrc"]),
                           ("knobs", ["env"]), ("inject_env", {"A": "1"}),
                           ("format", "json")):
            with self.subTest(key=key):
                changed = dict(base)
                changed[key] = value
                self.assertNotEqual(parse_config(changed), cfg)


class TruncationReporting(unittest.TestCase):
    """Round 8: a truncated workspace copy must be visible in the receipt."""

    def test_prepare_marks_incomplete_copy(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(6):
                with open(os.path.join(d, "f%d.txt" % i), "w", encoding="utf-8") as fh:
                    fh.write("x")
            snap = _snapshot(d)
            cfg = parse_config({"command": "make"})
            with mock.patch.object(workspace, "MAX_FILES", 3):
                p = workspace.prepare(TrialSpec(frozenset()), snap, cfg)
            try:
                self.assertFalse(p.complete)
                self.assertLessEqual(len(os.listdir(p.cwd)), 3)
            finally:
                p.cleanup()

    def test_report_notes_truncated_trial(self):
        trial = Trial(spec=TrialSpec(frozenset()), exit_code=0, passed=True,
                      timed_out=False, error=None, stdout_tail="", stderr_tail="",
                      duration_ms=1, truncated=True)
        rep = Report(verdict="clean", command="make", knobs=(), trials=[trial])
        self.assertTrue(rep.to_dict()["trials"][0]["truncated"])


class CanonicalFreeze(unittest.TestCase):
    """Round 8/9: the function-freeze format ignores volatile timing."""

    def test_canonical_ignores_duration_and_trial_order(self):
        def make(duration, order):
            trials = [
                Trial(spec=TrialSpec(frozenset({"env"})), exit_code=0, passed=True,
                      timed_out=False, error=None, stdout_tail=order, stderr_tail="",
                      duration_ms=duration),
                Trial(spec=TrialSpec(frozenset()), exit_code=1, passed=False,
                      timed_out=False, error=None, stdout_tail="", stderr_tail="",
                      duration_ms=duration + 1),
            ]
            if duration % 2:
                trials.reverse()
            return Report(verdict="hidden", command="make", knobs=("env",), trials=trials)
        self.assertEqual(report.canonical_json(make(1, "a")),
                         report.canonical_json(make(999, "a")))

    def test_canonical_detects_a_verdict_change(self):
        def make(verdict):
            return Report(verdict=verdict, command="make", knobs=())
        self.assertNotEqual(report.canonical_json(make("clean")),
                            report.canonical_json(make("hidden")))


class BudgetExhaustion(unittest.TestCase):
    """Round 7: an exhausted trial budget must not overstate a hidden verdict."""

    def test_exhausted_budget_returns_blocked(self):
        from cleanroom import engine
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "run.py"), "w", encoding="utf-8") as fh:
                fh.write("import os,sys;sys.exit(0 if os.environ.get('NEED_THIS')=='1' else 1)\n")
            cfg = parse_config({
                "command": sys.executable + " run.py",
                "knobs": ["env"],
                "inject_env": {"NEED_THIS": "1"},
                "max_trials": 1,
                "timeout": 10,
            })
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        self.assertEqual(rep.verdict, "blocked")
        self.assertEqual(rep.confidence, "partial")
        self.assertTrue(any("budget" in n.lower() for n in rep.notes))


class ChildResourceLimit(unittest.TestCase):
    """Round 5: the child file-size limit is actually installed."""

    def test_preexec_limit_is_bounded_in_a_child(self):
        # Lowering RLIMIT_FSIZE in this process would be irreversible, so check
        # it in a subprocess, exactly where the runner installs it.
        import subprocess
        code = (
            "import json,sys;"
            "sys.path.insert(0,%r);"
            "from cleanroom.runner import _limit_child;"
            "import resource;"
            "_limit_child();"
            "print(json.dumps(resource.getrlimit(resource.RLIMIT_FSIZE)))"
        ) % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.name != "posix":
            self.skipTest("POSIX only")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout.strip())[0], security.CHILD_FILE_LIMIT)


if __name__ == "__main__":
    unittest.main()
