"""Milestone 7 - Cross-account deletion safety.

The core Milestone 7 guarantee: a confirmed deletion can
only ever hit the exact account it was proposed on.
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
from agent.action_safety import ActionSafety  # noqa: E402
from cloud.accounts import AccountRegistry  # noqa: E402
from cloud.multi_drive import (  # noqa: E402
    MultiAccountDriveManager,
)


class FakeProvider:

    def __init__(self, account_id, files=None):
        self.account_id = account_id
        self.files = files if files is not None else []
        self.search_calls = []
        self.delete_calls = []

    def authenticate(self):
        return {"success": True}

    def search_files(self, query):
        self.search_calls.append(query)
        return {
            "success": True,
            "matches": [dict(f) for f in self.files],
        }

    def delete_file_by_id(self, file_id):
        self.delete_calls.append(file_id)
        return {
            "success": True,
            "message": (
                f"Deleted {file_id} from "
                f"{self.account_id}"
            ),
        }


class FakeAI:

    def ask(self, prompt):
        return "FAKE AI RESPONSE"


def make_agent(accounts):
    """
    accounts: {email: [files]}.
    Returns (agent, providers_by_account_id).
    """

    agent = AIAgent()
    agent.ai = FakeAI()

    registry = AccountRegistry()

    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeProvider(
                account.id,
                files=accounts.get(
                    account.email,
                    [],
                ),
            )

        return providers[account.id]

    agent.router.drive_manager = (
        MultiAccountDriveManager(
            registry=registry,
            provider_factory=factory,
        )
    )

    for email in accounts:
        agent.router.drive_manager.connect_account(
            "google_drive",
            email=email,
        )

    return agent, providers


# =========================================================
# SAFETY LAYER ACCOUNT BINDING
# =========================================================


class TestActionSafetyAccountBinding:

    def test_propose_delete_records_account(self):
        safety = ActionSafety()

        pending = safety.propose_delete(
            "f1",
            "notes.txt",
            account_id="account-2",
        )

        assert pending.account_id == "account-2"
        assert safety.has_pending() is True

    def test_proposal_without_account_stays_backward_compatible(self):
        safety = ActionSafety()

        pending = safety.propose_delete("f1", "n.txt")

        assert pending.account_id is None

    def test_describe_mentions_bound_account(self):
        safety = ActionSafety()

        safety.propose_delete(
            "f1",
            "notes.txt",
            account_id="account-3",
        )

        description = (
            safety.get_pending().describe().lower()
        )

        assert "account-3" in description

    def test_empty_target_still_rejected_with_account(self):
        safety = ActionSafety()

        with pytest.raises(ValueError):
            safety.propose_delete(
                "   ",
                "x.txt",
                account_id="account-1",
            )


# =========================================================
# END-TO-END CONFIRMED DELETE PER ACCOUNT
# =========================================================


class TestConfirmedDeletePerAccount:

    def test_confirmation_deletes_only_on_named_account(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "fA", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "fB", "name": "a.txt"}
                ],
            }
        )

        # The same file name exists on BOTH accounts;
        # the user names account 2 explicitly.

        response = agent.chat(
            "Delete a.txt from account 2"
        )

        assert (
            agent.safety.get_pending().account_id
            == "account-2"
        )

        confirmation = agent.chat("confirm delete")

        assert providers[
            "account-2"
        ].delete_calls == ["fB"]

        # Proof of isolation: account 1 was untouched.

        assert providers.get("account-1") is None

    def test_ambiguous_delete_across_accounts_refuses(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "fA", "name": "same.txt"}
                ],
                "two@x.com": [
                    {"id": "fB", "name": "other.txt"}
                ],
            }
        )

        response = agent.chat(
            "Delete same.txt from Drive"
        )

        # No account was named and several are
        # connected -> refuse instead of guessing.

        assert agent.safety.has_pending() is False
        assert providers.get("account-1") is None
        assert providers.get("account-2") is None
        assert "account" in response.lower()

    def test_single_connected_account_delete_still_works(self):
        agent, providers = make_agent(
            {
                "only@x.com": [
                    {"id": "f9", "name": "solo.txt"}
                ],
            }
        )

        agent.chat("Delete solo.txt from Google Drive")

        assert (
            agent.safety.get_pending().account_id
            == "account-1"
        )

        agent.chat("confirm delete")

        assert providers[
            "account-1"
        ].delete_calls == ["f9"]

    def test_disconnected_bound_account_fails_safe(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "fA", "name": "a.txt"}
                ],
                "two@x.com": [],
            }
        )

        agent.chat("Delete a.txt from account 1")

        # The bound account disappears before
        # confirmation arrives.

        agent.router.drive_manager.disconnect_account(
            "account-1"
        )

        response = agent.chat("confirm delete")

        # Fail-safe: no session, no deletion anywhere.

        assert (
            providers["account-1"].delete_calls == []
        )
        assert providers.get("account-2") is None
        assert "couldn't" in response.lower()


# =========================================================
# ROUTER GUARDS
# =========================================================


class TestRouterAccountGuards:

    def test_delete_with_unknown_account_never_touches_legacy(self):
        from agent.tool_router import ToolRouter

        class Legacy:
            def __init__(self):
                self.delete_calls = []

            def delete_file_by_id(self, file_id):
                self.delete_calls.append(file_id)
                return {"success": True}

        router = ToolRouter()
        legacy = Legacy()
        router.google_drive = legacy

        result = router.execute_delete_by_id(
            "fX",
            "x.txt",
            account_id="account-42",
        )

        assert result["success"] is False
        assert legacy.delete_calls == []

    def test_delete_without_account_keeps_legacy_path(self):
        from agent.tool_router import ToolRouter

        class Legacy:
            def __init__(self):
                self.delete_calls = []

            def delete_file_by_id(self, file_id):
                self.delete_calls.append(file_id)
                return {
                    "success": True,
                    "message": "deleted",
                }

        router = ToolRouter()
        legacy = Legacy()
        router.google_drive = legacy

        result = router.execute_delete_by_id("fZ")

        assert result["success"] is True
        assert legacy.delete_calls == ["fZ"]
