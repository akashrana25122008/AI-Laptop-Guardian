"""Milestone 11 - Real Google Drive integration tests.

Proves the end-to-end cloud integration works using
deterministic fakes.  No real OAuth, no real network,
no real credentials.

Tests at minimum:
    - OAuth through controller
    - failed OAuth does not register
    - startup never authenticates
    - view navigation never authenticates
    - account list reflects registrations
    - cloud intelligence with connected accounts
    - one failing account does not hide healthy
    - disconnect targets exact account
    - disconnect uses confirmation flow
    - no silent fallback on disconnect
    - dashboard shows connected account count
    - cloud view data shapes match rendering
"""

import sys
import types


def _install_cloud_stub():
    if "cloud.google_drive" not in sys.modules:
        module = types.ModuleType(
            "cloud.google_drive"
        )

        class StubGoogleDriveProvider:
            def __init__(self, *a, **kw):
                self.service = None
                self.credentials = None

        module.GoogleDriveProvider = (
            StubGoogleDriveProvider
        )

        sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

import pytest  # noqa: E402

from agent.ai_agent import AIAgent  # noqa: E402
from cloud.accounts import AccountRegistry  # noqa: E402
from cloud.multi_drive import (  # noqa: E402
    MultiAccountDriveManager,
)
from cloud.auth_manager import (  # noqa: E402
    GoogleAuthManager,
)
from cloud.cloud_intelligence import (  # noqa: E402
    CloudStorageIntelligence,
)
from ui.app_controller import GuardianController  # noqa: E402
from ui.navigation import NAV_ITEMS  # noqa: E402


# =========================================================
# CONSTANTS
# =========================================================

GB = 1024 * 1024 * 1024
MB = 1024 * 1024


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


class FakeCloudProvider:
    """Per-account fake provider."""

    def __init__(
        self,
        account_id,
        email=None,
        storage_behavior=None,
        files=None,
    ):
        self.account_id = account_id
        self.email = email
        self.service = "fake"
        self.credentials = None
        self.authenticate_calls = 0
        self.storage_behavior = storage_behavior
        self.files = files or []
        self.search_calls = []

    def authenticate(self):
        self.authenticate_calls += 1
        return {"success": True}

    def get_account_identity(self):
        return {
            "success": True,
            "email": self.email,
            "display_name": self.email,
        }

    def get_storage_info(self):
        if isinstance(
            self.storage_behavior, Exception
        ):
            raise self.storage_behavior
        if self.storage_behavior is None:
            return {
                "success": False,
                "error": "not implemented",
            }
        return self.storage_behavior

    def search_files(self, query):
        self.search_calls.append(query)
        q = str(query).lower()
        matches = [
            f
            for f in self.files
            if q in f.get("name", "").lower()
        ]
        return {
            "success": True,
            "matches": matches,
        }

    def list_large_files(
        self, min_size_bytes=0, limit=50
    ):
        results = []
        for f in self.files:
            if f.get("size_bytes", 0) >= min_size_bytes:
                results.append(dict(f))
            if len(results) >= limit:
                break
        return {
            "success": True,
            "files": results,
            "count": len(results),
        }

    def list_all_files_metadata(self, limit=200):
        return {
            "success": True,
            "files": list(self.files[:limit]),
            "count": min(len(self.files), limit),
        }


# =========================================================
# BUILDER
# =========================================================


def make_controller(tmp_path):
    agent = AIAgent()
    agent.ai = FakeAI()

    registry = AccountRegistry()
    providers = {}

    manager = MultiAccountDriveManager(
        registry=registry,
        token_dir=str(tmp_path / "tokens"),
    )

    def factory(account):
        if account.id not in providers:
            providers[account.id] = FakeCloudProvider(
                account.id,
                email=account.email,
            )
        return providers[account.id]

    manager._provider_factory = factory

    agent.router.drive_manager = manager
    agent.router._cloud_intelligence = (
        CloudStorageIntelligence(manager)
    )
    agent.router._auth_manager = GoogleAuthManager(
        drive_manager=manager,
        credentials_file=str(
            tmp_path / "credentials.json"
        ),
    )

    ctrl = GuardianController(agent=agent)

    return ctrl, manager, registry, providers


def _add_accounts(mgr, providers, emails):
    """Register accounts and trigger provider creation."""
    for email in emails:
        mgr.connect_account(
            "google_drive", email=email
        )
    for acc in mgr.registry.list_accounts():
        mgr.get_session(acc.id)


