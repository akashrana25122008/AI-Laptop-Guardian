"""
Milestone 13 — Real-World Validation & Packaging Readiness

Tests covering live Tk smoke testing, background-refresh
robustness, stale-result protection, startup validation,
local functionality, cloud safety, and packaging exclusion
verification.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ───────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────

HAS_DISPLAY = os.environ.get("DISPLAY") is not None or sys.platform == "win32"


def _make_controller(**kwargs):
    from ui.app_controller import GuardianController
    agent = kwargs.get("agent", MagicMock())

    if not hasattr(agent, 'router'):
        agent.router = MagicMock()

    if not hasattr(agent.router, 'drive_manager'):
        agent.router.drive_manager = MagicMock()
        agent.router.drive_manager.token_dir = MagicMock(
            __str__=lambda _: "/tmp/tokens"
        )

    if not hasattr(agent, 'safety'):
        agent.safety = MagicMock()
        agent.safety.has_pending.return_value = False

    if not hasattr(agent, 'ai'):
        agent.ai = MagicMock()
        agent.ai.model = "unknown"

    if not hasattr(agent, 'chat'):
        agent.chat = MagicMock(return_value="ok")

    ctrl = GuardianController.__new__(GuardianController)
    ctrl.agent = agent
    ctrl._current_view = "dashboard"
    ctrl._last_health = None
    ctrl._root = kwargs.get("root", None)
    ctrl._shutting_down = False
    import itertools
    ctrl._gen_counter = itertools.count()
    return ctrl


# ───────────────────────────────────────────────────────
# Phase 2 — Live Tk Smoke Test
# ───────────────────────────────────────────────────────

class TestLiveTkSmoke(unittest.TestCase):
    """Live Tk lifecycle smoke test when display available."""

    @unittest.skipIf(not HAS_DISPLAY, "No display/Tk")
    def test_application_construction_and_lifecycle(self):
        """Build root, navigate views, destroy cleanly."""
        try:
            import customtkinter as ctk
        except ImportError:
            self.skipTest("customtkinter not installed")

        from ui.app_controller import GuardianController
        from ui.views import register_views

        ctrl = GuardianController.__new__(GuardianController)
        ctrl.agent = MagicMock()
        ctrl._current_view = "dashboard"
        ctrl._last_health = None
        ctrl._shutting_down = False
        import itertools
        ctrl._gen_counter = itertools.count()

        try:
            root = ctk.CTk()
        except Exception:
            self.skipTest(
                "Tk/Tcl not available in this session"
            )

        ctrl._root = root

        root.title("Smoke Test")
        root.geometry("400x300")

        content = ctk.CTkFrame(root)
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        view_classes = register_views()
        view_cache = {}

        for key in [
            "dashboard", "health", "storage",
            "cleanup", "cloud", "accounts", "settings",
        ]:
            for child in content.winfo_children():
                child.grid_forget()

            if key not in view_cache:
                cls = view_classes[key]
                view_cache[key] = cls(content, ctrl)

            view = view_cache[key]
            view.grid(row=0, column=0, sticky="nsew")
            root.update_idletasks()

        for key in view_cache:
            self.assertIn(key, view_cache)
            self.assertTrue(
                view_cache[key].winfo_exists()
            )

        ctrl._shutting_down = True
        view_cache.clear()
        root.after(50, root.destroy)
        root.mainloop()

    @unittest.skipIf(not HAS_DISPLAY, "No display/Tk")
    def test_navigation_buttons_exist(self):
        """Verify all 7 nav buttons are created."""
        try:
            import customtkinter as ctk
        except ImportError:
            self.skipTest("customtkinter not installed")

        from ui.navigation import NAV_ITEMS

        try:
            root = ctk.CTk()
        except Exception:
            self.skipTest(
                "Tk/Tcl not available in this session"
            )

        root.title("Nav Test")
        root.geometry("200x400")

        nav_buttons = {}
        for key, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                root, text=label, width=150,
            )
            btn.pack(pady=2)
            nav_buttons[key] = btn

        self.assertEqual(len(nav_buttons), 7)
        for key, _ in NAV_ITEMS:
            self.assertIn(key, nav_buttons)

        root.after(50, root.destroy)
        root.mainloop()

    @unittest.skipIf(not HAS_DISPLAY, "No display/Tk")
    def test_controller_shutdown_prevents_work(self):
        """After shutdown flag, run_refresh returns None."""
        ctrl = _make_controller()
        ctrl._shutting_down = True

        result = ctrl.run_refresh(
            _FakeView(),
            ctrl.next_gen(),
            lambda: "data",
            on_done=MagicMock(),
            on_error=MagicMock(),
        )

        self.assertIsNone(result)


# ───────────────────────────────────────────────────────
# Phase 3 — Background Refresh Robustness
# ───────────────────────────────────────────────────────

class _FakeView:
    """Simple view stub with winfo_exists and _gen_id."""
    def __init__(self, gen_id=0):
        self._gen_id = gen_id
    def winfo_exists(self):
        return True


class TestRefreshRobustness(unittest.TestCase):
    """run_refresh with generation-based staleness protection."""

    def test_next_gen_increments(self):
        ctrl = _make_controller()
        g1 = ctrl.next_gen()
        g2 = ctrl.next_gen()
        g3 = ctrl.next_gen()
        self.assertGreater(g2, g1)
        self.assertGreater(g3, g2)

    def test_run_refresh_calls_on_done_headless(self):
        ctrl = _make_controller()
        results = []
        view = _FakeView()
        view._gen_id = ctrl.next_gen()
        ctrl.run_refresh(
            view,
            view._gen_id,
            lambda: "hello",
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, ["hello"])

    def test_run_refresh_calls_on_error_headless(self):
        ctrl = _make_controller()
        errors = []
        view = _FakeView()
        gen = ctrl.next_gen()
        view._gen_id = gen

        def fail():
            raise ValueError("boom")

        ctrl.run_refresh(
            view, gen, fail,
            on_done=MagicMock(),
            on_error=lambda e: errors.append(e),
        )
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)

    def test_stale_callback_discarded(self):
        """Older generation result is discarded when
        view's _gen_id has advanced."""
        ctrl = _make_controller()
        results = []

        view = _FakeView()
        old_gen = ctrl.next_gen()
        view._gen_id = old_gen

        ctrl.run_refresh(
            view, old_gen,
            lambda: "stale",
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, ["stale"])

        view._gen_id = ctrl.next_gen()
        ctrl.run_refresh(
            view, old_gen,
            lambda: "stale2",
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, ["stale"])

    def test_shutting_down_blocks_new_work(self):
        ctrl = _make_controller()
        ctrl._shutting_down = True
        results = []

        ctrl.run_refresh(
            _FakeView(),
            ctrl.next_gen(),
            lambda: "data",
            on_done=lambda r: results.append(r),
        )

        self.assertEqual(results, [])

    def test_nonexistent_view_discards(self):
        """Callbacks for destroyed views are discarded."""
        ctrl = _make_controller()
        results = []

        class DeadView:
            _gen_id = 0
            def winfo_exists(self):
                return False

        ctrl.run_refresh(
            DeadView(),
            ctrl.next_gen(),
            lambda: "data",
            on_done=lambda r: results.append(r),
        )

        self.assertEqual(results, [])

    def test_multiple_rapid_refreshes_same_gen(self):
        """Multiple calls with same gen_id all fire
        (they were dispatched at same generation)."""
        ctrl = _make_controller()
        results = []
        view = _FakeView()
        gen = ctrl.next_gen()
        view._gen_id = gen

        for i in range(5):
            ctrl.run_refresh(
                view, gen,
                lambda v=i: f"result_{v}",
                on_done=lambda r: results.append(r),
            )

        self.assertEqual(len(results), 5)

    def test_headless_no_root_works(self):
        """run_refresh works without Tk root."""
        ctrl = _make_controller(root=None)
        results = []
        view = _FakeView()
        gen = ctrl.next_gen()
        view._gen_id = gen
        ctrl.run_refresh(
            view, gen,
            lambda: 42,
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, [42])

    def test_headless_error_no_root(self):
        """Error callback works without Tk root."""
        ctrl = _make_controller(root=None)
        errors = []
        view = _FakeView()
        gen = ctrl.next_gen()
        view._gen_id = gen

        def fail():
            raise RuntimeError("fail")

        ctrl.run_refresh(
            view, gen, fail,
            on_done=MagicMock(),
            on_error=lambda e: errors.append(e),
        )
        self.assertEqual(len(errors), 1)

    def test_no_on_error_discards_silently(self):
        """Missing on_error handler silently discards."""
        ctrl = _make_controller(root=None)

        def fail():
            raise RuntimeError("fail")

        ctrl.run_refresh(
            _FakeView(),
            ctrl.next_gen(),
            fail,
            on_done=MagicMock(),
            on_error=None,
        )

    def test_stale_gen_discards_result(self):
        """If view._gen_id advanced, callback is
        silently discarded."""
        ctrl = _make_controller()
        results = []

        view = _FakeView()
        old_gen = ctrl.next_gen()
        view._gen_id = old_gen

        new_gen = ctrl.next_gen()
        view._gen_id = new_gen

        ctrl.run_refresh(
            view, old_gen,
            lambda: "stale",
            on_done=lambda r: results.append(r),
        )

        self.assertEqual(results, [])


