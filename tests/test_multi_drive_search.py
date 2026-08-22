"""Milestone 7 - MultiAccountDriveManager search behavior.

All provider sessions are injected fakes. Nothing here
touches Google, tokens, or the network.
"""

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import MultiAccountDriveManager


class FakeProvider:
    """
    Fake per-account Google Drive provider.

    Records every call so tests can prove exactly which
    account was touched.
    """

    def __init__(self, account_id, files=None):
        self.account_id = account_id
        self.files = files if files is not None else []
        self.search_calls = []
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []
        self.authenticate_calls = 0

    def authenticate(self):
        self.authenticate_calls += 1
        return {"success": True}

    def search_files(self, query):
        self.search_calls.append(query)
        return {
            "success": True,
            "matches": [dict(f) for f in self.files],
        }

    def download_file_by_id(self, file_id):
        self.download_calls.append(file_id)
        return {
            "success": True,
            "message": f"Downloaded {file_id}",
        }

    def delete_file_by_id(self, file_id):
        self.delete_calls.append(file_id)
        return {
            "success": True,
            "message": f"Deleted {file_id}",
        }

    def upload_file(self, path):
        self.upload_calls.append(path)
        return {
            "success": True,
            "message": f"Uploaded {path}",
        }


def make_manager(accounts):
    """
    accounts: list of (email, files) tuples.

    Returns (manager, providers_by_account_id).
    """

    registry = AccountRegistry()

    providers = {}

    def factory(account):
        email = account.email

        key = account.id

        if key not in providers:

            files = accounts.get(email, [])

            providers[key] = FakeProvider(
                key,
                files=files,
            )

        return providers[key]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in accounts:
        manager.connect_account(
            "google_drive",
            email=email,
        )

    return manager, providers


# =========================================================
# DETERMINISTIC TARGETING
# =========================================================


class TestSearchTargeting:

    def test_explicit_account_searches_only_that_account(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "f2", "name": "b.txt"}
                ],
            }
        )

        result = manager.search_accounts(
            "report",
            account_ids=["account-1"],
        )

        assert result["success"] is True
        assert providers[
            "account-1"
        ].search_calls == ["report"]

        # The other account was never even consulted.

        assert providers.get("account-2") is None

    def test_matches_carry_account_identity(self):
        manager, _ = make_manager(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [],
            }
        )

        result = manager.search_accounts(
            "x",
            scope_all=True,
        )

        match = result["matches"][0]

        assert match["account_id"] == "account-1"
        assert match["account_email"] == "one@x.com"

    def test_scope_all_searches_every_connected_account(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "f2", "name": "b.txt"}
                ],
            }
        )

        result = manager.search_accounts(
            "x",
            scope_all=True,
        )

        assert result["success"] is True
        assert sorted(result["succeeded_accounts"]) == [
            "account-1",
            "account-2",
        ]
        names = [m["name"] for m in result["matches"]]

        assert names == ["a.txt", "b.txt"]

    def test_single_connected_account_auto_selected(self):
        manager, providers = make_manager(
            {
                "only@x.com": [
                    {"id": "f9", "name": "solo.txt"}
                ],
            }
        )

        result = manager.search_accounts("anything")

        assert result["success"] is True
        assert not result.get("needs_selection")
        assert providers[
            "account-1"
        ].search_calls == ["anything"]

    def test_multiple_accounts_without_choice_asks_user(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        result = manager.search_accounts("x")

        assert result["success"] is False
        assert result.get("needs_selection") is True
        labels = [
            a["label"] for a in result["accounts"]
        ]

        assert labels == ["one@x.com", "two@x.com"]

        # Proof: no provider was consulted while the
        # choice was ambiguous.

        for provider in providers.values():
            assert provider.search_calls == []

    def test_unknown_explicit_account_fails_safe(self):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        result = manager.search_accounts(
            "x",
            account_ids=["account-99"],
        )

        assert result["success"] is False
        assert "not connected" in result["error"]

        for provider in providers.values():
            assert provider.search_calls == []

    def test_empty_query_refused_before_any_provider_call(
        self,
    ):
        manager, providers = make_manager(
            {"one@x.com": []}
        )

        result = manager.search_accounts("   ")

        assert result["success"] is False
        assert "query" in result["error"].lower()

        # No session was ever constructed.

        assert manager._sessions == {}


# =========================================================
# PARTIAL AND TOTAL FAILURE HANDLING
# =========================================================


class TestFailureHandling:

    def test_one_failed_account_never_hides_other_results(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [],
            }
        )

        # Warm both lazy sessions, then break one.

        manager.get_session("account-1")
        manager.get_session("account-2")

        providers["account-2"].search_files = (
            lambda query: {
                "success": False,
                "error": "quota exceeded",
            }
        )

        result = manager.search_accounts(
            "x",
            scope_all=True,
        )

        assert result["success"] is True
        assert result["succeeded_accounts"] == [
            "account-1"
        ]
        assert len(result["matches"]) == 1
        assert any(
            entry["error"] == "quota exceeded"
            for entry in result["account_errors"]
        )

    def test_all_accounts_failing_reports_failure(self):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        manager.get_session("account-1")
        manager.get_session("account-2")

        for provider in providers.values():

            provider.search_files = lambda query: {
                "success": False,
                "error": "offline",
            }

        result = manager.search_accounts(
            "x",
            scope_all=True,
        )

        assert result["success"] is False
        assert "offline" in result["error"]
        assert result["matches"] == []

    def test_raising_account_is_reported_not_crashing(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [],
            }
        )

        def explode(query):
            raise RuntimeError("boom")

        manager.get_session("account-1")
        manager.get_session("account-2")

        providers["account-1"].search_files = explode

        result = manager.search_accounts(
            "x",
            scope_all=True,
        )

        assert result["success"] is True
        errors = {
            entry["account_id"]: entry["error"]
            for entry in result["account_errors"]
        }

        assert errors.get("account-1") == "boom"


