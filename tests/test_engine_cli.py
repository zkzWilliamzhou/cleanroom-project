import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from cleanroom import cli, engine
from cleanroom.config import parse_config
from cleanroom.model import KNOB_NAMES, TrialSpec


def _write(path, body):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)


class EngineTests(unittest.TestCase):
    def test_clean_command_returns_clean_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({
                "command": f"{sys.executable} -c 'print(1)'",
                "knobs": ["env"],
                "inject_env": {"IRRELEVANT": "x"},
            })
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        self.assertEqual(rep.verdict, "clean")
        self.assertEqual(rep.minimal_set, ())
        self.assertEqual(rep.findings, [])

    def test_hidden_env_var_is_attributed_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "run.py"),
                   "import os, sys\n"
                   "sys.exit(0 if os.environ.get('DEMO_LICENSE_KEY') == 'granted' else 1)\n")
            cfg = parse_config({
                "command": f"{sys.executable} run.py",
                "knobs": ["env"],
                "inject_env": {"DEMO_LICENSE_KEY": "granted"},
                "timeout": 10,
            })
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        self.assertEqual(rep.verdict, "hidden")
        self.assertIn("env", rep.minimal_set)
        details = " ".join(f.detail for f in rep.findings)
        self.assertIn("DEMO_LICENSE_KEY", details)

    def test_command_that_fails_everywhere_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({
                "command": f"{sys.executable} -c 'import sys; sys.exit(7)'",
                "knobs": ["env"],
            })
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        self.assertEqual(rep.verdict, "inconclusive")

    def test_trial_results_are_cached(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({"command": f"{sys.executable} -c 'print(1)'", "knobs": ["env"]})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        specs = [t.spec for t in rep.trials]
        self.assertEqual(len(specs), len(set(specs)))

    def test_leave_one_out_evidence_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "run.py"),
                   "import os, sys\n"
                   "ok = os.environ.get('A') == '1' and os.environ.get('B') == '2'\n"
                   "sys.exit(0 if ok else 1)\n")
            cfg = parse_config({
                "command": f"{sys.executable} run.py",
                "knobs": ["env"],
                "inject_env": {"A": "1", "B": "2"},
                "timeout": 10,
            })
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                rep = engine.evaluate(config=cfg, source=d)
        self.assertEqual(rep.verdict, "hidden")
        self.assertTrue(any("A" in f.detail and "B" in f.detail or "A" in f.detail for f in rep.findings))


class CliTests(unittest.TestCase):
    def test_version_command(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["version"])
        self.assertEqual(code, 0)
        self.assertTrue(buf.getvalue().strip())

    def test_knobs_command_lists_all_seven(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["knobs"])
        self.assertEqual(code, 0)
        for name in KNOB_NAMES:
            self.assertIn(name, buf.getvalue())

    def test_demo_reports_a_hidden_dependency(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["demo"])
        self.assertEqual(code, 1)
        self.assertIn("DEMO_LICENSE_KEY", buf.getvalue())

    def test_test_command_returns_clean_for_a_clean_command(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True):
                with redirect_stdout(buf):
                    code = cli.main(["test", f"{sys.executable} -c 'print(1)'", "--knobs", "env"])
            self.assertEqual(code, 0)
            self.assertIn("CLEAN", buf.getvalue())

    def test_output_dir_escape_is_rejected(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["test", f"{sys.executable} -c 'print(1)'", "--out", "../../escape"])
        self.assertEqual(code, 2)

    def test_invalid_config_is_a_clean_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            _write(path, '{"timeout": 0}')
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["test", "--config", path])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", buf.getvalue())

    def test_selftest_passes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["selftest"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
