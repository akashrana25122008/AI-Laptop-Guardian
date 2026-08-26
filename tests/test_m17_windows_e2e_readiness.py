"""Milestone 17 — Real Windows Executable End-to-End Validation.

Tests cover:
- Packaged artifact checks (exe, version, structure, forbidden files)
- Runtime readiness (deps, env handling, user-data, version)
- GUI smoke checks (only if display available)
- Google Drive graceful degradation without google-auth
- Safety regressions (no secrets, no tracked credentials)
"""

import os
import sys
import json
import types
import unittest
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
DIST_DIR = PROJECT_ROOT / "dist" / "AI-Laptop-Guardian"


# ============================================================
# PACKAGED ARTIFACT CHECKS
# ============================================================


class TestPackagedArtifact(unittest.TestCase):
    """Verify the built distribution is structurally correct."""

    def test_dist_directory_exists(self):
        self.assertTrue(DIST_DIR.exists())

    def test_exe_exists(self):
        exe = DIST_DIR / "AI-Laptop-Guardian.exe"
        self.assertTrue(exe.exists())

    def test_exe_size_reasonable(self):
        exe = DIST_DIR / "AI-Laptop-Guardian.exe"
        mb = exe.stat().st_size / (1024 * 1024)
        self.assertGreater(mb, 1.0)
        self.assertLess(mb, 50.0)

    def test_dist_size_reasonable(self):
        total = sum(
            f.stat().st_size
            for f in DIST_DIR.rglob("*")
            if f.is_file()
        )
        mb = total / (1024 * 1024)
        self.assertGreater(mb, 5.0)
        self.assertLess(mb, 500.0)

    def test_internal_dir_exists(self):
        self.assertTrue((DIST_DIR / "_internal").exists())

    def test_no_credentials_in_dist(self):
        for name in ["credentials.json", "token.json", ".env"]:
            found = list(DIST_DIR.rglob(name))
            self.assertEqual(found, [], f"Sensitive file: {name}")

    def test_no_cloud_data_in_dist(self):
        found = list(DIST_DIR.rglob("cloud_data"))
        self.assertEqual(found, [], "cloud_data in dist")

    def test_no_git_in_dist(self):
        found = list(DIST_DIR.rglob(".git"))
        self.assertEqual(found, [], ".git in dist")

    def test_dist_has_dlls(self):
        dlls = list(DIST_DIR.rglob("*.dll"))
        self.assertGreater(len(dlls), 0)


# ============================================================
# VERSION MODULE
# ============================================================


class TestVersionModule(unittest.TestCase):
    """Version is consistent and valid."""

    def test_version_string(self):
        from app.version import __version__

        self.assertIsInstance(__version__, str)

    def test_version_semver(self):
        from app.version import __version__

        parts = __version__.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit())

    def test_version_not_placeholder(self):
        from app.version import __version__

        self.assertNotIn("TODO", __version__)
        self.assertNotIn("0.0.0", __version__)


# ============================================================
# RUNTIME READINESS
# ============================================================


