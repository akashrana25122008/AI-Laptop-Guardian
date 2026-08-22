"""Milestone 8 - AIAgent chat flows for cloud intelligence.

End-to-end deterministic answers over fake providers:
quota summaries, large-file reports, duplicate
candidates, and the unified local+cloud overview.

Hard assertions:

    - analytics answers are produced WITHOUT any AI call,
    - no mutating provider call ever happens,
    - local disks and cloud quota are never merged,
    - Milestone 7 zero-account behavior is preserved.
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


MB = 1024 * 1024
GB = 1024 * 1024 * 1024


class FakeProvider:
    """
    Full fake per-account provider covering quota,
    listings, search, and MUTATING operations that must
    stay untouched by intelligence flows.
    """

    def __init__(
        self,
        account_id,
        storage=None,
        large_files=None,
        all_files=None,
    ):
        self.account_id = account_id
        self.storage = storage
        self.large_files = large_files or []
        self.all_files = all_files or []
        self.search_calls = []
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []

    def authenticate(self):
        return {"success": True}

    def get_storage_info(self):
        return self.storage

    def list_large_files(
        self,
        min_size_bytes=0,
        limit=50,
    ):
        return {
            "success": True,
            "files": [
                dict(f)
                for f in self.large_files
                if f.get("size_bytes", 0)
                >= min_size_bytes
            ],
        }

    def list_all_files_metadata(self, limit=200):
        return {
            "success": True,
            "files": [
                dict(f) for f in self.all_files
            ],
        }

    def search_files(self, query):
        self.search_calls.append(query)
        return {"success": True, "matches": []}

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


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class FakeStorageTool:
    """Deterministic local disk scanner replacement."""

    def get_drive_info(self):
        return [
            {
                "drive": "C:\\",
                "total_gb": 476,
                "used_gb": 401,
                "free_gb": 75,
                "percent_used": 84.2,
            }
        ]

    def get_temp_files_size(self):
        return {"count": 3, "size_mb": 120}

    def get_drive_status(self, usage_percent):
        return "Warning"


def make_agent(accounts):
    """
    accounts: {email: {storage, large_files, all_files}}.

    Returns (agent, providers_by_account_id).
    """

    agent = AIAgent()

    agent.ai = FakeAI()

    agent.router.storage_tool = FakeStorageTool()

    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            config = accounts.get(account.email) or {}

            providers[account.id] = FakeProvider(
                account.id,
                storage=config.get("storage"),
                large_files=config.get(
                    "large_files"
                ),
                all_files=config.get("all_files"),
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
# STORAGE SUMMARY ANSWERS
# =========================================================


class TestStorageSummaryFlow:

    def test_summary_is_deterministic_without_ai(self):
        agent, _ = make_agent(
            {
                "a@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 15 * GB,
                        "used_bytes": 8 * GB,
                    },
                },
            }
        )

        response = agent.chat(
            "How much Google Drive storage do I have?"
        )

        assert "a@x.com" in response
        assert "8.00 GB used" in response
        assert "7.00 GB free" in response
        assert "15.00 GB total" in response
        assert "Most free space" in response

        # Deterministic layer answered alone.

        assert agent.ai.prompts == []

    def test_multi_account_summary_with_totals(self):
        agent, _ = make_agent(
            {
                "a@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 15 * GB,
                        "used_bytes": 8 * GB,
                    },
                },
                "b@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 15 * GB,
                        "used_bytes": 12 * GB,
                    },
                },
            }
        )

        response = agent.chat(
            "Give me a storage report for all my "
            "accounts."
        )

        # Every account is named - nothing is silently
        # merged.

        assert "a@x.com" in response
        assert "b@x.com" in response
        assert "Known total used" in response
        assert "20.00 GB" in response

        assert agent.ai.prompts == []

    def test_unavailable_account_reported_not_hidden(self):
        agent, _ = make_agent(
            {
                "healthy@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 10 * GB,
                        "used_bytes": 3 * GB,
                    },
                },
                "quiet@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": None,
                        "used_bytes": None,
                    },
                },
            }
        )

        response = agent.chat(
            "How much space is left across my Google "
            "accounts?"
        )

        # Incomplete data is never presented as complete.

        assert "Not included" in response
        assert "quiet@x.com" in response
        assert (
            "available account(s)"
            in response
        )

        # Healthy account data still shown honestly.

        assert "healthy@x.com" in response
        assert "3.00 GB used" in response

        assert agent.ai.prompts == []

    def test_failed_account_shown_with_reason(self):
        agent, _ = make_agent(
            {
                "dead@x.com": None,
                "live@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 5 * GB,
                        "used_bytes": 1 * GB,
                    },
                },
            }
        )

        response = agent.chat(
            "What is my Google Drive quota?"
        )

        assert "failed" in response.lower()
        assert "dead@x.com" in response
        assert "live@x.com" in response

    def test_zero_accounts_gives_clean_failure(self):
        agent = AIAgent()

        agent.ai = FakeAI()

        response = agent.chat(
            "How much Google Drive storage do I have?"
        )

        lowered = response.lower()

        assert "couldn't" in lowered
        assert "no connected" in lowered

    def test_single_account_never_asks_for_selection(self):
        agent, _ = make_agent(
            {
                "only@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 9 * GB,
                        "used_bytes": 4 * GB,
                    },
                },
            }
        )

        response = agent.chat(
            "How much Google Drive storage do I have?"
        )

        assert "which account" not in (
            response.lower()
        )
        assert "only@x.com" in response


# =========================================================
# LARGE FILE ANSWERS
# =========================================================


class TestLargeFilesFlow:

    def test_largest_files_reported_with_sizes_and_accounts(self):
        agent, _ = make_agent(
            {
                "a@x.com": {
                    "large_files": [
                        {
                            "id": "f1",
                            "name": "movie.mkv",
                            "size_bytes": (
                                300 * MB
                            ),
                        },
                    ],
                },
                "b@x.com": {
                    "large_files": [
                        {
                            "id": "f2",
                            "name": "backup.iso",
                            "size_bytes": (
                                900 * MB
                            ),
                        },
                    ],
                },
            }
        )

        response = agent.chat(
            "Find my largest files in Google Drive."
        )

        assert "Large cloud files over 100 MB" in (
            response
        )
        assert "backup.iso" in response
        assert "movie.mkv" in response
        assert "b@x.com" in response
        assert "read-only" in response

        assert agent.ai.prompts == []

    def test_threshold_query_filters_small_files(self):
        agent, _ = make_agent(
            {
                "a@x.com": {
                    "large_files": [
                        {
                            "id": "small",
                            "name": "notes.txt",
                            "size_bytes": 10 * MB,
                        },
                        {
                            "id": "big",
                            "name": "huge.bin",
                            "size_bytes": (
                                700 * MB
                            ),
                        },
                    ],
                },
            }
        )

        response = agent.chat(
            "Show me files larger than 500 MB in "
            "Google Drive"
        )

        assert "huge.bin" in response
        assert "notes.txt" not in response
        assert "500 MB" in response


# =========================================================
# DUPLICATE CANDIDATE ANSWERS
# =========================================================


class TestDuplicatesFlow:

    def test_candidates_labeled_possible_not_confirmed(self):
        agent, providers = make_agent(
            {
                "a@x.com": {
                    "all_files": [
                        {
                            "id": "f1",
                            "name": "report.pdf",
                            "size_bytes": 42 * MB,
                        },
                    ],
                },
                "b@x.com": {
                    "all_files": [
                        {
                            "id": "f2",
                            "name": "report.pdf",
                            "size_bytes": 42 * MB,
                        },
                    ],
                },
            }
        )

        response = agent.chat(
            "Show me possible duplicate files across my "
            "Google Drives."
        )

        assert "report.pdf" in response
        assert (
            "NOT confirmed duplicates" in response
        )
        assert (
            "Nothing was deleted or modified"
            in response
        )
        assert "Potential duplicate space" in (
            response
        )

        # Analysis NEVER deletes anything anywhere.

        for provider in providers.values():

            assert provider.delete_calls == []
            assert provider.download_calls == []
            assert provider.upload_calls == []

        assert agent.ai.prompts == []


# =========================================================
# UNIFIED OVERVIEW (LOCAL + CLOUD SEPARATE)
# =========================================================


class TestOverviewFlow:

    def test_overview_reports_local_and_cloud_separately(self):
        agent, _ = make_agent(
            {
                "cloudy@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 15 * GB,
                        "used_bytes": 8 * GB,
                    },
                },
            }
        )

        response = agent.chat(
            "Show me a local and cloud storage overview"
        )

        # Both worlds are present, clearly separated.

        assert "LOCAL" in response
        assert "CLOUD" in response
        assert "C:\\" in response
        assert "84% used" in response
        assert "cloudy@x.com" in response
        assert (
            "separate resources and are reported "
            "separately" in response
        )

        assert agent.ai.prompts == []


# =========================================================
# MILESTONE 7 REGRESSIONS THROUGH THE AGENT
# =========================================================


class TestLegacyAgentBehaviorPreserved:

    def test_zero_account_search_still_falls_back(self):
        agent = AIAgent()

        agent.ai = FakeAI()

        response = agent.chat(
            "Search Google Drive for anything"
        )

        # Legacy fallback path still exists and answers
        # without crashing.

        assert isinstance(response, str)
        assert response

    def test_analytics_flows_leave_legacy_tools_alone(self):
        agent, providers = make_agent(
            {
                "a@x.com": {
                    "storage": {
                        "success": True,
                        "total_bytes": 15 * GB,
                        "used_bytes": 8 * GB,
                    },
                },
            }
        )

        agent.chat("How much Google Drive storage do "
                   "I have?")

        agent.chat("Find my largest files in Google "
                   "Drive.")

        agent.chat("Show me possible duplicate files "
                   "across my Google Drives.")

        for provider in providers.values():

            assert provider.download_calls == []
            assert provider.delete_calls == []
            assert provider.upload_calls == []
