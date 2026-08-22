"""Milestone 7 - AIAgent multi-account chat flows.

End-to-end agent behavior over fake providers: account
disambiguation, scoped searches, and account-bound
downloads. No network, no OAuth, no real AI calls.
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
    """Fake per-account provider with call recording."""

    def __init__(self, account_id, files=None):
        self.account_id = account_id
        self.files = files if files is not None else []
        self.search_calls = []
        self.download_calls = []

    def authenticate(self):
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


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
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
# DISAMBIGUATION
# =========================================================


class TestAccountDisambiguation:

    def test_multiple_accounts_prompt_selection(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "f2", "name": "b.txt"}
                ],
            }
        )

        response = agent.chat(
            "Search Drive for notes"
        )

        assert "which account" in response.lower()
        assert "one@x.com" in response
        assert "two@x.com" in response

        # Ambiguity must never leak into provider calls.

        for provider in providers.values():
            assert provider.search_calls == []

    def test_single_account_searches_without_asking(self):
        agent, providers = make_agent(
            {
                "only@x.com": [
                    {
                        "id": "f9",
                        "name": "solo.txt",
                    }
                ],
            }
        )

        response = agent.chat("Search Drive for solo")

        assert providers[
            "account-1"
        ].search_calls == ["solo"]
        assert "solo.txt" in response
        assert "only@x.com" in response


# =========================================================
# SCOPED SEARCHES THROUGH CHAT
# =========================================================


class TestScopedSearchThroughChat:

    def test_explicit_account_chat_search(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "f2", "name": "b.txt"}
                ],
            }
        )

        response = agent.chat(
            "Search account 1 for report"
        )

        assert providers[
            "account-1"
        ].search_calls == ["report"]

        # The other account was never even consulted.

        assert providers.get("account-2") is None
        assert "a.txt" in response

    def test_all_drives_chat_search_merges_results(self):
        agent, providers = make_agent(
            {
                "one@x.com": [
                    {"id": "f1", "name": "a.txt"}
                ],
                "two@x.com": [
                    {"id": "f2", "name": "b.txt"}
                ],
            }
        )

        response = agent.chat(
            "Search all my Google Drives for docs"
        )

        assert sorted(
            providers["account-1"].search_calls
            + providers["account-2"].search_calls
        ) == ["docs", "docs"]
        assert "a.txt" in response
        assert "b.txt" in response

        # Both matches carry their account labels.

        assert "one@x.com" in response
        assert "two@x.com" in response

    def test_unknown_account_reference_is_refused(self):
        agent, providers = make_agent(
            {"one@x.com": []}
        )

        response = agent.chat(
            "Search account 5 for ghosts"
        )

        assert "couldn't" in response.lower()
        assert "'5'" in response

        # Nothing anywhere was searched.

        assert providers.get("account-1") is None


# =========================================================
# ACCOUNT-BOUND NUMBERED DOWNLOADS
# =========================================================


class TestAccountBoundDownloads:

    def test_numbered_download_hits_only_source_account(self):
        agent, providers = make_agent(
            {
                "one@x.com": [],
                "two@x.com": [
                    {
                        "id": "fB",
                        "name": "b.txt",
                    }
                ],
            }
        )

        # Scoped search stores account-tagged matches.

        agent.chat("Search account 2 for b")

        response = agent.chat("Download number 1")

        assert providers[
            "account-2"
        ].download_calls == ["fB"]

        # The other account was never touched.

        assert providers.get("account-1") is None
        assert "fb" in response.lower() or (
            "downloaded" in response.lower()
        )

    def test_download_without_prior_search_stays_safe(self):
        agent, _ = make_agent({"one@x.com": []})

        response = agent.chat("Download number 1")

        assert "search" in response.lower()


# =========================================================
# LEGACY SINGLE-PROVIDER BEHAVIOR PRESERVED
# =========================================================


class TestLegacyPreserved:

    def test_zero_registered_accounts_use_default_provider(self):
        from agent.ai_agent import AIAgent as Fresh

        class LegacyProvider:

            def __init__(self):
                self.search_calls = []

            def search_files(self, query):
                self.search_calls.append(query)
                return {
                    "success": True,
                    "matches": [
                        {
                            "id": "old",
                            "name": "invoices.xlsx",
                        }
                    ],
                }

        agent = Fresh()
        agent.ai = FakeAI()

        legacy = LegacyProvider()
        agent.router.google_drive = legacy

        response = agent.chat(
            "Search Google Drive for invoices"
        )

        assert legacy.search_calls == ["invoices"]
        assert "invoices.xlsx" in response

        # And the registry stayed untouched.

        assert (
            agent.router.drive_manager.registry.count()
            == 0
        )
