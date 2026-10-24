"""Configuration validation and real atomic file operations; no bot or ADB."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from config import json_store
from config.user_overrides import normalize_user_settings, load_user_settings, apply_overrides_to_settings
from config.validation import validate_workflows
import test_founders as helpers

ROOT = Path(__file__).resolve().parent.parent


class SettingsValidationTests(unittest.TestCase):
    def test_visibility_overrides_and_legacy_level_switch_have_one_canonical_value(self):
        payload = {"startup_defaults": {"gem_statistics_enabled": False,
                   "screenshot_visible": False, "detect_level_enabled": False},
                   "detect_level": {"DETECT_LEVEL_ENABLED": True}}
        result = normalize_user_settings(payload)
        self.assertNotIn("DETECT_LEVEL_ENABLED", result["detect_level"])
        self.assertTrue(result["startup_defaults"]["detect_level_enabled"])
        self.assertEqual(normalize_user_settings(result), result)
        settings = {}
        apply_overrides_to_settings(settings, result)
        self.assertFalse(settings["GEM_STATISTICS_ENABLED_DEFAULT"])
        self.assertFalse(settings["SCREENSHOT_VISIBLE_DEFAULT"])
        self.assertTrue(settings["DETECT_LEVEL_ENABLED"])
        result["startup_defaults"]["detect_level_enabled"] = False
        apply_overrides_to_settings(settings, result)
        self.assertFalse(settings["DETECT_LEVEL_ENABLED"])

    def test_rejects_invalid_shapes_types_and_ranges(self):
        invalid = [None, [], {"adb": []}, {"unknown": {}},
            {"adb": {"ADB_AUTO_CONNECT": "false"}}, {"adb": {"ADB_MAX_RETRIES": 0}},
            {"adb": {"ADB_SCAN_PORTS": [65536]}}, {"adb": {"ADB_SCAN_PORTS": [True]}},
            {"startup_defaults": {"freebies_enabled": 1}},
            {"freebies": {"FREEBIES_MATCH_THRESHOLD": 1.1}},
            {"freebies": {"FREEBIES_TAP_JITTER_PX": -1}},
            {"freebies": {"FREEBIES_SCROLL_ATTEMPTS": 1.5}},
            {"founders": {"FOUNDERS_DETECT_ROI": [1, 2, 1, 8]}},
            {"founders": {"FOUNDERS_TEMPLATE": "../outside.png"}},
            {"lootbug": {"LOOTBUG_CHECK_INTERVAL_S": 0}},
            {"lootbug": {"LOOTBUG_INTERVAL_VARIANCE_PCT": 101}},
            {"workflows": {"WORKFLOWS_SCREEN_REUSE_AGE_S": float("nan")}},
            {"workflows": {"WORKFLOWS_BUSY_RETRY_S": float("inf")}},
            {"workflows": {"WORKFLOWS_BUSY_RETRY_S": 10 ** 1000}},
            {"screenshot_capture": {"SCREENSHOT_RETRY_DELAY_S": 10 ** 1000}},
            {"scroll": {"SCROLL_DEFAULT_SPEED": "typo"}},
            {"scroll": {"SCROLL_DEFAULT_AREA": [0, 0, 10, 10], "SCROLL_EDGE_PADDING_PX": 5}},
            {"screenshot_viewer": {"SCREENSHOT_VIEWER_FILES": ["../secret.png"]}}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                normalize_user_settings(data)

    def test_invalid_local_settings_warn_without_changing_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "config").mkdir()
            path = root / "config/user_settings.json"
            path.write_text('{"freebies":{"FREEBIES_CHECK_INTERVAL_S":-1}}')
            original = path.read_bytes()
            with self.assertWarns(RuntimeWarning):
                self.assertEqual(load_user_settings(root), {})
            self.assertEqual(path.read_bytes(), original)


class WorkflowValidationTests(unittest.TestCase):
    def test_rejects_malformed_steps_and_conditions(self):
        bad_steps = [None, {"type": "typo"}, {"type": []},
            {"type": "tap_xy", "x": True, "y": 1},
            {"type": "tap_roi", "roi": [1, 2, 1, 4]},
            {"type": "wait", "seconds": float("nan")},
            {"type": "tap_xy", "x": 1, "y": 2, "count": -1},
            {"type": "call_workflow", "target": "absent"},
            {"type": "click_template", "template": "../secret"},
            {"type": "if", "branches": "bad"},
            {"type": "if", "branches": [{"condition": {"kind": "level_eq", "value": None}}]},
            {"type": "if", "else_steps": [{"type": "if"}]}]
        for step in bad_steps:
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_workflows({"wf": {"steps": [step]}})
        for data in (None, [], {"wf": []}, {"wf": {"interval_s": -1}},
                     {"wf": {"ignore_action_lock": "false"}}, {"wf": {"steps": None}}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_workflows(data)

    def test_preserves_optional_semantics_drafts_and_legacy_default_scroll(self):
        data = {"wf": {"interval_variance_pct": None, "log_level": "", "steps": [
            {"type": "swipe", "area": [0], "count": None, "duration_ms": None},
            {"type": "click_template", "template": "x", "optional": True, "roi": [], "hold_ms": None},
            {"type": "call_workflow", "target": "", "_disabled": True}]}}
        original = copy.deepcopy(data)
        result = validate_workflows(data)
        self.assertIsNone(result["wf"]["steps"][0]["area"])
        self.assertEqual(data, original)
        self.assertEqual(validate_workflows({}), {})  # deleting the last WF stays deleted

    def test_builtins_validate_without_local_json(self):
        module = helpers.load_module("workflow_defaults_validation", "config/config_workflows.py")
        self.assertTrue(validate_workflows(module._DEFAULT_WORKFLOWS))

    def test_local_loader_accepts_empty_document_and_never_mutates_active_definitions(self):
        module = helpers.load_module("workflow_loader_validation", "config/config_workflows.py")
        active = module.WORKFLOWS
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "config").mkdir()
            path = root / "config/user_workflows.json"
            with patch.object(module, "BASE_DIR", root):
                self.assertEqual(module.load_workflow_definitions(), validate_workflows(module._DEFAULT_WORKFLOWS))
                path.write_text("{}")
                self.assertEqual(module.load_workflow_definitions(), {})
                for content in ("{broken", "[]", '{"a":{"steps":[{"type":"unknown"}]}}'):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        module.load_workflow_definitions()
                    self.assertIs(module.WORKFLOWS, active)
                    self.assertEqual(path.read_text(), content)


class AtomicStorageTests(unittest.TestCase):
    def test_replace_or_fsync_failure_preserves_original_and_cleans_staging(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "config.json"
            json_store.atomic_write_json(path, {"old": True})
            original = path.read_bytes()
            for phase in ("replace", "fsync"):
                with self.subTest(phase=phase), patch.object(json_store.os, phase, side_effect=OSError("disk failure")):
                    with self.assertRaises(OSError):
                        json_store.atomic_write_json(path, {"new": True})
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(path.parent.iterdir()), [path])
            with self.assertRaises(ValueError):
                json_store.atomic_write_json(path, {"bad": float("nan")})
            self.assertEqual(path.read_bytes(), original)

    def test_parallel_readers_and_writers_only_see_complete_documents(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "config.json"
            json_store.atomic_write_json(path, {"n": 0, "payload": "x" * 20000})
            def work(n):
                if n % 2:
                    json_store.atomic_write_json(path, {"n": n, "payload": "x" * 20000})
                read = json_store.read_json(path)
                self.assertEqual(read["payload"], "x" * 20000)
                self.assertIsInstance(read["n"], int)
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(work, range(60)))
            self.assertEqual(list(path.parent.iterdir()), [path])


class ConfigApiSafetyTests(unittest.TestCase):
    def test_invalid_payloads_and_disk_failures_never_overwrite_and_return_json(self):
        api = helpers.load_module("safe_config_api", "web/config_api.py")
        app = Flask(__name__)
        app.register_blueprint(api.config_bp)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            (root / "config").mkdir()
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"):
                client = app.test_client()
                for endpoint, filename, good, bad in (
                    ("settings", "user_settings.json", {"adb": {"ADB_AUTO_CONNECT": False}},
                     {"adb": {"ADB_AUTO_CONNECT": "false"}}),
                    ("workflows/full", "user_workflows.json", {"a": {"steps": []}},
                     {"a": {"steps": [{"type": "call_workflow", "target": "absent"}]}})):
                    url = "/api/config/" + endpoint
                    self.assertEqual(client.post(url, json=good).status_code, 200)
                    path = root / "config" / filename
                    original = path.read_bytes()
                    for payload in (bad, [], None):
                        response = client.post(url, data=json.dumps(payload), content_type="application/json")
                        self.assertEqual(response.status_code, 400, response.get_json())
                        self.assertFalse(response.get_json()["ok"])
                        self.assertEqual(path.read_bytes(), original)
                    for kwargs in ({"data": "{broken", "content_type": "application/json"},
                                   {"data": "{}", "content_type": "text/plain"}):
                        self.assertEqual(client.post(url, **kwargs).status_code, 400)
                        self.assertEqual(path.read_bytes(), original)
                    with patch.object(json_store.os, "replace", side_effect=OSError("blocked")):
                        self.assertEqual(client.post(url, json=good).status_code, 500)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertFalse(list(path.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
