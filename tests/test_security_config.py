import os
import tempfile
import unittest
from unittest import mock

from cleanroom import security
from cleanroom.config import ConfigError, default_config_dict, load_config, parse_config
from cleanroom.model import KNOB_NAMES


class SecurityTests(unittest.TestCase):
    def test_is_secret_name_matches_common_secret_names(self):
        for name in ("NPM_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD", "api-key", "GH_TOKEN"):
            self.assertTrue(security.is_secret_name(name), name)

    def test_is_secret_name_ignores_ordinary_names(self):
        for name in ("PATH", "LANG", "CI", "NODE_ENV", "HOME"):
            self.assertFalse(security.is_secret_name(name), name)

    def test_redact_hides_bearer_tokens_and_key_values(self):
        text = "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        out = security.redact(text)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", out)
        self.assertIn(security.REDACTED, out)

    def test_redact_hides_url_credentials_and_pem_blocks(self):
        out = security.redact("url=https://bob:hunter2@example.com/secret")
        self.assertNotIn("hunter2", out)
        pem = "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----"
        self.assertNotIn("QUJD", security.redact(pem))

    def test_redact_leaves_ordinary_text_alone(self):
        self.assertEqual(security.redact("build finished in 2s"), "build finished in 2s")

    def test_redact_env_masks_only_secret_values(self):
        env = {"PATH": "/usr/bin", "NPM_TOKEN": "super-secret", "CI": "true"}
        out = security.redact_env(env)
        self.assertEqual(out["PATH"], "/usr/bin")
        self.assertEqual(out["CI"], "true")
        self.assertEqual(out["NPM_TOKEN"], security.REDACTED)

    def test_contained_rejects_traversal_and_absolute_escape(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(security.contained(root, os.path.join(root, "a", "b")))
            self.assertFalse(security.contained(root, os.path.join(root, "..", "escape")))
            self.assertFalse(security.contained(root, "/etc/passwd"))

    def test_is_probably_binary_detects_nul_bytes(self):
        self.assertTrue(security.is_probably_binary(b"abc\x00def"))
        self.assertFalse(security.is_probably_binary(b"plain text\n"))


class ConfigTests(unittest.TestCase):
    def test_defaults_are_parseable(self):
        cfg = parse_config(default_config_dict())
        self.assertEqual(cfg.timeout, security.DEFAULT_TIMEOUT)
        self.assertEqual(cfg.knobs, KNOB_NAMES)

    def test_command_can_be_supplied_separately(self):
        cfg = parse_config({}, base_command="make test")
        self.assertEqual(cfg.command, "make test")

    def test_missing_command_raises(self):
        with self.assertRaises(ConfigError):
            parse_config({})

    def test_unknown_key_raises(self):
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", "typo_key": 1})

    def test_invalid_types_and_ranges_raise(self):
        for bad in (
            {"command": "make", "timeout": 0},
            {"command": "make", "timeout": "30"},
            {"command": "make", "repeat": 0},
            {"command": "make", "max_trials": 0},
            {"command": "make", "format": "xml"},
            {"command": "make", "knobs": ["bogus"]},
            {"command": ""},
        ):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                parse_config(bad)

    def test_inject_env_validates_names_and_values(self):
        cfg = parse_config({"command": "make", "inject_env": {"A": "1", "B_TOKEN": "x"}})
        self.assertEqual(cfg.inject_env["A"], "1")
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", "inject_env": {"bad name": "1"}})
        with self.assertRaises(ConfigError):
            parse_config({"command": "make", "inject_env": {"A": 5}})

    def test_load_config_reads_json_from_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, ".cleanroom.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"command": "make test", "timeout": 12}')
            cfg = load_config(path)
            self.assertEqual(cfg.command, "make test")
            self.assertEqual(cfg.timeout, 12)

    def test_load_config_rejects_invalid_json_and_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("not json")
            with self.assertRaises(ConfigError):
                load_config(bad)
            arr = os.path.join(d, "arr.json")
            with open(arr, "w", encoding="utf-8") as fh:
                fh.write("[]")
            with self.assertRaises(ConfigError):
                load_config(arr)

    def test_parse_does_not_read_real_environment(self):
        with mock.patch.dict(os.environ, {"HOME": "/somewhere"}, clear=True):
            cfg = parse_config({"command": "make"})
            self.assertNotIn("HOME", cfg.inject_env)


if __name__ == "__main__":
    unittest.main()
