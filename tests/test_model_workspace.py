import os
import tempfile
import unittest
from unittest import mock

from cleanroom.config import parse_config
from cleanroom.hostsnapshot import capture
from cleanroom.model import KNOBS, KNOB_NAMES, Report, Trial, TrialSpec
from cleanroom.workspace import prepare


class ModelTests(unittest.TestCase):
    def test_knob_partition_is_complete_and_unique(self):
        self.assertEqual(len(KNOBS), 7)
        self.assertEqual(len(KNOB_NAMES), len(set(KNOB_NAMES)))
        self.assertEqual(set(KNOB_NAMES), {"env", "dotfiles", "path", "artifacts", "locale", "network", "clock"})
        for knob in KNOBS:
            self.assertTrue(knob.description)
            self.assertTrue(knob.fix_hint)

    def test_trial_spec_is_hashable_and_distinguishable(self):
        a = TrialSpec(knobs=frozenset({"env"}), env_names=frozenset({"A"}))
        b = TrialSpec(knobs=frozenset({"env"}), env_names=frozenset({"A"}))
        c = TrialSpec(knobs=frozenset({"env"}), env_names=frozenset({"B"}))
        self.assertEqual(a, b)
        self.assertEqual(len({a, b, c}), 2)

    def test_report_to_dict_is_deterministic(self):
        trial = Trial(spec=TrialSpec(frozenset()), exit_code=0, passed=True, timed_out=False,
                      error=None, stdout_tail="ok", stderr_tail="", duration_ms=1,
                      runs=1, flaky=False)
        report = Report(verdict="clean", command="make", knobs=KNOB_NAMES, trials=[trial],
                        findings=[], minimal_set=(), confidence="full", notes=(), limits={})
        self.assertEqual(report.to_dict(), report.to_dict())
        self.assertIn("schema_version", report.to_dict())


class SnapshotTests(unittest.TestCase):
    def test_capture_partitions_path_and_injected_vars(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({"command": "make", "inject_env": {"DEMO_KEY": "yes"}})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/opt/bin", "LANG": "en_US.UTF-8"}, clear=True):
                snap = capture(d, cfg)
            self.assertEqual(snap.path_entries, ("/usr/bin", "/opt/bin"))
            self.assertEqual(snap.env["DEMO_KEY"], "yes")
            self.assertEqual(snap.env["LANG"], "en_US.UTF-8")

    def test_capture_finds_only_existing_artifact_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "dist"))
            cfg = parse_config({"command": "make"})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
                snap = capture(d, cfg)
            self.assertIn("dist", snap.artifacts)
            self.assertNotIn("node_modules", snap.artifacts)

    def test_capture_never_raises_on_missing_dotfiles(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = parse_config({"command": "make"})
            with mock.patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": d}, clear=True):
                snap = capture(d, cfg)
            self.assertIsInstance(snap.dotfiles, dict)


class WorkspaceTests(unittest.TestCase):
    def _snapshot(self, source):
        cfg = parse_config({"command": "make", "inject_env": {"DEMO_KEY": "yes", "OTHER_KEY": "no"}})
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/opt/bin", "LANG": "C"}, clear=True):
            return capture(source, cfg), cfg

    def test_clean_env_owns_home_tmp_and_path(self):
        with tempfile.TemporaryDirectory() as d:
            snap, cfg = self._snapshot(d)
            p = prepare(TrialSpec(frozenset()), snap, cfg)
            try:
                self.assertEqual(p.env["HOME"], p.home)
                self.assertTrue(p.env["PATH"].startswith("/usr/bin"))
                self.assertNotIn("DEMO_KEY", p.env)
                self.assertEqual(p.env["LANG"], "C")
                self.assertTrue(os.path.isdir(p.cwd))
            finally:
                p.cleanup()

    def test_restoring_env_does_not_override_home_or_tmpdir(self):
        with tempfile.TemporaryDirectory() as d:
            snap, cfg = self._snapshot(d)
            p = prepare(TrialSpec(frozenset({"env"})), snap, cfg)
            try:
                self.assertEqual(p.env["HOME"], p.home)
                self.assertEqual(p.env["DEMO_KEY"], "yes")
                self.assertEqual(p.env["TMPDIR"], p.root)
            finally:
                p.cleanup()

    def test_env_names_subset_restricts_restored_variables(self):
        with tempfile.TemporaryDirectory() as d:
            snap, cfg = self._snapshot(d)
            spec = TrialSpec(frozenset({"env"}), env_names=frozenset({"DEMO_KEY"}))
            p = prepare(spec, snap, cfg)
            try:
                self.assertEqual(p.env["DEMO_KEY"], "yes")
                self.assertNotIn("OTHER_KEY", p.env)
                self.assertEqual(p.env["LANG"], "C")
            finally:
                p.cleanup()

    def test_artifacts_are_excluded_unless_the_knob_is_restored(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "keep.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            os.mkdir(os.path.join(d, "dist"))
            with open(os.path.join(d, "dist", "built.js"), "w", encoding="utf-8") as fh:
                fh.write("built\n")
            snap, cfg = self._snapshot(d)
            clean = prepare(TrialSpec(frozenset()), snap, cfg)
            try:
                self.assertTrue(os.path.isfile(os.path.join(clean.cwd, "keep.py")))
                self.assertFalse(os.path.exists(os.path.join(clean.cwd, "dist")))
            finally:
                clean.cleanup()
            dirty = prepare(TrialSpec(frozenset({"artifacts"})), snap, cfg)
            try:
                self.assertTrue(os.path.isfile(os.path.join(dirty.cwd, "dist", "built.js")))
            finally:
                dirty.cleanup()

    def test_symlinks_are_skipped_and_never_followed(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            with open(os.path.join(outside, "secret.txt"), "w", encoding="utf-8") as fh:
                fh.write("secret")
            os.symlink(os.path.join(outside, "secret.txt"), os.path.join(d, "link.txt"))
            snap, cfg = self._snapshot(d)
            p = prepare(TrialSpec(frozenset()), snap, cfg)
            try:
                self.assertFalse(os.path.exists(os.path.join(p.cwd, "link.txt")))
            finally:
                p.cleanup()

    def test_oversized_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "big.bin"), "wb") as fh:
                fh.write(b"x" * (security_limit() + 1))
            with open(os.path.join(d, "small.txt"), "w", encoding="utf-8") as fh:
                fh.write("ok")
            snap, cfg = self._snapshot(d)
            p = prepare(TrialSpec(frozenset()), snap, cfg)
            try:
                self.assertFalse(os.path.exists(os.path.join(p.cwd, "big.bin")))
                self.assertTrue(os.path.isfile(os.path.join(p.cwd, "small.txt")))
            finally:
                p.cleanup()

    def test_cleanup_removes_the_temp_tree(self):
        with tempfile.TemporaryDirectory() as d:
            snap, cfg = self._snapshot(d)
            p = prepare(TrialSpec(frozenset()), snap, cfg)
            root = p.root
            self.assertTrue(os.path.isdir(root))
            p.cleanup()
            self.assertFalse(os.path.exists(root))
            p.cleanup()


def security_limit():
    from cleanroom.security import MAX_FILE_BYTES
    return MAX_FILE_BYTES


if __name__ == "__main__":
    unittest.main()