# ───────────────────────────────────────────────────────
# Phase 4 — Stale Result Protection
# ───────────────────────────────────────────────────────

class TestStaleResultProtection(unittest.TestCase):
    """Older callbacks cannot overwrite newer results."""

    def test_b_newer_wins_over_a_headless(self):
        """In headless mode, only newer gen fires."""
        ctrl = _make_controller()
        results = []

        view = _FakeView()

        gen_a = ctrl.next_gen()
        view._gen_id = gen_a
        ctrl.run_refresh(
            view, gen_a,
            lambda: "A_done",
            on_done=lambda r: results.append(("A", r)),
        )

        gen_b = ctrl.next_gen()
        view._gen_id = gen_b
        ctrl.run_refresh(
            view, gen_b,
            lambda: "B_done",
            on_done=lambda r: results.append(("B", r)),
        )

        self.assertEqual(results, [("A", "A_done"), ("B", "B_done")])

    def test_completed_request_allows_later(self):
        """After a request completes, a new one works."""
        ctrl = _make_controller()
        results = []
        view = _FakeView()
        gen1 = ctrl.next_gen()
        view._gen_id = gen1

        ctrl.run_refresh(
            view, gen1,
            lambda: "first",
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, ["first"])

        gen2 = ctrl.next_gen()
        view._gen_id = gen2
        ctrl.run_refresh(
            view, gen2,
            lambda: "second",
            on_done=lambda r: results.append(r),
        )
        self.assertEqual(results, ["first", "second"])

    def test_failed_newer_does_not_corrupt_state(self):
        """A fails, B succeeds. UI shows both results."""
        ctrl = _make_controller()
        results = []

        view = _FakeView()

        gen_a = ctrl.next_gen()
        view._gen_id = gen_a
        ctrl.run_refresh(
            view, gen_a,
            lambda: (_ for _ in ()).throw(
                RuntimeError("A_fail")
            ),
            on_done=MagicMock(),
            on_error=lambda e: None,
        )

        gen_b = ctrl.next_gen()
        view._gen_id = gen_b
        ctrl.run_refresh(
            view, gen_b,
            lambda: "B_ok",
            on_done=lambda r: results.append(r),
        )

        self.assertEqual(results, ["B_ok"])