# =========================================================
# BOUND OPERATIONS
# =========================================================


class TestBoundOperations:

    def test_download_hits_only_named_account(self):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        result = manager.download_from_account(
            "account-2",
            "fB",
        )

        assert result["success"] is True
        assert result["account_id"] == "account-2"
        assert providers[
            "account-2"
        ].download_calls == ["fB"]

        # The other account's provider was never even
        # constructed (lazy isolation).

        assert providers.get("account-1") is None

    def test_delete_hits_only_named_account(self):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        result = manager.delete_from_account(
            "account-1",
            "fA",
        )

        assert result["success"] is True
        assert providers[
            "account-1"
        ].delete_calls == ["fA"]
        assert providers.get("account-2") is None

    def test_upload_hits_only_named_account(self):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )

        result = manager.upload_to_account(
            "account-2",
            "notes.txt",
        )

        assert result["success"] is True
        assert providers[
            "account-2"
        ].upload_calls == ["notes.txt"]
        assert providers.get("account-1") is None

    def test_operations_on_disconnected_account_fail_safe(
        self,
    ):
        manager, providers = make_manager(
            {
                "one@x.com": [],
                "two@x.com": [],
            }
        )
        manager.disconnect_account("account-1")

        result = manager.delete_from_account(
            "account-1",
            "fA",
        )

        assert result["success"] is False
        assert "session" in result["error"].lower()

        # The surviving account must stay untouched.

        assert providers.get("account-2") is None

    def test_empty_file_id_refused_locally(self):
        manager, _ = make_manager({"one@x.com": []})

        for operation in (
            manager.download_from_account,
            manager.delete_from_account,
        ):

            result = operation("account-1", "  ")

            assert result["success"] is False

    def test_raising_operation_returns_failure_result(self):
        manager, providers = make_manager(
            {"one@x.com": []}
        )

        def explode(file_id):
            raise RuntimeError("api down")

        manager.get_session("account-1")

        providers[
            "account-1"
        ].delete_file_by_id = explode

        result = manager.delete_from_account(
            "account-1",
            "fA",
        )

        assert result["success"] is False
        assert result["account_id"] == "account-1"
        assert "api down" in result["error"]
