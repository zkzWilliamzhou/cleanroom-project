import json
import unittest

from cleanroom import report as R
from cleanroom.model import Finding, Report, Trial, TrialSpec


def _report(verdict="hidden"):
    spec = TrialSpec(frozenset({"env"}))
    trials = [
        Trial(spec=TrialSpec(frozenset()), exit_code=1, passed=False, timed_out=False,
              error=None, stdout_tail="", stderr_tail="missing", duration_ms=137,
              runs=1, flaky=False),
        Trial(spec=spec, exit_code=0, passed=True, timed_out=False,
              error=None, stdout_tail="ok", stderr_tail="", duration_ms=42,
              runs=1, flaky=False),
    ]
    findings = [Finding(knob="env", detail="DEMO_KEY", evidence="without it the command exits 1",
                        fix="declare DEMO_KEY in CI", confidence="full")]
    return Report(verdict=verdict, command="make test", knobs=("env",), trials=trials,
                  findings=findings, minimal_set=("env",), confidence="full",
                  notes=("best-effort network controls are not a sandbox",),
                  limits={"max_trials": 80, "timeout": 30})


class ReportTests(unittest.TestCase):
    def test_terminal_render_contains_verdict_and_fix(self):
        out = R.render_terminal(_report())
        self.assertIn("HIDDEN", out)
        self.assertIn("DEMO_KEY", out)
        self.assertIn("declare DEMO_KEY in CI", out)

    def test_terminal_render_marks_clean_verdict(self):
        self.assertIn("CLEAN", R.render_terminal(_report("clean")))

    def test_json_render_is_serializable_and_has_schema(self):
        data = R.render_json(_report())
        encoded = json.dumps(data)
        self.assertIn("schema_version", encoded)
        self.assertEqual(data["verdict"], "hidden")

    def test_markdown_render_is_shareable(self):
        out = R.render_markdown(_report())
        self.assertTrue(out.startswith("#"))
        self.assertIn("DEMO_KEY", out)

    def test_sarif_is_valid_2_1_0_with_results(self):
        sarif = R.render_sarif(_report())
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(len(sarif["runs"]), 1)
        self.assertEqual(len(sarif["runs"][0]["results"]), 1)
        json.dumps(sarif)

    def test_annotations_render_github_workflow_commands(self):
        out = R.render_annotations(_report())
        self.assertIn("::error", out)

    def test_canonical_strips_volatile_timing_and_paths(self):
        a = _report()
        b = _report()
        b.trials[0].duration_ms = 99999
        b.trials[1].duration_ms = 1
        self.assertEqual(R.canonical_json(a), R.canonical_json(b))

    def test_canonical_detects_a_real_function_change(self):
        a = _report()
        b = _report()
        b.findings[0].detail = "A_DIFFERENT_VARIABLE"
        self.assertNotEqual(R.canonical_json(a), R.canonical_json(b))

    def test_explain_renders_a_loaded_report(self):
        data = R.render_json(_report())
        out = R.explain(data)
        self.assertIn("DEMO_KEY", out)

    def test_report_to_dict_roundtrips_trials(self):
        data = _report().to_dict()
        self.assertEqual(len(data["trials"]), 2)
        self.assertEqual(data["trials"][0]["passed"], False)


if __name__ == "__main__":
    unittest.main()
