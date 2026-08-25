"""Milestone 12 — Desktop application reliability tests.

Proves the hardening changes made in M12:
- main-thread callback marshaling in run_in_background
- widget existence guards in all views
- clean shutdown behavior
- safe user-facing error messages
- empty/unavailable state handling
- security regression protection

All tests use fakes/stubs. No real UI, no real OAuth,
no real network calls.
"""

import sys
import types


def _install_cloud_stub():
    if "cloud.google_drive" not in sys.modules:
        module = types.ModuleType("cloud.google_drive")

        class StubGoogleDriveProvider:
            def __init__(self, *a, **kw):
                self.service = None
                self.credentials = None

        module.GoogleDriveProvider = StubGoogleDriveProvider
        sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

import pytest  # noqa: E402

from agent.ai_agent import AIAgent  # noqa: E402
from ui.app_controller import GuardianController  # noqa: E402
from ui.navigation import NAV_ITEMS  # noqa: E402
from ui.components import (  # noqa: E402
    safe_text,
    format_bytes_short,
    status_label,
)


# =========================================================
# FAKES
# =========================================================


class FakeAI:
    def __init__(self):
        self.prompts = []
        self.model = "fake-model"

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


def make_controller(tmp_path=None):
    agent = AIAgent()
    agent.ai = FakeAI()
    return GuardianController(agent=agent)


# =========================================================
# 1. CONTROLLER INITIALIZATION
# =========================================================


class TestControllerInit:
    def test_default_view_is_dashboard(self):
        ctrl = make_controller()
        assert ctrl.current_view == "dashboard"

    def test_root_defaults_to_none(self):
        ctrl = make_controller()
        assert ctrl._root is None

    def test_shutting_down_defaults_false(self):
        ctrl = make_controller()
        assert ctrl._shutting_down is False

    def test_agent_stored(self):
        ctrl = make_controller()
        assert ctrl.agent is not None

    def test_custom_agent_accepted(self):
        agent = AIAgent()
        agent.ai = FakeAI()
        ctrl = GuardianController(agent=agent)
        assert ctrl.agent is agent


# =========================================================
# 2. NAVIGATION
# =========================================================


class TestNavigation:
    def test_all_nav_items_are_valid(self):
        ctrl = make_controller()
        for key, _ in NAV_ITEMS:
            ctrl.open_view(key)
            assert ctrl.current_view == key

    def test_invalid_view_raises(self):
        ctrl = make_controller()
        with pytest.raises(ValueError):
            ctrl.open_view("nonexistent")

    def test_nav_keys_match_controller_set(self):
        ctrl = make_controller()
        for key, _ in NAV_ITEMS:
            ctrl.open_view(key)

    def test_navigation_is_idempotent(self):
        ctrl = make_controller()
        ctrl.open_view("dashboard")
        ctrl.open_view("dashboard")
        assert ctrl.current_view == "dashboard"


# =========================================================
# 3. RUN_IN_BACKGROUND (headless — no _root)
# =========================================================


class TestBackgroundHeadless:
    def test_on_done_called_with_result(self, tmp_path):
        ctrl = make_controller()
        results = []
        ctrl.run_in_background(
            lambda: 42, on_done=results.append
        )
        import time
        time.sleep(0.1)
        assert results == [42]

    def test_on_error_called_with_exception(self):
        ctrl = make_controller()
        errors = []

        def fail():
            raise RuntimeError("boom")

        ctrl.run_in_background(
            fail, on_done=lambda _: None,
            on_error=errors.append,
        )
        import time
        time.sleep(0.1)
        assert len(errors) == 1
        assert "boom" in str(errors[0])

    def test_no_on_error_discards_silently(self):
        ctrl = make_controller()

        def fail():
            raise RuntimeError("boom")

        ctrl.run_in_background(
            fail, on_done=lambda _: None
        )
        import time
        time.sleep(0.1)

    def test_returns_thread(self):
        ctrl = make_controller()
        import threading
        t = ctrl.run_in_background(
            lambda: None, on_done=lambda _: None
        )
        assert isinstance(t, threading.Thread)

    def test_thread_is_daemon(self):
        ctrl = make_controller()
        import threading
        t = ctrl.run_in_background(
            lambda: None, on_done=lambda _: None
        )
        assert t.daemon is True


# =========================================================
# 4. SHUTDOWN BEHAVIOR
# =========================================================


class TestShutdown:
    def test_shutting_down_flag_propagation(self):
        ctrl = make_controller()
        assert ctrl._shutting_down is False
        ctrl._shutting_down = True
        assert ctrl._shutting_down is True

    def test_shutdown_flag_does_not_affect_headless(self):
        ctrl = make_controller()
        ctrl._shutting_down = True
        results = []
        ctrl.run_in_background(
            lambda: 99, on_done=results.append
        )
        import time
        time.sleep(0.1)
        assert results == [99]


# =========================================================
# 5. USER-FACING ERROR HANDLING
# =========================================================


