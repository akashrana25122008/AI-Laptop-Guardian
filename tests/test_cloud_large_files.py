"""Milestone 8 - Cross-account large-file analysis.

Threshold semantics, defensive re-filtering, honest
partial failures, and the metadata-only guarantee
(files are never downloaded to be measured).
"""

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import MultiAccountDriveManager
from cloud.cloud_intelligence import (
    DEFAULT_LARGE_FILE_MIN_MB,
    CloudStorageIntelligence,
)


MB = 1024 * 1024


class FakeCloudProvider:

    def __init__(
        self,
        account_id,
        large=None,
        behavior="ok",
    ):
        self.account_id = account_id
        self.large = large or []
        self.behavior = behavior
        self.list_calls = []
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []

    def authenticate(self):
        return {"success": True}

    def list_large_files(
        self,
        min_size_bytes=0,
        limit=50,
    ):
        self.list_calls.append(
            {
                "min_size_bytes": min_size_bytes,
                "limit": limit,
            }
        )

        if self.behavior == "raise":
            raise RuntimeError("listing exploded")

        if self.behavior == "fail":
            return {
                "success": False,
                "error": "api quota exhausted",
            }

        return {
            "success": True,
            "files": list(self.large),
        }


def make_intelligence(large_by_email):
    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeCloudProvider(
                account.id,
                large=large_by_email.get(
                    account.email
                ),
            )

        return providers[account.id]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in large_by_email:
        manager.connect_account(
            "google_drive",
            email=email,
        )

    return (
        CloudStorageIntelligence(manager),
        manager,
        providers,
    )


# =========================================================
# THRESHOLD SEMANTICS
# =========================================================


class TestThresholds:

    def test_default_threshold_is_100_mb(self):
        assert DEFAULT_LARGE_FILE_MIN_MB == 100

        intel, _, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "small",
                        "name": "notes.txt",
                        "size_bytes": 10 * MB,
                    },
                    {
                        "id": "big",
                        "name": "movie.mkv",
                        "size_bytes": 300 * MB,
                    },
                ],
            }
        )

        result = intel.find_large_files()

        names = [
            file["name"] for file in result["files"]
        ]

        assert names == ["movie.mkv"]
        assert result["min_mb"] == 100

        # Provider was asked with byte threshold.

        call = providers["account-1"].list_calls[0]

        assert call["min_size_bytes"] == (
            100 * MB
        )

    def test_explicit_threshold_honored(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "medium.bin",
                        "size_bytes": 200 * MB,
                    },
                    {
                        "id": "f2",
                        "name": "huge.bin",
                        "size_bytes": 900 * MB,
                    },
                ],
            }
        )

        result = intel.find_large_files(min_mb=500)

        names = [
            file["name"] for file in result["files"]
        ]

        assert names == ["huge.bin"]
        assert result["min_mb"] == 500.0

    def test_boundary_file_exactly_at_threshold_included(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "edge",
                        "name": "edge.bin",
                        "size_bytes": 100 * MB,
                    },
                ],
            }
        )

        result = intel.find_large_files(min_mb=100)

        assert result["count"] == 1

    def test_subthreshold_file_defensively_removed(self):
        """
        Even if a provider misbehaves and returns a file
        below the threshold, the intelligence layer must
        filter it out.
        """

        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "tiny",
                        "name": "tiny.txt",
                        "size_bytes": 1 * MB,
                    },
                ],
            }
        )

        # Ask for 500 MB; provider ignores thresholds
        # and returns everything.

        result = intel.find_large_files(min_mb=500)

        assert result["files"] == []

    def test_malformed_sizes_are_skipped(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "doc",
                        "name": "doc.gdoc",
                        "size_bytes": None,
                    },
                    {
                        "id": "zero",
                        "name": "empty.log",
                        "size_bytes": 0,
                    },
                    "not-even-a-dict",
                    {
                        "id": "good",
                        "name": "real.zip",
                        "size_bytes": 250 * MB,
                    },
                ],
            }
        )

        result = intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        assert [
            file["name"] for file in result["files"]
        ] == ["real.zip"]


# =========================================================
# MULTI-ACCOUNT BEHAVIOR
# =========================================================


class TestMultiAccount:

    def test_results_merged_and_sorted_by_size(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "a1",
                        "name": "mid.bin",
                        "size_bytes": 400 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "b1",
                        "name": "giant.iso",
                        "size_bytes": 4 * 1024 * MB,
                    },
                    {
                        "id": "b2",
                        "name": "smaller.mov",
                        "size_bytes": 150 * MB,
                    },
                ],
            }
        )

        result = intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        names = [
            file["name"] for file in result["files"]
        ]

        assert names == [
            "giant.iso",
            "mid.bin",
            "smaller.mov",
        ]
        assert sorted(
            result["succeeded_accounts"]
        ) == ["account-1", "account-2"]

    def test_one_failed_account_does_not_hide_others(self):
        intel, manager, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "a1",
                        "name": "ok.zip",
                        "size_bytes": 500 * MB,
                    },
                ],
                "b@x.com": [],
            }
        )

        # Realize both sessions first so the providers map
        # is fully populated before overriding behavior.

        for account_id in (
            "account-1",
            "account-2",
        ):
            manager.get_session(account_id)

        providers["account-2"].behavior = "raise"

        result = intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        assert result["success"] is True
        assert [
            file["id"] for file in result["files"]
        ] == ["a1"]

        errors = {
            error["account_id"]: error["error"]
            for error in result["account_errors"]
        }

        assert "account-2" in errors
        assert "exploded" in errors["account-2"]

    def test_all_accounts_failing_reports_failure(self):
        intel, manager, providers = make_intelligence(
            {
                "a@x.com": [],
                "b@x.com": [],
            }
        )

        for account_id in (
            "account-1",
            "account-2",
        ):
            manager.get_session(account_id)

        providers["account-1"].behavior = "fail"
        providers["account-2"].behavior = "fail"

        result = intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        assert result["success"] is False
        assert result["files"] == []
        assert len(result["account_errors"]) == 2


# =========================================================
# TARGETING + READ-ONLY PROOF
# =========================================================


class TestTargetingAndSafety:

    def test_multiple_accounts_without_scope_ask_user(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [],
                "b@x.com": [],
            }
        )

        result = intel.find_large_files()

        assert result.get("needs_selection") is True

    def test_zero_accounts_fails_cleanly(self):
        intel, _, _ = make_intelligence({})

        result = intel.find_large_files()

        assert result["success"] is False
        assert "No connected" in result["error"]

    def test_metadata_only_no_downloads_ever(self):
        intel, _, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "big.one",
                        "size_bytes": 700 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "f2",
                        "name": "big.two",
                        "size_bytes": 600 * MB,
                    },
                ],
            }
        )

        intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        for provider in providers.values():

            assert provider.download_calls == []
            assert provider.delete_calls == []
            assert provider.upload_calls == []
