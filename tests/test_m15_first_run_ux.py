"""Milestone 15 — First-Run Experience & Product UX.

Tests cover:
- Onboarding flow and state management
- Privacy guarantees
- OAuth safety (no implicit auth)
- Ollama UX
- Dashboard UX
- Accounts UX
- Cloud UX
- Settings UX
- Error handling
- Security regressions
- M14 packaging compatibility
"""

import os
import sys
import json
import types
import unittest
from unittest import mock


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

from agent.ai_agent import AIAgent  # noqa: E402
from cloud.accounts import AccountRegistry  # noqa: E402
from cloud.multi_drive import MultiAccountDriveManager  # noqa: E402
from ui.app_controller import GuardianController  # noqa: E402


# ============================================================
# HELPERS
# ============================================================


class FakeAI:
    def __init__(self):
        self.prompts = []
        self.model = "fake-model"

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class FakeProvider:
    def __init__(self, *a, **kw):
        pass

    def get_storage_info(self):
        return None


def make_controller(tmp_path=None):
    """Build a headless GuardianController with fakes."""
    agent = AIAgent()
    agent.ai = FakeAI()

    token_dir = str(tmp_path / "tokens") if tmp_path else "/tmp/tokens"

    agent.router.drive_manager = (
        MultiAccountDriveManager(
            registry=AccountRegistry(),
            token_dir=token_dir,
            provider_factory=FakeProvider,
        )
    )

    return GuardianController(agent=agent)


# ============================================================
# FIRST-RUN STATE
# ============================================================


class TestFirstRunState(unittest.TestCase):
    """app.state manages onboarding preferences safely."""

    def test_load_returns_dict_on_missing_file(self):
        import app.state as state_mod

        original = state_mod._state_path
        state_mod._state_path = lambda: "/nonexistent/path/state.json"
        try:
            result = state_mod.load()
            self.assertIsInstance(result, dict)
            self.assertFalse(result["onboarding_completed"])
        finally:
            state_mod._state_path = original

    def test_load_returns_dict_on_malformed_json(self):
        import app.state as state_mod
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("{invalid json!!!")
            f.flush()
            path = f.name

        original = state_mod._state_path
        state_mod._state_path = lambda: path
        try:
            result = state_mod.load()
            self.assertIsInstance(result, dict)
            self.assertFalse(result["onboarding_completed"])
        finally:
            state_mod._state_path = original
            try:
                os.remove(path)
            except OSError:
                pass

    def test_load_returns_dict_on_non_dict_content(self):
        import app.state as state_mod
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump("just a string", f)
            f.flush()
            path = f.name

        original = state_mod._state_path
        state_mod._state_path = lambda: path
        try:
            result = state_mod.load()
            self.assertIsInstance(result, dict)
            self.assertFalse(result["onboarding_completed"])
        finally:
            state_mod._state_path = original
            try:
                os.remove(path)
            except OSError:
                pass

    def test_save_and_load_roundtrip(self):
        import app.state as state_mod
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "preferences.json")
            original = state_mod._state_path
            state_mod._state_path = lambda: path
            try:
                state = state_mod.load()
                state["onboarding_completed"] = True
                state["onboarding_version"] = 15
                ok = state_mod.save(state)
                self.assertTrue(ok)

                loaded = state_mod.load()
                self.assertTrue(loaded["onboarding_completed"])
                self.assertEqual(loaded["onboarding_version"], 15)
            finally:
                state_mod._state_path = original

    def test_save_returns_false_on_bad_input(self):
        import app.state as state_mod

        result = state_mod.save("not a dict")
        self.assertFalse(result)

    def test_save_returns_false_on_unwritable_path(self):
        import app.state as state_mod

        original = state_mod._state_path
        state_mod._state_path = lambda: "Z:\\nonexistent\\dir\\file.json"
        try:
            result = state_mod.save({"onboarding_completed": True})
            self.assertFalse(result)
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
                ok = state_mod.mark_onboarding_completed(15)
                self.assertTrue(ok)
                self.assertTrue(state_mod.is_onboarding_completed())
            finally:
                state_mod._state_path = original

    def test_state_contains_no_secrets(self):
        import app.state as state_mod

        state = state_mod.load()
        state_str = json.dumps(state)
        for secret in ("access_token", "refresh_token", "password",
                       "oauth", "client_id", "client_secret"):
            self.assertNotIn(secret, state_str.lower())

    def test_default_state_has_required_keys(self):
        import app.state as state_mod

        state = state_mod.load()
        self.assertIn("onboarding_completed", state)
        self.assertIn("onboarding_version", state)
        self.assertIn("state_version", state)