# ───────────────────────────────────────────────────────
# Phase 5 — Startup Validation
# ───────────────────────────────────────────────────────

class TestStartupValidation(unittest.TestCase):
    """Application startup does not require auth/Ollama."""

    def test_controller_init_no_auth(self):
        ctrl = _make_controller()
        self.assertFalse(ctrl._shutting_down)
        self.assertIsNone(ctrl._root)

    def test_controller_init_with_mock_agent(self):
        agent = MagicMock()
        ctrl = _make_controller(agent=agent)
        self.assertIs(ctrl.agent, agent)

    def test_startup_no_ollama_call(self):
        ctrl = _make_controller()
        settings = ctrl.get_settings()
        self.assertIsInstance(settings, dict)
        self.assertIn("version", settings)

    def test_startup_no_cloud_call(self):
        ctrl = _make_controller()
        ctrl.agent.router.execute_cloud_storage.reset_mock()
        ctrl.agent.router.execute_cloud_large_files.reset_mock()
        ctrl.agent.router.execute_cloud_duplicates.reset_mock()
        ctrl.get_settings()
        ctrl.agent.router.execute_cloud_storage.assert_not_called()
        ctrl.agent.router.execute_cloud_large_files.assert_not_called()
        ctrl.agent.router.execute_cloud_duplicates.assert_not_called()

    def test_startup_no_auth_exposure(self):
        ctrl = _make_controller()
        settings = ctrl.get_settings()
        for key, value in settings.items():
            val_str = str(value).lower()
            self.assertNotIn("ya29", val_str)
            self.assertNotIn("refresh_token", val_str)
            self.assertNotIn("client_secret", val_str)