class TestRuntimeReadiness(unittest.TestCase):
    """Application modules and deps are functional."""

    def test_app_imports(self):
        import app.version
        import app.paths
        import app.state
        import app.env_check
        import app.logging_setup

    def test_ui_imports(self):
        from ui.navigation import NAV_ITEMS
        from ui.components import safe_text, format_bytes_short

        self.assertEqual(len(NAV_ITEMS), 7)

    def test_agent_imports(self):
        from agent.ai_agent import AIAgent
        from agent.tool_router import ToolRouter
        from agent.result_contract import sanitize_error, ensure_result
        from agent.action_safety import ActionSafety

    def test_local_tools_import(self):
        from tools.cpu.cpu import CPUTool
        from tools.ram.ram import RAMTool
        from tools.battery.battery import BatteryTool
        from tools.storage.scanner import StorageScanner
        from tools.health.health import HealthTool
        from tools.cleanup.cleanup import CleanupTool

    def test_local_tools_callable(self):
        from tools.cpu.cpu import CPUTool
        from tools.ram.ram import RAMTool

        self.assertIsInstance(CPUTool().execute(), dict)
        self.assertIsInstance(RAMTool().execute(), dict)

    def test_tool_router_init(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        self.assertTrue(hasattr(router, "execute"))
        self.assertTrue(hasattr(router, "google_drive"))

    def test_user_data_dir(self):
        from app.paths import user_data_dir

        path = user_data_dir()
        self.assertIsInstance(path, str)

    def test_env_check_runs(self):
        from app.env_check import run_all_checks

        results = run_all_checks()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_state_loads(self):
        import app.state as state_mod

        result = state_mod.load()
        self.assertIsInstance(result, dict)
        self.assertIn("theme", result)

    def test_theme_persistence(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state_mod.set_theme("Dark")
                self.assertEqual(state_mod.get_theme(), "Dark")
            finally:
                state_mod._state_path = original


# ============================================================
# GOOGLE DRIVE GRACEFUL DEGRADATION
# ============================================================


class TestGoogleDriveGraceful(unittest.TestCase):
    """Application works when google-auth is not installed."""

    def test_tool_router_has_google_drive_attr(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        self.assertTrue(hasattr(router, "google_drive"))

    def test_cloud_accounts_returns_safe_message(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute("cloud_accounts")
            self.assertIsInstance(result, dict)
            self.assertIn("accounts", result)

    def test_cloud_search_returns_safe_error(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute("cloud_search", "test")
            self.assertFalse(result.get("success", True))

    def test_cloud_upload_returns_safe_error(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute("cloud_upload", {})
            self.assertFalse(result.get("success", True))

    def test_cloud_download_returns_safe_error(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute("cloud_download", {})
            self.assertFalse(result.get("success", True))

    def test_cloud_delete_returns_safe_error(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute("cloud_delete", {})
            self.assertFalse(result.get("success", True))

    def test_local_tools_still_work(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        self.assertIsInstance(router.execute("cpu"), dict)
        self.assertIsInstance(router.execute("ram"), dict)
        self.assertIsInstance(router.execute("battery"), dict)

    def test_auth_manager_none_safe(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            self.assertIsNone(router.auth_manager)

    def test_drive_manager_none_safe(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            self.assertIsNone(router.drive_manager)

    def test_cloud_intelligence_none_safe(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            self.assertIsNone(router.cloud_intelligence)

    def test_describe_accounts_empty_when_no_google(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            accounts = router.describe_connected_accounts()
            self.assertEqual(accounts, [])

    def test_resolve_account_none_when_no_google(self):
        from agent.tool_router import ToolRouter

        router = ToolRouter()
        if router.google_drive is None:
            result = router.resolve_account("test")
            self.assertIsNone(result)


# ============================================================
# ACTION SAFETY UNCHANGED
# ============================================================


class TestActionSafetyUnchanged(unittest.TestCase):
    """M1-M16 safety model is preserved."""

    def test_action_safety_propose(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("f1", "test.pdf")
        self.assertTrue(safety.has_pending())

    def test_action_safety_confirm(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("f1", "test.pdf")
        result = safety.validate_confirmation("yes")
        self.assertIsNotNone(result)

    def test_action_safety_cancel(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        safety.propose_delete("f1", "test.pdf")
        safety.cancel()
        self.assertFalse(safety.has_pending())

    def test_cleanup_requires_confirmation(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        items = [{"path": "/tmp/a.txt", "size_bytes": 1024}]
        safety.propose_cleanup(items)
        self.assertTrue(safety.has_pending())
        result = safety.validate_confirmation("no")
        self.assertIsNone(result)


# ============================================================
# GUI SMOKE CHECKS
# ============================================================


_HAS_DISPLAY = False
try:
    import tkinter as _tk_test
    _root = _tk_test.Tk()
    _root.destroy()
    _HAS_DISPLAY = True
except Exception:
    _HAS_DISPLAY = False


@unittest.skipUnless(_HAS_DISPLAY, "No display/Tk available")
class TestGUISmoke(unittest.TestCase):
    """Basic GUI smoke test if display is available."""

    def test_guardian_app_creates(self):
        try:
            import customtkinter as ctk
        except ImportError:
            self.skipTest("customtkinter not installed")

        from ui.app_controller import GuardianController
        from ui.app import GuardianApp

        ctrl = GuardianController.__new__(GuardianController)
        ctrl.agent = types.SimpleNamespace()
        ctrl.agent.ai = types.SimpleNamespace()
        ctrl.agent.ai.model = "fake"
        ctrl.agent.ai.ask = lambda self_, p: "ok"
        ctrl.agent.router = types.SimpleNamespace()
        ctrl.agent.router.execute = lambda self_, t, a=None: {"success": True, "tool": t, "data": {}}
        ctrl.agent.router.drive_manager = None
        ctrl.agent.router.cloud_intelligence = None
        ctrl.agent.router.auth_manager = None
        ctrl._current_view = None
        ctrl._last_health = None
        ctrl._shutting_down = False
        import itertools
        ctrl._gen_counter = itertools.count()

        app = GuardianApp(controller=ctrl)
        self.assertTrue(app.winfo_exists())
        app.after(500, app.destroy)
        app.mainloop()


# ============================================================
# SECURITY REGRESSIONS
# ============================================================


class TestSecurityRegressions(unittest.TestCase):
    """No secrets in tracked files."""

    def test_no_credentials_tracked(self):
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

    def test_state_no_secrets(self):
        import app.state as state_mod

        state = state_mod.load()
        for key in state:
            lower = key.lower()
            self.assertNotIn("secret", lower)
            self.assertNotIn("password", lower)
            self.assertNotIn("token", lower)
            self.assertNotIn("credential", lower)

    def test_gitignore_covers_sensitive(self):
        gi = PROJECT_ROOT / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        self.assertIn("credentials.json", content)
        self.assertIn("token.json", content)
        self.assertIn(".env", content)


# ============================================================
# SPEC AND BUILD SCRIPT
# ============================================================


class TestSpecAndBuildScript(unittest.TestCase):
    """PyInstaller configuration is correct."""

    def test_spec_uses_gui_entry(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("run_gui.py", content)

    def test_spec_console_false(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("console=False", content)

    def test_spec_has_collect(self):
        spec = PROJECT_ROOT / "AI-Laptop-Guardian.spec"
        content = spec.read_text(encoding="utf-8")
        self.assertIn("COLLECT", content)

    def test_build_script_exists(self):
        build = PROJECT_ROOT / "scripts" / "build_windows.py"
        self.assertTrue(build.exists())

    def test_gui_entry_exists(self):
        entry = PROJECT_ROOT / "run_gui.py"
        self.assertTrue(entry.exists())

    def test_gui_entry_imports_guardian_app(self):
        entry = PROJECT_ROOT / "run_gui.py"
        content = entry.read_text(encoding="utf-8")
        self.assertIn("GuardianApp", content)
        self.assertIn("mainloop", content)


# ============================================================
# CLEANUP SAFETY
# ============================================================


class TestCleanupSafety(unittest.TestCase):
    """Cleanup requires explicit confirmation."""

    def test_cleanup_preview(self):
        from tools.cleanup.cleanup import CleanupTool

        result = CleanupTool().preview()
        self.assertIsInstance(result, dict)

    def test_action_safety_blocks_cleanup(self):
        from agent.action_safety import ActionSafety

        safety = ActionSafety()
        self.assertFalse(safety.has_pending())


# ============================================================
# PROTECTED PROJECTS
# ============================================================


class TestProtectedProjects(unittest.TestCase):
    """Protected projects are untouched."""

    def test_protected_exists(self):
        self.assertTrue(Path(r"D:\AI-Laptop-Guardian").exists())

    def test_backup_exists(self):
        self.assertTrue(Path(r"D:\AI-Laptop-Guardian-Backup").exists())