# ============================================================
# ONBOARDING CONTROLLER
# ============================================================


class TestOnboardingStatus(unittest.TestCase):
    """Controller provides safe onboarding status."""

    def test_get_onboarding_status_returns_dict(self):
        ctrl = make_controller()
        status = ctrl.get_onboarding_status()
        self.assertIsInstance(status, dict)

    def test_onboarding_status_has_version(self):
        ctrl = make_controller()
        status = ctrl.get_onboarding_status()
        self.assertIn("version", status)

    def test_onboarding_status_has_ollama(self):
        ctrl = make_controller()
        status = ctrl.get_onboarding_status()
        self.assertIn("ollama_status", status)
        self.assertIn("ollama_available", status)

    def test_onboarding_status_has_google(self):
        ctrl = make_controller()
        status = ctrl.get_onboarding_status()
        self.assertIn("google_status", status)

    def test_onboarding_status_no_secrets(self):
        ctrl = make_controller()
        status = ctrl.get_onboarding_status()
        status_str = json.dumps(status)
        for secret in ("access_token", "refresh_token", "password",
                       "client_id", "client_secret"):
            self.assertNotIn(secret, status_str.lower())


# ============================================================
# OAUTH SAFETY
# ============================================================


class TestOAuthSafety(unittest.TestCase):
    """No implicit authentication on startup or navigation."""

    def test_startup_does_not_call_connect(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            ctrl.agent.router.execute("health")
            mock_connect.assert_not_called()

    def test_get_onboarding_status_no_connect(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            status = ctrl.get_onboarding_status()
            self.assertIsInstance(status, dict)
            mock_connect.assert_not_called()

    def test_get_settings_does_not_trigger_oauth(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            settings = ctrl.get_settings()
            self.assertIsInstance(settings, dict)
            mock_connect.assert_not_called()

    def test_connect_account_requires_explicit_action(self):
        """connect_account only runs when user clicks Connect."""
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            # Calling get_dashboard should never trigger connect
            ctrl.get_dashboard()
            mock_connect.assert_not_called()

    def test_dashboard_does_not_trigger_oauth(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            result = ctrl.get_dashboard()
            self.assertIsInstance(result, dict)
            mock_connect.assert_not_called()


# ============================================================
# OLLAMA UX
# ============================================================


class TestOllamaUX(unittest.TestCase):
    """Ollama status messages are safe and informative."""

    def test_ollama_available_message(self):
        from ui.components import safe_ollama_message
        msg = safe_ollama_message("Ready")
        self.assertIn("available", msg.lower())

    def test_ollama_unavailable_message(self):
        from ui.components import safe_ollama_message
        msg = safe_ollama_message("Unavailable")
        self.assertIn("not available", msg.lower())

    def test_ollama_no_models_message(self):
        from ui.components import safe_ollama_message
        msg = safe_ollama_message("Running (no local models found)")
        self.assertIn("running", msg.lower())
        self.assertIn("no", msg.lower())

    def test_ollama_none_message(self):
        from ui.components import safe_ollama_message
        msg = safe_ollama_message(None)
        self.assertIn("unknown", msg.lower())

    def test_ollama_status_in_settings(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        self.assertIn("ollama_status", settings)

    def test_ollama_does_not_crash_when_unavailable(self):
        from ui.components import safe_ollama_message
        for status in ("Unavailable", None, "", "Random"):
            msg = safe_ollama_message(status)
            self.assertIsInstance(msg, str)


# ============================================================
# DASHBOARD UX
# ============================================================


class TestDashboardUX(unittest.TestCase):
    """Dashboard handles all backend states gracefully."""

    def test_dashboard_returns_cards(self):
        ctrl = make_controller()
        result = ctrl.get_dashboard()
        self.assertIn("cards", result)
        self.assertIsInstance(result["cards"], list)

    def test_dashboard_with_zero_accounts(self):
        ctrl = make_controller()
        result = ctrl.get_dashboard()
        self.assertIn("cards", result)

    def test_dashboard_with_failed_backend(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute",
            return_value={"success": False, "error": "unavailable"},
        ):
            result = ctrl.get_dashboard()
            self.assertIn("cards", result)
            self.assertIsInstance(result["cards"], list)


# ============================================================
# ACCOUNTS UX
# ============================================================


class TestAccountsUX(unittest.TestCase):
    """Account display is safe and informative."""

    def test_safe_account_count_zero(self):
        from ui.components import safe_account_count
        msg = safe_account_count([])
        self.assertIn("No", msg)
        self.assertIn("connected", msg)

    def test_safe_account_count_one(self):
        from ui.components import safe_account_count
        msg = safe_account_count([{"id": "1"}])
        self.assertIn("1", msg)
        self.assertIn("connected", msg)

    def test_safe_account_count_multiple(self):
        from ui.components import safe_account_count
        msg = safe_account_count([{"id": "1"}, {"id": "2"}])
        self.assertIn("2", msg)
        self.assertIn("connected", msg)

    def test_safe_account_count_none(self):
        from ui.components import safe_account_count
        msg = safe_account_count(None)
        self.assertIn("No", msg)


# ============================================================
# CLOUD UX
# ============================================================


class TestCloudUX(unittest.TestCase):
    """Cloud messages are safe and informative."""

    def test_safe_cloud_message_none(self):
        from ui.components import safe_cloud_message
        msg = safe_cloud_message(None)
        self.assertIn("unavailable", msg.lower())

    def test_safe_cloud_message_failed(self):
        from ui.components import safe_cloud_message
        msg = safe_cloud_message({"success": False})
        self.assertIn("unavailable", msg.lower())

    def test_safe_cloud_message_auth_error(self):
        from ui.components import safe_cloud_message
        msg = safe_cloud_message(
            {"success": False, "error": "auth failed"}
        )
        self.assertIn("connection", msg.lower())

    def test_safe_cloud_message_success(self):
        from ui.components import safe_cloud_message
        msg = safe_cloud_message({"success": True})
        self.assertEqual(msg, "")

    def test_safe_connect_message_success(self):
        from ui.components import safe_connect_message
        msg = safe_connect_message(
            {"success": True, "account": {"email": "a@b.com"}}
        )
        self.assertIn("Connected", msg)
        self.assertIn("a@b.com", msg)

    def test_safe_connect_message_failure(self):
        from ui.components import safe_connect_message
        msg = safe_connect_message({"success": False})
        self.assertIn("could not be completed", msg)


# ============================================================
# SETTINGS UX
# ============================================================


class TestSettingsUX(unittest.TestCase):
    """Settings has all required sections."""

    def test_settings_has_version(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        self.assertIn("version", settings)

    def test_settings_has_account_count(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        self.assertIn("account_count", settings)

    def test_settings_has_onboarding_status(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        self.assertIn("onboarding_completed", settings)

    def test_settings_has_ollama_status(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        self.assertIn("ollama_status", settings)

    def test_settings_no_secrets(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        settings_str = json.dumps(settings)
        for secret in ("access_token", "refresh_token",
                       "client_secret", "password",
                       "client_id"):
            self.assertNotIn(secret, settings_str.lower())


# ============================================================
# ERROR HANDLING
# ============================================================


class TestErrorHandling(unittest.TestCase):
    """Backend exceptions become safe UI messages."""

    def test_safe_backend_message_none(self):
        from ui.components import safe_backend_message
        msg = safe_backend_message(None)
        self.assertIn("went wrong", msg)

    def test_safe_backend_message_exception(self):
        from ui.components import safe_backend_message
        msg = safe_backend_message(
            Exception("sensitive data here")
        )
        self.assertNotIn("sensitive", msg.lower())
        self.assertIn("went wrong", msg)

    def test_safe_text_preserves_normal_text(self):
        from ui.components import safe_text
        result = safe_text("Hello World")
        self.assertEqual(result, "Hello World")

    def test_safe_text_fallback_on_none(self):
        from ui.components import safe_text
        result = safe_text(None, "Fallback")
        self.assertEqual(result, "Fallback")

    def test_safe_text_fallback_on_empty(self):
        from ui.components import safe_text
        result = safe_text("", "Fallback")
        self.assertEqual(result, "Fallback")


# ============================================================
# SECURITY REGRESSION
# ============================================================


class TestSecurityRegression(unittest.TestCase):
    """No secrets, no implicit auth, no credential leaks."""

    def _git_tracked_files(self):
        import subprocess
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        return set(result.stdout.splitlines())

    def test_no_tracked_credentials(self):
        tracked = self._git_tracked_files()
        for name in ("credentials.json", "token.json", ".env"):
            self.assertNotIn(name, tracked)

    def test_no_token_values_in_state(self):
        import app.state as state_mod
        state = state_mod.load()
        state_str = json.dumps(state)
        self.assertNotIn("access_token", state_str)
        self.assertNotIn("refresh_token", state_str)

    def test_no_client_secrets_in_components(self):
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ui", "components.py",
        )
        with open(src_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("client_secret", content)
        self.assertNotIn("access_token", content)

    def test_no_implicit_auth_in_onboarding(self):
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ui", "views", "onboarding_view.py",
        )
        with open(src_path, encoding="utf-8") as f:
            content = f.read()
        # No OAuth-triggering calls in code (docstrings mentioning OAuth are ok)
        self.assertNotIn("connect_account", content)
        self.assertNotIn("execute(\"cloud_connect\"", content)
        self.assertNotIn(".authenticate(", content)

    def test_no_implicit_auth_in_app_startup(self):
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ui", "app.py",
        )
        with open(src_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("connect_account", content)
        self.assertNotIn("execute(\"cloud_connect\"", content)

    def test_controller_has_no_network_in_init(self):
        ctrl = make_controller()
        with mock.patch.object(
            ctrl.agent.router, "execute_google_connect"
        ) as mock_connect:
            # Just constructing and having the controller ready
            # should never trigger OAuth
            self.assertIsNotNone(ctrl)
            mock_connect.assert_not_called()


# ============================================================
# M14 PACKAGING COMPATIBILITY
# ============================================================


class TestM14Compatibility(unittest.TestCase):
    """M14 packaging infrastructure is preserved."""

    def test_version_module_exists(self):
        from app.version import __version__
        self.assertIsInstance(__version__, str)

    def test_paths_module_exists(self):
        from app.paths import app_root, user_data_dir
        self.assertIsNotNone(app_root())
        self.assertIsNotNone(user_data_dir())

    def test_env_check_module_exists(self):
        from app.env_check import run_all_checks
        results = run_all_checks()
        self.assertIsInstance(results, list)

    def test_logging_module_exists(self):
        from app.logging_setup import setup_logging
        self.assertIsNotNone(setup_logging)

    def test_spec_file_exists(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(root, "AI-Laptop-Guardian.spec")
            )
        )

    def test_build_script_exists(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(root, "scripts", "build_windows.py")
            )
        )


# ============================================================
# NAVIGATION
# ============================================================


class TestNavigationConsistency(unittest.TestCase):
    """Navigation still lists the same 7 views."""

    def test_nav_item_count(self):
        from ui.navigation import NAV_ITEMS
        self.assertEqual(len(NAV_ITEMS), 7)

    def test_nav_keys_are_strings(self):
        from ui.navigation import NAV_ITEMS
        for key, label in NAV_ITEMS:
            self.assertIsInstance(key, str)
            self.assertIsInstance(label, str)


if __name__ == "__main__":
    unittest.main()