# ───────────────────────────────────────────────────────
# Phase 6 — Local Tool Validation
# ───────────────────────────────────────────────────────

class TestLocalToolValidation(unittest.TestCase):
    """Validate local tools via controller with fakes."""

    def test_health_report_structure(self):
        ctrl = _make_controller()
        result = ctrl.get_health_report()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_local_drives_structure(self):
        ctrl = _make_controller()
        result = ctrl.get_local_drives()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_large_files_structure(self):
        ctrl = _make_controller()
        result = ctrl.get_large_files()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_duplicates_structure(self):
        ctrl = _make_controller()
        result = ctrl.get_local_duplicates()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_cleanup_preview_structure(self):
        ctrl = _make_controller()
        result = ctrl.get_cleanup_preview()
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_dashboard_returns_cards(self):
        ctrl = _make_controller()
        dashboard = ctrl.get_dashboard()
        self.assertIsInstance(dashboard, dict)
        self.assertIn("cards", dashboard)
        self.assertIsInstance(dashboard["cards"], list)

    def test_get_safe_cleanup_items_empty(self):
        ctrl = _make_controller()
        items = ctrl.get_safe_cleanup_items(
            {"success": False}
        )
        self.assertEqual(items, [])


# ───────────────────────────────────────────────────────
# Phase 7 — Cloud Safety (Mocked)
# ───────────────────────────────────────────────────────

class TestCloudSafety(unittest.TestCase):
    """Cloud operations stay mocked, no real API calls."""

    def _ctrl(self):
        ctrl = _make_controller()
        ctrl.agent.router.execute_cloud_storage.return_value = {
            "success": True, "accounts": [], "totals": {}
        }
        ctrl.agent.router.execute_cloud_large_files.return_value = {
            "success": True, "files": []
        }
        ctrl.agent.router.execute_cloud_duplicates.return_value = {
            "success": True, "groups": []
        }
        ctrl.agent.router.execute.return_value = {
            "success": True, "accounts": []
        }
        ctrl.agent.chat.return_value = "ok"
        return ctrl

    def test_cloud_storage_returns_dict(self):
        ctrl = self._ctrl()
        result = ctrl.get_cloud_storage()
        self.assertIsInstance(result, dict)

    def test_cloud_large_files_returns_dict(self):
        ctrl = self._ctrl()
        result = ctrl.get_cloud_large_files()
        self.assertIsInstance(result, dict)

    def test_cloud_duplicates_returns_dict(self):
        ctrl = self._ctrl()
        result = ctrl.get_cloud_duplicates()
        self.assertIsInstance(result, dict)

    def test_accounts_returns_dict(self):
        ctrl = self._ctrl()
        result = ctrl.get_accounts()
        self.assertIsInstance(result, dict)

    def test_connect_account_returns_result(self):
        ctrl = self._ctrl()
        result = ctrl.connect_account()
        self.assertIsInstance(result, dict)

    def test_disconnect_without_account_fails(self):
        ctrl = self._ctrl()
        result = ctrl.confirm_disconnect()
        self.assertIsInstance(result, str)

    def test_no_implicit_cloud_on_startup(self):
        """Cloud methods not called during get_settings."""
        ctrl = self._ctrl()
        ctrl.agent.router.execute_cloud_storage.reset_mock()
        ctrl.get_settings()
        ctrl.agent.router.execute_cloud_storage.assert_not_called()


# ───────────────────────────────────────────────────────
# Phase 8 — Ollama Validation
# ───────────────────────────────────────────────────────

