"""Milestone 7 - Upload destination resolution.

Uploads always go to an explicitly resolved account.
Ambiguous or unknown destinations never silently pick
another account. Legacy behavior is preserved when no
accounts are registered.
"""

import sys
import types


def _install_cloud_stub() -> None:
    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        def __init__(self, *args, **kwargs):
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


class FakeProvider:

    def __init__(self, account_id):
        self.account_id = account_id
        self.upload_calls = []

    def authenticate(self):
        return {"success": True}

    def upload_file(self, path):
        self.upload_calls.append(path)
        return {
            "success": True,
            "message": f"Uploaded {path}",
        }


class FakeAI:

    def ask(self, prompt):
        return "FAKE AI RESPONSE"


def make_agent(email_count=2):
    agent = AIAgent()
    agent.ai = FakeAI()

    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeProvider(
                account.id
            )

        return providers[account.id]

    agent.router.drive_manager = (
        MultiAccountDriveManager(
            registry=registry,
            provider_factory=factory,
        )
    )

    for index in range(email_count):

        agent.router.drive_manager.connect_account(
            "google_drive",
            email=f"user{index + 1}@x.com",
        )

    return agent, providers


# =========================================================
# ROUTER RESOLUTION HELPERS
# =========================================================


class TestResolutionHelpers:

    def test_resolve_by_number_returns_safe_metadata(self):
        agent, _ = make_agent()

        record = agent.router.resolve_account("1")

        assert record["id"] == "account-1"
        assert record["email"] == "user1@x.com"
        assert record["status"] == "connected"

    def test_resolve_unknown_returns_none(self):
        agent, _ = make_agent()

        assert (
            agent.router.resolve_account("9") is None
        )

    def test_describe_accounts_is_metadata_only(self):
        agent, _ = make_agent(1)

        described = (
            agent.router.describe_connected_accounts()
        )

        assert described[0]["label"] == "user1@x.com"

        serialized = str(described).lower()

        for forbidden in (
            "token",
            "secret",
            "password",
            "credential",
        ):

            assert forbidden not in serialized


# =========================================================
# BOUND UPLOAD THROUGH CHAT
# =========================================================


class TestBoundUploadThroughChat:

    def test_upload_goes_only_to_named_account(
        self,
        tmp_path,
    ):
        agent, providers = make_agent()

        target = tmp_path / "notes.txt"
        target.write_text(
            "local content",
            encoding="utf-8",
        )

        response = agent.chat(
            f"Upload {target} to account 1"
        )

        assert providers[
            "account-1"
        ].upload_calls == [str(target)]

        # Proof of isolation.

        assert providers.get("account-2") is None

    def test_upload_to_unknown_account_uploads_nowhere(
        self,
        tmp_path,
    ):
        agent, providers = make_agent()

        target = tmp_path / "ghost.txt"
        target.write_text("x", encoding="utf-8")

        response = agent.chat(
            f"Upload {target} to account 9"
        )

        assert "couldn't find" in response.lower()

        for provider in providers.values():
            assert provider.upload_calls == []

    def test_manager_upload_rejects_empty_path(self):
        agent, providers = make_agent(1)

        result = (
            agent.router.drive_manager
            .upload_to_account("account-1", "   ")
        )

        assert result["success"] is False

        # No session was ever constructed.

        assert agent.router.drive_manager._sessions == {}


# =========================================================
# LEGACY UPLOAD PRESERVED
# =========================================================


class TestLegacyUploadPreserved:

    def test_zero_registered_accounts_use_default_provider(
        self,
        tmp_path,
    ):
        class LegacyProvider:

            def __init__(self):
                self.upload_calls = []

            def upload_file(self, path):
                self.upload_calls.append(path)
                return {
                    "success": True,
                    "message": "Uploaded",
                }

        from agent.ai_agent import AIAgent

        agent = AIAgent()
        agent.ai = FakeAI()

        legacy = LegacyProvider()
        agent.router.google_drive = legacy

        target = tmp_path / "legacy.txt"
        target.write_text("x", encoding="utf-8")

        response = agent.chat(
            f"Upload {target} to Google Drive"
        )

        assert legacy.upload_calls == [str(target)]
