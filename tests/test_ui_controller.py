"""Milestone 10 - GuardianController tests.

Fully headless: no display server needed.

All tests call controller methods directly; the thin
widget layer is tested separately under a display guard.
"""

import sys
import types
from pathlib import Path


def _install_cloud_stub():
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
from cloud.accounts import AccountRegistry  # noqa: E402
from cloud.multi_drive import (  # noqa: E402
    MultiAccountDriveManager,
)
from ui.app_controller import GuardianController  # noqa: E402
from ui.components import (  # noqa: E402
    safe_text,
    format_bytes_short,
    status_label,
)
from ui.navigation import NAV_ITEMS  # noqa: E402


# =========================================================
# HELPERS
# =========================================================


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


def make_controller(tmp_path):
    agent = AIAgent()
    agent.ai = FakeAI()

    agent.router.drive_manager = (
        MultiAccountDriveManager(
            registry=AccountRegistry(),
            token_dir=str(tmp_path / "tokens"),
            provider_factory=FakeProvider,
        )
    )

    return GuardianController(agent=agent)


# =========================================================
# NAVIGATION
# =========================================================


class TestNavigation:

    def test_all_views_are_valid(self):
        import tempfile

        ctrl = make_controller(
            Path(tempfile.mkdtemp())
        )

        for key, _label in NAV_ITEMS:

            assert ctrl.open_view(key) == key

    def test_invalid_view_raises(self):
        import tempfile

        ctrl = make_controller(
            Path(tempfile.mkdtemp())
        )

        with pytest.raises(ValueError):
            ctrl.open_view("nonexistent")

    def test_current_view_updates(self):
        import tempfile

        ctrl = make_controller(
            Path(tempfile.mkdtemp())
        )

        assert ctrl.current_view == "dashboard"

        ctrl.open_view("health")

        assert ctrl.current_view == "health"


# =========================================================
# DASHBOARD
# =========================================================


class TestDashboard:

    def test_dashboard_returns_cards(self, tmp_path):
        ctrl = make_controller(tmp_path)

        data = ctrl.get_dashboard()

        assert "cards" in data
        assert "status" in data
        assert isinstance(data["cards"], list)
        assert len(data["cards"]) >= 5

    def test_dashboard_card_shape(self, tmp_path):
        ctrl = make_controller(tmp_path)

        data = ctrl.get_dashboard()

        for card in data["cards"]:
            assert "label" in card
            assert "value" in card
            assert "ok" in card

    def test_dashboard_uses_backend_directly(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        data = ctrl.get_dashboard()

        health_cards = [
            c for c in data["cards"]
            if c["label"] == "Health"
        ]

        assert len(health_cards) == 1

        assert "Unavailable" not in (
            health_cards[0]["value"]
        )

    def test_dashboard_status_deterministic(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        data = ctrl.get_dashboard()

        assert data["status"] in {
            "Protected",
            "Healthy",
            "Attention Needed",
        }


# =========================================================
# HEALTH
# =========================================================


class TestHealth:

    def test_health_report_structure(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_health_report()

        assert result.get("success") is True

        assert "data" in result

    def test_recommendations_are_empty_or_list(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_health_report()

        recs = ctrl.get_health_recommendations(result)

        assert isinstance(recs, list)


# =========================================================
# STORAGE
# =========================================================


class TestStorage:

    def test_drives_return_success(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_local_drives()

        assert result.get("success") is True

    def test_large_files_return(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_large_files()

        assert "success" in result

    def test_duplicates_return(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_local_duplicates()

        assert "success" in result


# =========================================================
# CLEANUP SAFETY
# =========================================================


class TestCleanupSafety:

    def test_preview_returns_success(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_cleanup_preview()

        assert result.get("success") is True

    def test_safe_items_are_only_safe(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_cleanup_preview()

        items = ctrl.get_safe_cleanup_items(result)

        for item in items:
            assert item.get("classification") == "safe"

    def test_propose_cleanup_holds_safety(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        items = [
            {
                "path": "/tmp/test.tmp",
                "name": "test.tmp",
                "size_bytes": 1024,
                "classification": "safe",
            }
        ]

        desc = ctrl.propose_cleanup(items)

        assert ctrl.agent.safety.has_pending()

        assert "1 file(s)" in desc

    def test_confirm_cleanup_executes(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        items = [
            {
                "path": "/tmp/test.tmp",
                "name": "test.tmp",
                "size_bytes": 1024,
                "classification": "safe",
            }
        ]

        ctrl.propose_cleanup(items)

        msg = ctrl.confirm_cleanup_deletion()

        assert isinstance(msg, str)

        assert not ctrl.agent.safety.has_pending()

    def test_cancel_cleanup_clears_safety(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        items = [
            {
                "path": "/tmp/a.tmp",
                "name": "a.tmp",
                "size_bytes": 512,
                "classification": "safe",
            }
        ]

        ctrl.propose_cleanup(items)

        assert ctrl.agent.safety.has_pending()

        ctrl.cancel_cleanup()

        assert not ctrl.agent.safety.has_pending()


# =========================================================
# ACCOUNTS
# =========================================================


class TestAccounts:

    def test_accounts_offline(self, tmp_path):
        ctrl = make_controller(tmp_path)

        result = ctrl.get_accounts()

        assert result.get("success") is True

        assert result.get("tool") == "cloud_accounts"

    def test_disconnect_requires_proposal(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        msg = ctrl.request_disconnect("ghost@x.com")

        assert isinstance(msg, str)


# =========================================================
# CHAT
# =========================================================


class TestChat:

    def test_ask_passes_to_agent(self, tmp_path):
        ctrl = make_controller(tmp_path)

        ctrl.ask("hello")

        assert ctrl.agent.ai.prompts == ["hello"]


# =========================================================
# SETTINGS
# =========================================================


class TestSettings:

    def test_settings_shape(self, tmp_path):
        ctrl = make_controller(tmp_path)

        s = ctrl.get_settings()

        assert "model" in s

        assert "version" in s

        assert "ollama_status" in s


# =========================================================
# BACKGROUND THREADS
# =========================================================


class TestBackground:

    def test_run_in_background_calls_on_done(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        result_box = []

        def work():
            return 42

        ctrl.run_in_background(
            work,
            on_done=lambda r: result_box.append(r),
        )

        import time

        time.sleep(0.3)

        assert result_box == [42]

    def test_run_in_background_calls_on_error(
        self, tmp_path
    ):
        ctrl = make_controller(tmp_path)

        err_box = []

        def work():
            raise RuntimeError("boom")

        ctrl.run_in_background(
            work,
            on_done=lambda r: None,
            on_error=lambda e: err_box.append(str(e)),
        )

        import time

        time.sleep(0.3)

        assert err_box == ["boom"]


# =========================================================
# COMPONENT UTILITIES
# =========================================================


class TestComponents:

    def test_safe_text_none(self):
        assert safe_text(None) == "Unknown"

    def test_format_bytes_none(self):
        assert format_bytes_short(None) == "Unavailable"

    def test_status_label_none(self):
        assert status_label(None) == "Unknown"

    def test_status_label_high(self):
        assert status_label(90) == "Protected"

    def test_status_label_mid(self):
        assert status_label(65) == "Healthy"

    def test_status_label_low(self):
        assert status_label(30) == "Attention Needed"