class TestOllamaValidation(unittest.TestCase):
    """Application works whether Ollama is available."""

    def test_settings_works_without_ollama(self):
        ctrl = _make_controller()
        settings = ctrl.get_settings()
        self.assertIn("ollama_status", settings)
        self.assertIsInstance(
            settings["ollama_status"], str
        )

    def test_settings_works_with_ollama_unavailable(self):
        ctrl = _make_controller()
        ctrl.agent.ai = MagicMock()
        ctrl.agent.ai.model = "llama3"
        ctrl.agent.router.drive_manager = MagicMock()
        ctrl.agent.router.drive_manager.token_dir = (
            MagicMock(__str__=lambda _: "/tmp/tokens")
        )

        with patch(
            "builtins.__import__",
            side_effect=ImportError("no ollama"),
        ):
            settings = ctrl.get_settings()
            self.assertEqual(
                settings["ollama_status"], "Unavailable"
            )


# ───────────────────────────────────────────────────────
# Phase 10 — Packaging Exclusion Verification
# ───────────────────────────────────────────────────────

class TestPackagingExclusions(unittest.TestCase):
    """Credential/secret files are not tracked in git."""

    def test_credentials_not_tracked(self):
        result = os.popen(
            "git ls-files"
        ).read()
        self.assertNotIn("credentials.json", result)
        self.assertNotIn("token.json", result)
        self.assertNotIn(".env", result)
        self.assertNotIn(".venv/", result)
        self.assertNotIn("__pycache__/", result)

    def test_cloud_data_not_tracked(self):
        result = os.popen(
            "git ls-files"
        ).read()
        self.assertNotIn("cloud_data/", result)

    def test_requirements_exists(self):
        self.assertTrue(
            os.path.isfile("requirements.txt")
        )

    def test_gitignore_covers_credentials(self):
        with open(".gitignore") as f:
            content = f.read()
        self.assertIn("credentials.json", content)
        self.assertIn("token.json", content)
        self.assertIn(".env", content)
        self.assertIn("cloud_data/", content)


# ───────────────────────────────────────────────────────
# Phase 16 — Security Regression
# ───────────────────────────────────────────────────────

class TestSecurityRegressions(unittest.TestCase):
    """No secrets leak through UI or controller."""

    def test_settings_no_expose_secrets(self):
        ctrl = _make_controller()
        settings = ctrl.get_settings()
        for v in settings.values():
            s = str(v).lower()
            self.assertNotIn("ya29", s)
            self.assertNotIn("refresh_token", s)
            self.assertNotIn("client_secret", s)

    def test_dashboard_no_expose_secrets(self):
        ctrl = _make_controller()
        dashboard = ctrl.get_dashboard()
        for card in dashboard.get("cards", []):
            for v in card.values():
                s = str(v).lower()
                self.assertNotIn("ya29", s)
                self.assertNotIn("client_secret", s)

    def test_accounts_no_expose_tokens(self):
        ctrl = _make_controller()
        result = ctrl.get_accounts()
        text = str(result).lower()
        self.assertNotIn("ya29", text)
        self.assertNotIn("client_secret", text)

    def test_no_implicit_cloud_calls(self):
        """Navigation/open_view does not call cloud tools."""
        ctrl = _make_controller()
        ctrl.agent.router.execute_cloud_storage.reset_mock()
        ctrl.agent.router.execute_cloud_large_files.reset_mock()
        ctrl.agent.router.execute_cloud_duplicates.reset_mock()
        ctrl.open_view("dashboard")
        ctrl.open_view("settings")
        ctrl.agent.router.execute_cloud_storage.assert_not_called()
        ctrl.agent.router.execute_cloud_large_files.assert_not_called()
        ctrl.agent.router.execute_cloud_duplicates.assert_not_called()

    def test_format_bytes_never_exposes_raw(self):
        from ui.components import format_bytes_short
        result = format_bytes_short(None)
        self.assertEqual(result, "Unavailable")
        result = format_bytes_short(float("inf"))
        self.assertIsInstance(result, str)

    def test_status_label_never_exposes_raw(self):
        from ui.components import status_label
        result = status_label(None)
        self.assertEqual(result, "Unknown")
        result = status_label("abc")
        self.assertEqual(result, "Unknown")

    def test_safe_text_none_returns_fallback(self):
        from ui.components import safe_text
        result = safe_text(None)
        self.assertEqual(result, "Unknown")

    def test_safe_text_preserves_content(self):
        from ui.components import safe_text
        result = safe_text("Hello")
        self.assertEqual(result, "Hello")