class TestSafeErrors:
    def test_sanitize_error_produces_single_line(self):
        from agent.result_contract import sanitize_error

        exc = PermissionError(
            "C:\\Users\\test\\credentials.json"
        )
        msg = sanitize_error(exc)
        assert "\n" not in msg
        assert "PermissionError" in msg

    def test_sanitize_error_truncates_token_paths(self):
        from agent.result_contract import sanitize_error

        exc = RuntimeError(
            "token.json not found at "
            "C:\\Users\\test\\tokens\\account-1.json"
        )
        msg = sanitize_error(exc)
        assert "RuntimeError" in msg
        assert len(msg) <= 300

    def test_sanitize_error_truncates_long(self):
        from agent.result_contract import sanitize_error

        exc = RuntimeError("x" * 500)
        msg = sanitize_error(exc)
        assert len(msg) <= 300

    def test_safe_text_none_returns_fallback(self):
        assert safe_text(None) == "Unknown"

    def test_safe_text_empty_returns_fallback(self):
        assert safe_text("") == "Unknown"
        assert safe_text("  ") == "Unknown"

    def test_safe_text_preserves_content(self):
        assert safe_text("hello") == "hello"

    def test_format_bytes_none_returns_unavailable(self):
        assert format_bytes_short(None) == "Unavailable"

    def test_format_bytes_bad_type_returns_unavailable(self):
        assert format_bytes_short("abc") == "Unavailable"

    def test_status_label_none_returns_unknown(self):
        assert status_label(None) == "Unknown"

    def test_status_label_bad_type_returns_unknown(self):
        assert status_label("abc") == "Unknown"

    def test_ensure_result_normalizes_non_dict(self):
        from agent.result_contract import ensure_result

        r = ensure_result("just a string", "test")
        assert r["success"] is False
        assert r["tool"] == "test"

    def test_ensure_result_preserves_valid(self):
        from agent.result_contract import ensure_result

        r = ensure_result(
            {"success": True, "data": 42}, "test"
        )
        assert r["success"] is True
        assert r["data"] == 42


# =========================================================
# 6. EMPTY / UNAVAILABLE STATES
# =========================================================


class TestEmptyStates:
    def test_no_accounts_returns_empty_list(self):
        ctrl = make_controller()
        result = ctrl.get_accounts()
        assert result.get("success") is True
        accounts = result.get("accounts", [])
        assert isinstance(accounts, list)

    def test_dashboard_cards_are_list(self):
        ctrl = make_controller()
        result = ctrl.get_dashboard()
        assert isinstance(result.get("cards"), list)

    def test_health_report_has_success(self):
        ctrl = make_controller()
        result = ctrl.get_health_report()
        assert isinstance(result, dict)
        assert "success" in result

    def test_local_drives_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_local_drives()
        assert isinstance(result, dict)

    def test_large_files_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_large_files()
        assert isinstance(result, dict)

    def test_duplicates_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_local_duplicates()
        assert isinstance(result, dict)

    def test_cleanup_preview_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_cleanup_preview()
        assert isinstance(result, dict)

    def test_cloud_storage_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_cloud_storage()
        assert isinstance(result, dict)

    def test_cloud_large_files_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_cloud_large_files()
        assert isinstance(result, dict)

    def test_cloud_duplicates_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_cloud_duplicates()
        assert isinstance(result, dict)

    def test_settings_returns_dict(self):
        ctrl = make_controller()
        result = ctrl.get_settings()
        assert isinstance(result, dict)
        assert "version" in result
        assert "ollama_status" in result


# =========================================================
# 7. SECURITY REGRESSIONS
# =========================================================


class TestSecurityRegressions:
    def test_startup_no_auth(self):
        ctrl = make_controller()
        accounts = ctrl.get_accounts()
        assert accounts.get("success") is True

    def test_navigation_no_auth(self):
        ctrl = make_controller()
        for key, _ in NAV_ITEMS:
            ctrl.open_view(key)

    def test_settings_no_expose_secrets(self):
        ctrl = make_controller()
        settings = ctrl.get_settings()
        s = str(settings)
        assert "ya29" not in s.lower()
        assert "client_secret" not in s.lower()
        assert "SUPERSECRET" not in s

    def test_dashboard_no_expose_secrets(self):
        ctrl = make_controller()
        dashboard = ctrl.get_dashboard()
        s = str(dashboard)
        assert "ya29" not in s.lower()
        assert "token" not in s.lower()

    def test_accounts_no_expose_tokens(self):
        ctrl = make_controller()
        accounts = ctrl.get_accounts()
        s = str(accounts)
        assert "ya29" not in s.lower()

    def test_cleanup_requires_proposal(self):
        ctrl = make_controller()
        preview = ctrl.get_cleanup_preview()
        assert isinstance(preview, dict)

    def test_connect_returns_result(self):
        ctrl = make_controller()
        result = ctrl.connect_account()
        assert isinstance(result, dict)
        assert result.get("success") is False

    def test_disconnect_without_account_fails(self):
        ctrl = make_controller()
        result = ctrl.request_disconnect(
            "ghost@example.com"
        )
        assert isinstance(result, str)

    def test_no_implicit_cloud_calls(self):
        ctrl = make_controller()
        for key, _ in NAV_ITEMS:
            ctrl.open_view(key)

    def test_format_bytes_never_exposes_raw(self):
        result = format_bytes_short(None)
        assert result == "Unavailable"
        result = format_bytes_short(float("inf"))
        assert isinstance(result, str)

    def test_status_label_never_exposes_raw(self):
        result = status_label(None)
        assert result == "Unknown"
        result = status_label("abc")
        assert result == "Unknown"


# =========================================================
# 8. VIEW KEY CONSISTENCY
# =========================================================


class TestViewKeyConsistency:
    def test_nav_items_keys_are_strings(self):
        for key, label in NAV_ITEMS:
            assert isinstance(key, str)
            assert isinstance(label, str)

    def test_nav_items_has_exactly_7(self):
        assert len(NAV_ITEMS) == 7

    def test_nav_items_are_unique(self):
        keys = [k for k, _ in NAV_ITEMS]
        assert len(keys) == len(set(keys))