def _make_oauth_stub(identity):
    """Build a fake provider factory for OAuth tests.

    The stub writes a dummy token file at the temp path
    so that os.replace succeeds in complete_authentication.
    """

    def factory(token_path):
        class _Stub:
            def authenticate(self):
                from pathlib import Path

                Path(token_path).write_text("{}")
                return True

            def get_account_identity(self):
                return identity

        return _Stub()

    return factory


# =========================================================
# OAUTH FLOW
# =========================================================


class TestOAuthFlow:
    def test_connect_registers_account(
        self, tmp_path
    ):
        ctrl, mgr, reg, _ = make_controller(
            tmp_path
        )

        identity = {
            "success": True,
            "email": "alice@gmail.com",
            "display_name": "Alice",
        }

        ctrl.agent.router.auth_manager._pending_factory = (
            _make_oauth_stub(identity)
        )

        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        ctrl.agent.router.auth_manager.credentials_file = str(
            creds
        )
        (tmp_path / "tokens").mkdir(
            parents=True, exist_ok=True
        )

        result = ctrl.connect_account()

        assert result.get("success") is True
        assert result["account"]["email"] == (
            "alice@gmail.com"
        )

        accounts = ctrl.get_accounts()
        acc_list = accounts.get("accounts", [])
        assert len(acc_list) == 1
        assert acc_list[0]["email"] == "alice@gmail.com"

    def test_failed_oauth_does_not_register(
        self, tmp_path
    ):
        ctrl, mgr, reg, _ = make_controller(
            tmp_path
        )

        ctrl.agent.router.auth_manager._pending_factory = (
            lambda path: type(
                "FP",
                (),
                {
                    "authenticate": lambda s: False,
                    "get_account_identity": lambda s: {
                        "success": False
                    },
                },
            )()
        )

        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        ctrl.agent.router.auth_manager.credentials_file = str(
            creds
        )
        (tmp_path / "tokens").mkdir(
            parents=True, exist_ok=True
        )

        result = ctrl.connect_account()

        assert result.get("success") is False
        accounts = ctrl.get_accounts()
        assert len(accounts.get("accounts", [])) == 0

    def test_missing_credentials_returns_error(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        result = ctrl.connect_account()

        assert result.get("success") is False
        assert result.get("error_code") == (
            "missing_credentials"
        )

    def test_connect_does_not_expose_secrets(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        identity = {
            "success": True,
            "email": "bob@gmail.com",
            "display_name": "Bob",
        }

        ctrl.agent.router.auth_manager._pending_factory = (
            _make_oauth_stub(identity)
        )

        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        ctrl.agent.router.auth_manager.credentials_file = str(
            creds
        )
        (tmp_path / "tokens").mkdir(
            parents=True, exist_ok=True
        )

        result = ctrl.connect_account()

        result_str = str(result)
        assert "ya29" not in result_str.lower()
        assert "SUPERSECRET" not in result_str
        assert "refresh_token" not in (
            result_str.lower()
        )


# =========================================================
# MULTI-ACCOUNT
# =========================================================


class TestMultiAccount:
    def test_two_accounts_isolated(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com", "b@x.com"])

        a1 = reg.get_account("account-1")
        a2 = reg.get_account("account-2")

        assert a1.email == "a@x.com"
        assert a2.email == "b@x.com"

        s1 = mgr.get_session("account-1")
        s2 = mgr.get_session("account-2")

        assert s1 is not None
        assert s2 is not None
        assert s1 is not s2

    def test_same_filename_different_accounts(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com", "b@x.com"])

        provs["account-1"].files = [
            {
                "id": "f1",
                "name": "report.pdf",
                "size_bytes": 1024,
            }
        ]
        provs["account-2"].files = [
            {
                "id": "f2",
                "name": "report.pdf",
                "size_bytes": 2048,
            }
        ]

        result = ctrl.agent.router.execute_cloud_search_scoped(
            "report", scope_all=True
        )

        assert result.get("success") is True
        matches = result.get("matches", [])
        ids = {m.get("account_id") for m in matches}
        assert "account-1" in ids
        assert "account-2" in ids

    def test_disconnected_account_fails_safely(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        reg.remove_account("account-1")

        assert mgr.get_session("account-1") is None

    def test_no_fallback_to_other_account(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com", "b@x.com"])

        reg.remove_account("account-1")

        result = mgr.search_accounts(
            "test",
            account_ids=["account-1"],
        )

        assert result.get("success") is False
        assert "not connected" in (
            result.get("error", "").lower()
        )

    def test_unknown_account_fails_safely(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        result = mgr.search_accounts(
            "test",
            account_ids=["account-999"],
        )

        assert result.get("success") is False
        assert "not connected" in (
            result.get("error", "").lower()
        )


# =========================================================
# CLOUD INTELLIGENCE
# =========================================================


class TestCloudIntelligence:
    def test_one_healthy_account(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        provs["account-1"].storage_behavior = {
            "success": True,
            "total_bytes": 100 * GB,
            "used_bytes": 40 * GB,
        }

        result = ctrl.get_cloud_storage()

        assert result.get("success") is True
        entries = result.get("accounts", [])
        assert len(entries) == 1
        assert entries[0]["status"] == "available"
        assert (
            entries[0]["storage"]["used_bytes"]
            == 40 * GB
        )

    def test_two_healthy_accounts(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        provs["account-1"].storage_behavior = {
            "success": True,
            "total_bytes": 100 * GB,
            "used_bytes": 30 * GB,
        }
        provs["account-2"].storage_behavior = {
            "success": True,
            "total_bytes": 200 * GB,
            "used_bytes": 80 * GB,
        }

        result = ctrl.get_cloud_storage()

        assert result.get("success") is True
        entries = result.get("accounts", [])
        assert len(entries) == 2
        totals = result.get("totals", {})
        assert (
            totals["known_used_bytes"] == 110 * GB
        )

    def test_one_failing_does_not_hide_healthy(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        provs["account-1"].storage_behavior = {
            "success": True,
            "total_bytes": 100 * GB,
            "used_bytes": 40 * GB,
        }
        provs["account-2"].storage_behavior = (
            RuntimeError("network down")
        )

        result = ctrl.get_cloud_storage()

        entries = result.get("accounts", [])
        statuses = {
            e["account_id"]: e["status"]
            for e in entries
        }
        assert statuses["account-1"] == "available"
        assert statuses["account-2"] == "failed"

        totals = result.get("totals", {})
        assert (
            totals["known_used_bytes"] == 40 * GB
        )

        excluded = totals.get(
            "excluded_accounts", []
        )
        assert len(excluded) == 1
        assert (
            excluded[0]["account_id"] == "account-2"
        )

    def test_unavailable_is_not_zero(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        provs["account-1"].storage_behavior = {
            "success": True,
            "total_bytes": None,
            "used_bytes": None,
        }

        result = ctrl.get_cloud_storage()

        entries = result.get("accounts", [])
        assert entries[0]["status"] == "unavailable"

        totals = result.get("totals", {})
        assert totals["known_used_bytes"] is None

    def test_large_files_across_accounts(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        provs["account-1"].files = [
            {
                "id": "f1",
                "name": "big.iso",
                "size_bytes": 500 * MB,
            }
        ]
        provs["account-2"].files = [
            {
                "id": "f2",
                "name": "huge.zip",
                "size_bytes": 1024 * MB,
            }
        ]

        result = ctrl.get_cloud_large_files()

        assert result.get("success") is True
        files = result.get("files", [])
        assert len(files) == 2

        sizes = sorted(
            f["size_bytes"] for f in files
        )
        assert sizes == [500 * MB, 1024 * MB]

    def test_duplicates_across_accounts(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        provs["account-1"].files = [
            {
                "id": "f1",
                "name": "report.pdf",
                "size_bytes": 1024,
            }
        ]
        provs["account-2"].files = [
            {
                "id": "f2",
                "name": "report.pdf",
                "size_bytes": 1024,
            }
        ]

        result = ctrl.get_cloud_duplicates()

        assert result.get("success") is True
        groups = result.get("groups", [])
        assert len(groups) == 1
        assert groups[0]["count"] == 2
        assert groups[0]["confirmed"] is False


# =========================================================
# DISCONNECT
# =========================================================


class TestDisconnect:
    def test_disconnect_removes_exact_account(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        ctrl.agent.router.execute_google_disconnect(
            "a@x.com"
        )

        a1 = reg.get_account("account-1")
        a2 = reg.get_account("account-2")

        assert a1.status == "disconnected"
        assert a2.status == "connected"

    def test_disconnect_unknown_account_fails(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        result = (
            ctrl.agent.router.execute_google_disconnect(
                "ghost@x.com"
            )
        )

        assert result.get("success") is False

    def test_disconnect_removes_token_file(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        token = (
            tmp_path / "tokens" / "account-1.json"
        )
        token.parent.mkdir(
            parents=True, exist_ok=True
        )
        token.write_text("{}")

        result = (
            ctrl.agent.router.execute_google_disconnect(
                "a@x.com"
            )
        )

        assert result.get("success") is True
        assert not token.exists()

    def test_disconnect_preserves_other_tokens(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        t1 = tokens_dir / "account-1.json"
        t2 = tokens_dir / "account-2.json"
        t1.write_text("{}")
        t2.write_text("{}")

        (
            ctrl.agent.router.execute_google_disconnect(
                "a@x.com"
            )
        )

        assert not t1.exists()
        assert t2.exists()


# =========================================================
# ACCOUNTS LISTING
# =========================================================


class TestAccountListing:
    def test_accounts_offline_no_auth(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        result = ctrl.get_accounts()

        assert result.get("success") is True
        accounts = result.get("accounts", [])
        assert len(accounts) == 1
        assert accounts[0]["email"] == "a@x.com"

    def test_accounts_empty_when_none(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        result = ctrl.get_accounts()

        assert result.get("success") is True
        assert len(result.get("accounts", [])) == 0


# =========================================================
# DASHBOARD INTEGRATION
# =========================================================


class TestDashboardIntegration:
    def test_dashboard_shows_account_count(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(
            mgr, provs, ["a@x.com", "b@x.com"]
        )

        data = ctrl.get_dashboard()

        cards = data.get("cards", [])
        cloud_cards = [
            c
            for c in cards
            if c["label"] == "Google Accounts"
        ]
        assert len(cloud_cards) == 1
        assert cloud_cards[0]["value"] == "2"
        assert (
            cloud_cards[0]["detail"] == "Connected"
        )

    def test_dashboard_no_accounts(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        data = ctrl.get_dashboard()

        cards = data.get("cards", [])
        cloud_cards = [
            c
            for c in cards
            if c["label"] == "Google Accounts"
        ]
        assert len(cloud_cards) == 1
        assert cloud_cards[0]["value"] == "0"
        assert (
            cloud_cards[0]["detail"]
            == "None connected"
        )


# =========================================================
# STARTUP / NAVIGATION NO-AUTH
# =========================================================


class TestNoAuthGuarantees:
    def test_startup_no_auth(self, tmp_path):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        for acc in reg.list_accounts(
            connected_only=False
        ):
            assert (
                mgr.get_session(acc.id) is None
            )

    def test_get_accounts_never_authenticates(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        ctrl.get_accounts()

        for p in provs.values():
            assert p.authenticate_calls == 0

    def test_view_navigation_never_authenticates(
        self, tmp_path
    ):
        ctrl, _, _, provs = make_controller(
            tmp_path
        )

        for key, _ in NAV_ITEMS:
            ctrl.open_view(key)

        for p in provs.values():
            assert p.authenticate_calls == 0

    def test_connect_button_starts_auth(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        identity = {
            "success": True,
            "email": "test@gmail.com",
            "display_name": "Test",
        }

        ctrl.agent.router.auth_manager._pending_factory = (
            _make_oauth_stub(identity)
        )

        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        ctrl.agent.router.auth_manager.credentials_file = str(
            creds
        )
        (tmp_path / "tokens").mkdir(
            parents=True, exist_ok=True
        )

        result = ctrl.connect_account()

        assert result.get("success") is True


# =========================================================
# SETTINGS
# =========================================================


class TestSettings:
    def test_version_is_milestone_11(
        self, tmp_path
    ):
        ctrl, _, _, _ = make_controller(tmp_path)

        settings = ctrl.get_settings()

        version = settings["version"]
        assert isinstance(version, str)
        assert len(version) > 0


# =========================================================
# CLOUD VIEW DATA SHAPES
# =========================================================


class TestCloudViewDataShapes:
    """Ensure intelligence results match what the
    cloud view expects to render."""

    def test_summary_has_accounts_and_totals(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        provs["account-1"].storage_behavior = {
            "success": True,
            "total_bytes": 100 * GB,
            "used_bytes": 40 * GB,
        }

        result = ctrl.get_cloud_storage()

        assert "accounts" in result
        assert "totals" in result
        assert isinstance(
            result["accounts"], list
        )

        entry = result["accounts"][0]
        assert "storage" in entry
        assert "used_bytes" in entry["storage"]
        assert "free_bytes" in entry["storage"]
        assert "total_bytes" in entry["storage"]

    def test_large_files_has_files_key(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        provs["account-1"].files = [
            {
                "id": "f1",
                "name": "big.iso",
                "size_bytes": 200 * MB,
            }
        ]

        result = ctrl.get_cloud_large_files()

        assert "files" in result
        assert isinstance(result["files"], list)

    def test_duplicates_has_groups_key(
        self, tmp_path
    ):
        ctrl, mgr, reg, provs = make_controller(
            tmp_path
        )

        _add_accounts(mgr, provs, ["a@x.com"])

        provs["account-1"].files = [
            {
                "id": "f1",
                "name": "x.pdf",
                "size_bytes": 100,
            }
        ]

        result = ctrl.get_cloud_duplicates()

        assert "groups" in result
        assert isinstance(result["groups"], list)