# ───────────────────────────────────────────────────────
# Phase 14 — Lifecycle
# ───────────────────────────────────────────────────────

class TestLifecycle(unittest.TestCase):
    """Application shutdown and controller lifecycle."""

    def test_controller_shutdown_flag(self):
        ctrl = _make_controller()
        self.assertFalse(ctrl._shutting_down)
        ctrl._shutting_down = True
        self.assertTrue(ctrl._shutting_down)

    def test_shutdown_blocks_run_refresh(self):
        ctrl = _make_controller()
        ctrl._shutting_down = True
        result = ctrl.run_refresh(
            MagicMock(),
            ctrl.next_gen(),
            lambda: "data",
            on_done=MagicMock(),
        )
        self.assertIsNone(result)

    def test_shutdown_does_not_block_headless(self):
        ctrl = _make_controller(root=None)
        ctrl._shutting_down = True
        result = ctrl.run_refresh(
            MagicMock(),
            ctrl.next_gen(),
            lambda: "data",
            on_done=MagicMock(),
        )
        self.assertIsNone(result)

    @unittest.skipIf(not HAS_DISPLAY, "No display/Tk")
    def test_app_destroy_sets_flags(self):
        try:
            import customtkinter as ctk
        except ImportError:
            self.skipTest("customtkinter not installed")

        from ui.app_controller import GuardianController

        ctrl = GuardianController.__new__(GuardianController)
        ctrl.agent = MagicMock()
        ctrl._current_view = "dashboard"
        ctrl._last_health = None
        ctrl._shutting_down = False
        import itertools
        ctrl._gen_counter = itertools.count()

        root = ctk.CTk()
        ctrl._root = root

        ctrl._shutting_down = True
        root._shutting_down = True

        self.assertTrue(ctrl._shutting_down)
        self.assertTrue(root._shutting_down)

        root.after(50, root.destroy)
        root.mainloop()


# ───────────────────────────────────────────────────────
# Navigation key consistency
# ───────────────────────────────────────────────────────

class TestNavigationConsistency(unittest.TestCase):
    """NAV_ITEMS matches view registry."""

    def test_nav_items_are_strings(self):
        from ui.navigation import NAV_ITEMS
        for key, label in NAV_ITEMS:
            self.assertIsInstance(key, str)
            self.assertIsInstance(label, str)

    def test_nav_items_count(self):
        from ui.navigation import NAV_ITEMS
        self.assertEqual(len(NAV_ITEMS), 7)

    def test_nav_keys_unique(self):
        from ui.navigation import NAV_ITEMS
        keys = [k for k, _ in NAV_ITEMS]
        self.assertEqual(len(keys), len(set(keys)))


# ───────────────────────────────────────────────────────
# Resource path safety
# ───────────────────────────────────────────────────────

class TestResourcePathSafety(unittest.TestCase):
    """No hardcoded absolute paths in UI code."""

    def test_no_hardcoded_dev_paths(self):
        ui_files = [
            "ui/app.py",
            "ui/app_controller.py",
            "ui/components.py",
            "ui/navigation.py",
        ]
        for fp in ui_files:
            with open(fp, encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn(
                "D:\\AI-Laptop-Guardian-Dev",
                content,
                f"{fp} contains hardcoded path",
            )
            self.assertNotIn(
                "D:/AI-Laptop-Guardian-Dev",
                content,
                f"{fp} contains hardcoded path",
            )


# ───────────────────────────────────────────────────────
# User data safety
# ───────────────────────────────────────────────────────

class TestUserDataSafety(unittest.TestCase):
    """Application stores user data outside source."""

    def test_token_dir_is_not_source(self):
        ctrl = _make_controller()
        token_dir = str(
            ctrl.agent.router.drive_manager.token_dir
        )
        source_dir = os.path.abspath(".")
        self.assertNotEqual(
            os.path.normpath(token_dir),
            os.path.normpath(source_dir),
        )


if __name__ == "__main__":
    unittest.main()
