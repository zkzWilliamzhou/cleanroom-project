import os
import sys
import tempfile
import unittest
from unittest import mock

from cleanroom.bisect import ddmin
from cleanroom.config import parse_config
from cleanroom.hostsnapshot import capture
from cleanroom.model import TrialSpec
from cleanroom.runner import run_trial


def _fixture(d, body):
    with open(os.path.join(d, "run.py"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return f"{sys.executable} run.py"


class RunnerTests(unittest.TestCase):
    def _run(self, command, knobs=frozenset(), extra=None, timeout=10):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({"command": command, "timeout": timeout, **(extra or {})})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                snap = capture(d, cfg)
                return run_trial(TrialSpec(knobs), snap, cfg)

    def test_passing_command_produces_passing_trial(self):
        t = self._run(f"{sys.executable} -c 'print(1)'")
        self.assertTrue(t.passed)
        self.assertEqual(t.exit_code, 0)
        self.assertFalse(t.timed_out)
        self.assertIsNone(t.error)
        self.assertIn("1", t.stdout_tail)

    def test_failing_command_produces_failing_trial(self):
        t = self._run(f"{sys.executable} -c 'import sys; sys.exit(3)'")
        self.assertFalse(t.passed)
        self.assertEqual(t.exit_code, 3)

    def test_timeout_kills_the_process_group(self):
        t = self._run(f"{sys.executable} -c 'import time; time.sleep(30)'", timeout=1)
        self.assertFalse(t.passed)
        self.assertTrue(t.timed_out)

    def test_missing_executable_is_an_error_not_a_crash(self):
        t = self._run("/definitely/not/a/binary")
        self.assertFalse(t.passed)
        self.assertTrue(t.error)

    def test_stderr_is_redacted(self):
        cmd = f"{sys.executable} -c 'import sys; print(\"Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789\", file=sys.stderr); sys.exit(1)'"
        t = self._run(cmd)
        self.assertFalse(t.passed)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", t.stderr_tail)

    def test_shell_flag_uses_explicit_argv(self):
        t = self._run("echo hello | grep hello", extra={"shell": True})
        self.assertTrue(t.passed)
        self.assertIn("hello", t.stdout_tail)

    def test_output_is_bounded(self):
        cmd = f"{sys.executable} -c 'print(\"x\" * 500000)'"
        t = self._run(cmd)
        self.assertTrue(t.passed)
        self.assertLessEqual(len(t.stdout_tail), 64000 + 200)

    def test_env_knob_controls_visibility_of_injected_variable(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = _fixture(d, "import os, sys; sys.exit(0 if os.environ.get('DEMO_KEY') == 'yes' else 1)\n")
            cfg = parse_config({"command": cmd, "knobs": ["env"], "inject_env": {"DEMO_KEY": "yes"}})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                snap = capture(d, cfg)
                clean = run_trial(TrialSpec(frozenset()), snap, cfg)
                dirty = run_trial(TrialSpec(frozenset({"env"})), snap, cfg)
        self.assertFalse(clean.passed)
        self.assertTrue(dirty.passed)

    def test_repeat_detects_flaky_commands(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "counter")
            cmd = (f"{sys.executable} -c \"import os,sys; p={path!r}; "
                   "n=int(open(p).read())+1 if os.path.exists(p) else 1; "
                   "open(p,'w').write(str(n)); sys.exit(0 if n==1 else 1)\"")
            cfg = parse_config({"command": cmd, "repeat": 2, "timeout": 10})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                snap = capture(d, cfg)
                t = run_trial(TrialSpec(frozenset()), snap, cfg)
        self.assertFalse(t.passed)
        self.assertTrue(t.flaky)


class BisectTests(unittest.TestCase):
    def test_ddmin_finds_the_single_cause(self):
        calls = []

        def pred(subset):
            calls.append(frozenset(subset))
            return "c" in subset

        result = ddmin(("a", "b", "c", "d"), pred, max_tests=200)
        self.assertEqual(result.items, ("c",))
        self.assertTrue(result.complete)
        self.assertGreater(len(calls), 0)

    def test_ddmin_handles_two_causes_together(self):
        def pred(subset):
            return "a" in subset and "d" in subset
        result = ddmin(("a", "b", "c", "d"), pred, max_tests=200)
        self.assertEqual(set(result.items), {"a", "d"})

    def test_ddmin_records_leave_one_out_evidence(self):
        def pred(subset):
            return "a" in subset and "b" in subset
        result = ddmin(("a", "b", "c"), pred, max_tests=200)
        self.assertEqual(set(result.items), {"a", "b"})
        for item in result.items:
            self.assertIn(item, result.complements)
            self.assertFalse(result.complements[item])

    def test_ddmin_respects_the_test_budget(self):
        def pred(subset):
            return "z" in subset
        result = ddmin(tuple("abcdefghijklmnopqrstuvwxyz"), pred, max_tests=5)
        self.assertFalse(result.complete)
        self.assertLessEqual(result.tests, 5)

    def test_ddmin_returns_empty_when_nothing_is_needed(self):
        def pred(subset):
            return True
        result = ddmin(("a", "b"), pred, max_tests=50)
        self.assertEqual(result.items, ())
        self.assertTrue(result.complete)

    def test_ddmin_never_calls_pred_with_unhashable_input(self):
        seen = []
        def pred(subset):
            seen.append(type(subset))
            return "b" in subset
        ddmin(("a", "b"), pred, max_tests=50)
        self.assertTrue(all(t is tuple for t in seen))


if __name__ == "__main__":
    unittest.main()
