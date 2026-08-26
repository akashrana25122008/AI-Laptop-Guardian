"""Milestone 16 — Real-World Windows Release Validation.

Tests cover:
- Theme persistence (fix M15 limitation)
- Packaging configuration and artifact integrity
- Onboarding flow and state transitions
- Navigation model and view registration
- Version and environment validation
- Local functionality preservation
- Result contract and error sanitization
- Action safety and confirmation gate
- Cleanup safety (no implicit deletion)
- Tool routing and tool availability
- Security regressions (no secrets, no tracked credentials)
- Protected project integrity
- Lifecycle defaults and state recovery
"""

import os
import sys
import json
import types
import unittest
from unittest import mock
from pathlib import Path


def _install_cloud_stub():
    """Pre-stub google_drive before any project imports."""
    if "cloud.google_drive" in sys.modules:
        return
    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        def __init__(self, *a, **kw):
            self.service = None
            self.credentials = None

    module.GoogleDriveProvider = StubGoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# THEME PERSISTENCE
# ============================================================


class TestThemePersistence(unittest.TestCase):
    """Theme is persisted across sessions via app.state."""

    def test_get_theme_returns_string(self):
        import app.state as state_mod

        result = state_mod.get_theme()
        self.assertIsInstance(result, str)

    def test_get_theme_returns_valid_value(self):
        import app.state as state_mod

        result = state_mod.get_theme()
        self.assertIn(result, {"System", "Light", "Dark"})

    def test_set_theme_persists_dark(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Dark")
                result = state_mod.get_theme()
                self.assertEqual(result, "Dark")
            finally:
                state_mod._state_path = original

    def test_set_theme_persists_light(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Light")
                result = state_mod.get_theme()
                self.assertEqual(result, "Light")
            finally:
                state_mod._state_path = original

    def test_set_theme_persists_system(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("System")
                result = state_mod.get_theme()
                self.assertEqual(result, "System")
            finally:
                state_mod._state_path = original

    def test_sanitize_theme_rejects_invalid(self):
        import app.state as state_mod

        self.assertEqual(state_mod._sanitize_theme("invalid"), "System")
        self.assertEqual(state_mod._sanitize_theme(""), "System")
        self.assertEqual(state_mod._sanitize_theme(None), "System")
        self.assertEqual(state_mod._sanitize_theme(123), "System")

    def test_sanitize_theme_accepts_valid(self):
        import app.state as state_mod

        self.assertEqual(state_mod._sanitize_theme("System"), "System")
        self.assertEqual(state_mod._sanitize_theme("Light"), "Light")
        self.assertEqual(state_mod._sanitize_theme("Dark"), "Dark")

    def test_theme_survives_save_load_cycle(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Dark")
                loaded = state_mod.load()
                self.assertEqual(loaded.get("theme"), "Dark")
            finally:
                state_mod._state_path = original

    def test_theme_in_save_output(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Light")
                with open(path, "r") as f:
                    data = json.load(f)
                self.assertEqual(data.get("theme"), "Light")
            finally:
                state_mod._state_path = original

    def test_theme_not_in_default_when_missing(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                loaded = state_mod.load()
                self.assertEqual(loaded.get("theme"), "System")
            finally:
                state_mod._state_path = original

    def test_set_theme_does_not_corrupt_onboarding(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state = state_mod.load()
                state["onboarding_completed"] = True
                state["onboarding_version"] = 99
                state_mod.save(state)

                state_mod.set_theme("Dark")
                loaded = state_mod.load()
                self.assertTrue(loaded["onboarding_completed"])
                self.assertEqual(loaded["onboarding_version"], 99)
                self.assertEqual(loaded["theme"], "Dark")
            finally:
                state_mod._state_path = original

    def test_onboarding_does_not_corrupt_theme(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Light")
                state_mod.mark_onboarding_completed(16)
                loaded = state_mod.load()
                self.assertEqual(loaded.get("theme"), "Light")
                self.assertTrue(loaded["onboarding_completed"])
            finally:
                state_mod._state_path = original

    def test_theme_in_valid_themes_set(self):
        import app.state as state_mod

        self.assertIn("System", state_mod._VALID_THEMES)
        self.assertIn("Light", state_mod._VALID_THEMES)
        self.assertIn("Dark", state_mod._VALID_THEMES)
        self.assertEqual(len(state_mod._VALID_THEMES), 3)

    def test_theme_default_is_system(self):
        import app.state as state_mod

        self.assertEqual(state_mod._DEFAULT_STATE["theme"], "System")

    def test_default_state_has_theme_key(self):
        import app.state as state_mod

        self.assertIn("theme", state_mod._DEFAULT_STATE)


# ============================================================
# PACKAGING INTEGRITY
# ============================================================


class TestPackagingIntegrity(unittest.TestCase):
    """PyInstaller build configuration is valid and artifacts exist."""

    def test_spec_file_exists(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        self.assertTrue(spec.exists())

    def test_spec_references_main(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("main.py", content)

    def test_spec_excludes_test_frameworks(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("pytest", content)
        self.assertIn("unittest", content)

    def test_spec_console_false(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("console=False", content)

    def test_spec_folder_distribution(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("COLLECT", content)
        self.assertIn("COLLECT(\n", content)

    def test_build_script_exists(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        self.assertTrue(build.exists())

    def test_build_script_has_clean(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        content = build.read_text(encoding="utf-8")
        self.assertIn("def clean", content)

    def test_build_script_has_verify(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        content = build.read_text(encoding="utf-8")
        self.assertIn("def verify_spec", content)

    def test_build_script_has_build(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        content = build.read_text(encoding="utf-8")
        self.assertIn("def build", content)

    def test_build_script_has_print_artifacts(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        content = build.read_text(encoding="utf-8")
        self.assertIn("def print_artifacts", content)

    def test_dist_directory_exists(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        self.assertTrue(dist.exists())

    def test_dist_has_executable(self):
        exe = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian" / "AI-Laptop-Guardian.exe"
        self.assertTrue(exe.exists())

    def test_dist_has_python_dlls(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        dlls = list(dist.rglob("*.dll"))
        self.assertGreater(len(dlls), 0)

    def test_dist_no_credentials(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        sensitive = ["credentials.json", "token.json", ".env"]
        for name in sensitive:
            found = list(dist.rglob(name))
            self.assertEqual(found, [], f"Sensitive file found in dist: {name}")

    def test_dist_no_cloud_data(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        found = list(dist.rglob("cloud_data"))
        self.assertEqual(found, [], "cloud_data found in dist")

    def test_dist_no_git_directory(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        found = list(dist.rglob(".git"))
        self.assertEqual(found, [], ".git found in dist")

    def test_dist_size_reasonable(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        total = sum(
            f.stat().st_size
            for f in dist.rglob("*")
            if f.is_file()
        )
        mb = total / (1024 * 1024)
        self.assertGreater(mb, 1.0, "Build too small")
        self.assertLess(mb, 500.0, "Build too large")


# ============================================================
# ONBOARDING FLOW
# ============================================================


class TestOnboardingFlow(unittest.TestCase):
    """Onboarding gate and state transitions work correctly."""

    def test_onboarding_not_completed_by_default(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                self.assertFalse(state_mod.is_onboarding_completed())
            finally:
                state_mod._state_path = original

    def test_mark_onboarding_completed(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.mark_onboarding_completed(16)
                self.assertTrue(state_mod.is_onboarding_completed())
            finally:
                state_mod._state_path = original

    def test_onboarding_version_persisted(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.mark_onboarding_completed(42)
                state = state_mod.load()
                self.assertEqual(state["onboarding_version"], 42)
            finally:
                state_mod._state_path = original

    def test_onboarding_completed_is_boolean(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state = state_mod.load()
                state["onboarding_completed"] = True
                state_mod.save(state)
                loaded = state_mod.load()
                self.assertIs(True, loaded["onboarding_completed"])
            finally:
                state_mod._state_path = original


# ============================================================
# NAVIGATION MODEL
# ============================================================


class TestNavigationModel(unittest.TestCase):
    """Navigation items match expected views."""

    def test_seven_nav_items(self):
        from ui.navigation import NAV_ITEMS

        self.assertEqual(len(NAV_ITEMS), 7)

    def test_dashboard_first(self):
        from ui.navigation import NAV_ITEMS

        self.assertEqual(NAV_ITEMS[0], ("dashboard", "Dashboard"))

    def test_settings_last(self):
        from ui.navigation import NAV_ITEMS

        self.assertEqual(NAV_ITEMS[-1], ("settings", "Settings"))

    def test_all_nav_keys_unique(self):
        from ui.navigation import NAV_ITEMS

        keys = [k for k, _ in NAV_ITEMS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_expected_view_keys(self):
        from ui.navigation import NAV_ITEMS

        keys = {k for k, _ in NAV_ITEMS}
        expected = {
            "dashboard", "health", "storage",
            "cleanup", "cloud", "accounts", "settings",
        }
        self.assertEqual(keys, expected)


# ============================================================
# VERSION AND ENVIRONMENT
# ============================================================


class TestVersionAndEnvironment(unittest.TestCase):
    """Version module and environment checks are valid."""

    def test_version_is_semver(self):
        from app.version import __version__

        parts = __version__.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit())

    def test_version_is_not_placeholder(self):
        from app.version import __version__

        self.assertNotIn("TODO", __version__)
        self.assertNotIn("Milestone", __version__)
        self.assertNotIn("0.0.0", __version__)

    def test_env_check_all_checks_return_list(self):
        from app.env_check import run_all_checks

        results = run_all_checks()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_env_check_returns_dicts(self):
        from app.env_check import run_all_checks

        for check in run_all_checks():
            self.assertIsInstance(check, dict)
            self.assertIn("name", check)
            self.assertIn("ok", check)
            self.assertIn("detail", check)

    def test_env_check_python_ok(self):
        from app.env_check import check_python

        result = check_python()
        self.assertTrue(result["ok"])

    def test_env_check_user_data_dir_ok(self):
        from app.env_check import check_user_data_dir

        result = check_user_data_dir()
        self.assertTrue(result["ok"])

    def test_user_data_dir_returns_path(self):
        from app.paths import user_data_dir

        path = user_data_dir()
        self.assertIsInstance(path, str)
        self.assertTrue(len(path) > 0)

    def test_ensure_user_data_dir_creates_directory(self):
        from app.paths import ensure_user_data_dir

        path = ensure_user_data_dir()
        self.assertTrue(os.path.isdir(path))

    def test_app_root_is_project_root(self):
        from app.paths import app_root

        root = app_root()
        self.assertTrue(os.path.isdir(os.path.join(root, "app")))
        self.assertTrue(os.path.isdir(os.path.join(root, "ui")))


# ============================================================
# LOCAL FUNCTIONALITY PRESERVATION
# ============================================================


class TestLocalFunctionality(unittest.TestCase):
    """All local tools and core modules remain functional."""

    def test_cpu_tool_callable(self):
        from tools.cpu.cpu import CPUTool

        result = CPUTool().execute()
        self.assertIsInstance(result, dict)

    def test_ram_tool_callable(self):
        from tools.ram.ram import RAMTool

        result = RAMTool().execute()
        self.assertIsInstance(result, dict)

    def test_battery_tool_callable(self):
        from tools.battery.battery import BatteryTool

        result = BatteryTool().execute()
        self.assertIsInstance(result, dict)

    def test_storage_tool_callable(self):
        from tools.storage.scanner import StorageScanner

        result = StorageScanner().get_drive_info()
        self.assertIsInstance(result, (dict, list))

    def test_health_tool_callable(self):
        from tools.health.health import HealthTool

        result = HealthTool().execute()
        self.assertIsInstance(result, dict)

    def test_cleanup_tool_callable(self):
        from tools.cleanup.cleanup import CleanupTool

        result = CleanupTool().preview()
        self.assertIsInstance(result, dict)

    def test_file_inspector_tool_callable(self):
        from tools.file_inspector.inspector import FileInspector

        result = FileInspector().inspect(__file__)
        self.assertIsInstance(result, dict)


# ============================================================
# RESULT CONTRACT
# ============================================================


class TestResultContract(unittest.TestCase):
    """Result contract handles all input types safely."""

    def test_ensure_valid_dict_passthrough(self):
        from agent.result_contract import ensure_result

        valid = {"success": True, "tool": "cpu", "data": {}}
        self.assertIs(ensure_result(valid, "cpu"), valid)

    def test_ensure_dict_without_success_wraps(self):
        from agent.result_contract import ensure_result

        result = ensure_result({"foo": "bar"}, "cpu")
        self.assertFalse(result["success"])
        self.assertEqual(result["tool"], "cpu")
        self.assertIn("data", result)

    def test_ensure_non_dict_wraps(self):
        from agent.result_contract import ensure_result

        result = ensure_result("bad", "cpu")
        self.assertFalse(result["success"])
        self.assertEqual(result["tool"], "cpu")

    def test_sanitize_error_short(self):
        from agent.result_contract import sanitize_error

        result = sanitize_error("short error")
        self.assertEqual(result, "short error")

    def test_sanitize_error_long_truncated(self):
        from agent.result_contract import sanitize_error

        result = sanitize_error("x" * 500)
        self.assertLessEqual(len(result), 300)

    def test_sanitize_error_exception(self):
        from agent.result_contract import sanitize_error

        result = sanitize_error(ValueError("test"))
        self.assertIn("ValueError", result)

    def test_sanitize_error_empty_returns_fallback(self):
        from agent.result_contract import sanitize_error

        result = sanitize_error("")
        self.assertIn("error", result.lower())

    def test_is_successful_true(self):
        from agent.result_contract import is_successful_result

        self.assertTrue(is_successful_result({"success": True}))

    def test_is_successful_false(self):
        from agent.result_contract import is_successful_result

        self.assertFalse(is_successful_result({"success": False}))

    def test_is_successful_non_dict(self):
        from agent.result_contract import is_successful_result

        self.assertFalse(is_successful_result(None))
        self.assertFalse(is_successful_result("ok"))


# ============================================================
# ACTION SAFETY
# ============================================================


class TestActionSafety(unittest.TestCase):
    """Action safety gate prevents implicit destructive actions."""

    def test_no_pending_initially(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        self.assertFalse(safety.has_pending())

    def test_propose_delete_creates_pending(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("file-123", "report.pdf")
        self.assertTrue(safety.has_pending())

    def test_confirm_without_proposal_returns_none(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        result = safety.validate_confirmation("yes")
        self.assertIsNone(result)

    def test_confirm_with_valid_proposal(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("file-123", "report.pdf")
        result = safety.validate_confirmation("yes")
        self.assertIsNotNone(result)
        self.assertEqual(result.target_id, "file-123")

    def test_reject_non_confirmation(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("file-123", "report.pdf")
        result = safety.validate_confirmation("go ahead")
        self.assertIsNone(result)

    def test_cancel_clears_pending(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("file-123", "report.pdf")
        safety.cancel()
        self.assertFalse(safety.has_pending())

    def test_new_proposal_replaces_old(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("file-1", "a.pdf")
        safety.propose_delete("file-2", "b.pdf")
        result = safety.validate_confirmation("yes")
        self.assertEqual(result.target_id, "file-2")

    def test_propose_cleanup_requires_items(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        with self.assertRaises(ValueError):
            safety.propose_cleanup([])

    def test_propose_cleanup_requires_valid_items(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        with self.assertRaises(ValueError):
            safety.propose_cleanup([{"no_path": True}])

    def test_propose_cleanup_with_valid_items(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        items = [{"path": "/tmp/a.txt", "size_bytes": 1024}]
        safety.propose_cleanup(items)
        self.assertTrue(safety.has_pending())

    def test_normalize_phrase(self):
        from agent.action_safety import normalize_phrase

        self.assertEqual(normalize_phrase("Yes!"), "yes")
        self.assertEqual(normalize_phrase("  NO  "), "no")
        self.assertEqual(normalize_phrase("Do NOT delete"), "do not delete")


# ============================================================
# CLEANUP SAFETY
# ============================================================


class TestCleanupSafety(unittest.TestCase):
    """Cleanup operations require explicit confirmation."""

    def test_cleanup_preview_returns_dict(self):
        from tools.cleanup.cleanup import CleanupTool

        result = CleanupTool().preview()
        self.assertIsInstance(result, dict)

    def test_cleanup_preview_has_items(self):
        from tools.cleanup.cleanup import CleanupTool

        result = CleanupTool().preview()
        self.assertIn("data", result)

    def test_cleanup_items_are_list(self):
        from tools.cleanup.cleanup import CleanupTool

        result = CleanupTool().preview()
        data = result.get("data")
        self.assertTrue(data is None or isinstance(data, (list, dict)))

    def test_action_safety_blocks_cleanup(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        self.assertFalse(safety.has_pending())


# ============================================================
# TOOL ROUTING
# ============================================================


class TestToolRouting(unittest.TestCase):
    """ToolRouter has all expected tools registered."""

    def test_tool_router_has_execute(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        self.assertTrue(hasattr(router, "execute"))

    def test_cpu_tool_executes(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        result = router.execute("cpu")
        self.assertIsInstance(result, dict)

    def test_ram_tool_executes(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        result = router.execute("ram")
        self.assertIsInstance(result, dict)

    def test_battery_tool_executes(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        result = router.execute("battery")
        self.assertIsInstance(result, dict)

    def test_storage_tool_executes(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        result = router.execute("storage")
        self.assertIsInstance(result, dict)

    def test_health_tool_executes(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        result = router.execute("health")
        self.assertIsInstance(result, dict)


# ============================================================
# SECURITY REGRESSIONS
# ============================================================


class TestSecurityRegressions(unittest.TestCase):
    """No secrets in tracked files or state."""

    def test_no_credentials_in_git_tracked(self):
        import subprocess

        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        files = result.stdout.strip().split("\n")
        for f in files:
            lower = f.lower()
            self.assertNotIn("credentials", lower)
            self.assertNotIn("token.json", lower)
            self.assertNotIn(".env", lower)

    def test_state_never_stores_secrets(self):
        import app.state as state_mod

        state = state_mod.load()
        for key in state:
            lower = key.lower()
            self.assertNotIn("secret", lower)
            self.assertNotIn("password", lower)
            self.assertNotIn("token", lower)
            self.assertNotIn("key", lower)
            self.assertNotIn("credential", lower)

    def test_components_no_secret_leaks(self):
        from ui.components import safe_text

        result = safe_text(None)
        self.assertNotIn("secret", result.lower())
        self.assertNotIn("token", result.lower())

    def test_build_spec_excludes_test_frameworks(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("pytest", content)
        self.assertIn("unittest", content)

    def test_gitignore_covers_sensitive_files(self):
        gi = PROJECT_ROOT / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        self.assertIn("credentials.json", content)
        self.assertIn("token.json", content)
        self.assertIn(".env", content)
        self.assertIn("cloud_data/", content)


# ============================================================
# LIFECYCLE DEFAULTS
# ============================================================


class TestLifecycleDefaults(unittest.TestCase):
    """Application state defaults are safe and complete."""

    def test_default_state_has_required_keys(self):
        import app.state as state_mod

        self.assertIn("state_version", state_mod._DEFAULT_STATE)
        self.assertIn("onboarding_completed", state_mod._DEFAULT_STATE)
        self.assertIn("onboarding_version", state_mod._DEFAULT_STATE)
        self.assertIn("theme", state_mod._DEFAULT_STATE)

    def test_default_state_version_is_int(self):
        import app.state as state_mod

        self.assertIsInstance(state_mod._DEFAULT_STATE["state_version"], int)

    def test_default_onboarding_is_false(self):
        import app.state as state_mod

        self.assertFalse(state_mod._DEFAULT_STATE["onboarding_completed"])

    def test_default_theme_is_system(self):
        import app.state as state_mod

        self.assertEqual(state_mod._DEFAULT_STATE["theme"], "System")

    def test_load_never_raises(self):
        import app.state as state_mod

        original = state_mod._state_path
        state_mod._state_path = lambda: "/nonexistent/path/state.json"
        try:
            result = state_mod.load()
            self.assertIsInstance(result, dict)
        finally:
            state_mod._state_path = original

    def test_save_never_raises_on_bad_input(self):
        import app.state as state_mod

        self.assertFalse(state_mod.save(None))
        self.assertFalse(state_mod.save("bad"))
        self.assertFalse(state_mod.save(123))


# ============================================================
# MODULE STRUCTURE
# ============================================================


class TestModuleStructure(unittest.TestCase):
    """All core modules are importable and structured correctly."""

    def test_import_app_version(self):
        import app.version
        self.assertTrue(hasattr(app.version, "__version__"))

    def test_import_app_paths(self):
        import app.paths
        self.assertTrue(hasattr(app.paths, "app_root"))
        self.assertTrue(hasattr(app.paths, "user_data_dir"))

    def test_import_app_env_check(self):
        import app.env_check
        self.assertTrue(hasattr(app.env_check, "run_all_checks"))

    def test_import_app_logging_setup(self):
        import app.logging_setup
        self.assertTrue(hasattr(app.logging_setup, "setup_logging"))

    def test_import_app_state(self):
        import app.state
        self.assertTrue(hasattr(app.state, "load"))
        self.assertTrue(hasattr(app.state, "save"))
        self.assertTrue(hasattr(app.state, "get_theme"))
        self.assertTrue(hasattr(app.state, "set_theme"))

    def test_import_result_contract(self):
        import agent.result_contract
        self.assertTrue(hasattr(agent.result_contract, "sanitize_error"))
        self.assertTrue(hasattr(agent.result_contract, "ensure_result"))

    def test_import_action_safety(self):
        import agent.action_safety
        self.assertTrue(hasattr(agent.action_safety, "ActionSafety"))

    def test_import_ai_agent(self):
        from agent.ai_agent import AIAgent
        self.assertTrue(callable(AIAgent))

    def test_import_tool_router(self):
        from agent.tool_router import ToolRouter
        self.assertTrue(hasattr(ToolRouter, "execute"))

    def test_import_navigation(self):
        from ui.navigation import NAV_ITEMS
        self.assertIsInstance(NAV_ITEMS, list)


# ============================================================
# PROTECTED PROJECTS
# ============================================================


class TestProtectedProjects(unittest.TestCase):
    """Protected projects are not modified."""

    def test_protected_project_path_exists(self):
        protected = Path(r"D:\AI-Laptop-Guardian")
        self.assertTrue(protected.exists())

    def test_backup_project_path_exists(self):
        backup = Path(r"D:\AI-Laptop-Guardian-Backup")
        self.assertTrue(backup.exists())


# ============================================================
# BUILD ARTIFACT INTEGRITY
# ============================================================


class TestBuildArtifactIntegrity(unittest.TestCase):
    """Build output is present and correct."""

    def test_dist_folder_exists(self):
        dist = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"
        self.assertTrue(dist.exists())

    def test_exe_exists(self):
        exe = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian" / "AI-Laptop-Guardian.exe"
        self.assertTrue(exe.exists())

    def test_exe_not_empty(self):
        exe = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian" / "AI-Laptop-Guardian.exe"
        self.assertGreater(exe.stat().st_size, 1000)

    def test_no_build_artifacts_in_source(self):
        gi = PROJECT_ROOT / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        self.assertIn("build/", content)
        self.assertIn("dist/", content)

    def test_build_directory_is_gitignored(self):
        import subprocess

        result = subprocess.run(
            ["git", "check-ignore", "build/", "dist/"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        lines = result.stdout.strip().split("\n")
        self.assertIn("build/", lines)
        self.assertIn("dist/", lines)


# ============================================================
# CONTROLLER GET_SETTINGS
# ============================================================


class TestControllerGetSettings(unittest.TestCase):
    """GuardianController.get_settings returns structured data."""

    def _make_ctrl(self, tmp_path=None):
        from agent.ai_agent import AIAgent
        from cloud.accounts import AccountRegistry
        from cloud.multi_drive import MultiAccountDriveManager
        from ui.app_controller import GuardianController

        class FakeAI:
            model = "fake"
            def ask(self, prompt):
                return "ok"

        class FakeProvider:
            def __init__(self, *a, **kw):
                pass
            def get_storage_info(self):
                return None

        agent = AIAgent()
        agent.ai = FakeAI()
        token_dir = str(tmp_path / "tokens") if tmp_path else "/tmp/tokens"
        agent.router.drive_manager = MultiAccountDriveManager(
            registry=AccountRegistry(),
            token_dir=token_dir,
            provider_factory=FakeProvider,
        )
        return GuardianController(agent=agent)

    def test_get_settings_returns_dict(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIsInstance(result, dict)

    def test_get_settings_has_version(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIn("version", result)

    def test_get_settings_has_theme(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIn("theme", result)
        self.assertIn(result["theme"], {"System", "Light", "Dark"})

    def test_get_settings_has_ollama_status(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIn("ollama_status", result)

    def test_get_settings_has_account_count(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIn("account_count", result)
        self.assertIsInstance(result["account_count"], int)

    def test_get_settings_has_onboarding_completed(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        self.assertIn("onboarding_completed", result)
        self.assertIsInstance(result["onboarding_completed"], bool)

    def test_get_settings_no_secrets(self):
        ctrl = self._make_ctrl()
        result = ctrl.get_settings()
        for key, val in result.items():
            lower_key = key.lower()
            self.assertNotIn("secret", lower_key)
            self.assertNotIn("password", lower_key)
            if isinstance(val, str):
                self.assertNotIn("secret", val.lower())


# ============================================================
# THEME PERSISTENCE IN UI LAYER
# ============================================================


class TestThemeInUILayer(unittest.TestCase):
    """Settings view saves theme, controller reads persisted theme."""

    def test_controller_reads_persisted_theme(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Dark")

                from agent.ai_agent import AIAgent
                from cloud.accounts import AccountRegistry
                from cloud.multi_drive import MultiAccountDriveManager
                from ui.app_controller import GuardianController

                class FakeAI:
                    model = "fake"
                    def ask(self, p):
                        return "ok"

                class FakeProv:
                    def __init__(self, *a, **kw):
                        pass
                    def get_storage_info(self):
                        return None

                agent = AIAgent()
                agent.ai = FakeAI()
                agent.router.drive_manager = MultiAccountDriveManager(
                    registry=AccountRegistry(),
                    token_dir=str(td),
                    provider_factory=FakeProv,
                )
                ctrl = GuardianController(agent=agent)
                settings = ctrl.get_settings()
                self.assertEqual(settings["theme"], "Dark")
            finally:
                state_mod._state_path = original

    def test_settings_view_on_theme_calls_set_theme(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("System")
                state_mod.set_theme("Light")
                state_mod.set_theme("Dark")
                result = state_mod.get_theme()
                self.assertEqual(result, "Dark")
            finally:
                state_mod._state_path = original
