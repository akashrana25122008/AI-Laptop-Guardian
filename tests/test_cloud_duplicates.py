"""Milestone 8 - Duplicate CANDIDATES across accounts.

Matching is name (case/whitespace-insensitive) + exact
size only. Results are always labeled as possible, never
confirmed, and nothing is ever deleted or modified.
"""

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import MultiAccountDriveManager
from cloud.cloud_intelligence import (
    CloudStorageIntelligence,
)


MB = 1024 * 1024


class FakeCloudProvider:

    def __init__(
        self,
        account_id,
        files=None,
    ):
        self.account_id = account_id
        self.files = files or []
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []

    def authenticate(self):
        return {"success": True}

    def list_all_files_metadata(self, limit=200):
        return {
            "success": True,
            "files": list(self.files),
        }


def make_intelligence(files_by_email):
    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeCloudProvider(
                account.id,
                files=files_by_email.get(
                    account.email
                ),
            )

        return providers[account.id]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in files_by_email:
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
# MATCHING RULES
# =========================================================


class TestMatchingRules:

    def test_same_name_and_size_grouped_across_accounts(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "f2",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates(
            scope_all=True
        )

        assert result["group_count"] == 1

        group = result["groups"][0]

        assert group["name"] == "report.pdf"
        assert group["count"] == 2

    def test_case_and_whitespace_normalized(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": " Report.PDF ",
                        "size_bytes": 42 * MB,
                    },
                    {
                        "id": "f2",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result["group_count"] == 1
        assert result["groups"][0]["count"] == 2

    def test_same_name_different_size_not_grouped(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "v1",
                        "name": "trip.mp4",
                        "size_bytes": 800 * MB,
                    },
                    {
                        "id": "v2",
                        "name": "trip.mp4",
                        "size_bytes": 1200 * MB,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result["groups"] == []

    def test_same_size_different_name_not_grouped(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "alpha.bin",
                        "size_bytes": 50 * MB,
                    },
                    {
                        "id": "f2",
                        "name": "beta.bin",
                        "size_bytes": 50 * MB,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result["groups"] == []

    def test_unique_files_produce_no_groups(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "one.txt",
                        "size_bytes": 10,
                    },
                    {
                        "id": "f2",
                        "name": "two.txt",
                        "size_bytes": 20,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result["files_scanned"] == 2
        assert result["groups"] == []
        assert (
            result["potential_reclaim_bytes"] == 0
        )

    def test_files_without_real_size_excluded(self):
        """
        Google Docs-style entries (no size) and empty
        sizes can never match by size, so they are
        excluded from candidate grouping.
        """

        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "g1",
                        "name": "doc.gdoc",
                        "size_bytes": None,
                    },
                    {
                        "id": "z1",
                        "name": "empty.tmp",
                        "size_bytes": 0,
                    },
                    {
                        "id": "g2",
                        "name": "doc.gdoc",
                        "size_bytes": None,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result["files_scanned"] == 3
        assert result["groups"] == []


# =========================================================
# CANDIDATE SEMANTICS (POSSIBLE, NEVER CONFIRMED)
# =========================================================


class TestCandidateSemantics:

    def test_groups_labeled_possible_and_unconfirmed(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "same.zip",
                        "size_bytes": 7 * MB,
                    },
                    {
                        "id": "f2",
                        "name": "same.zip",
                        "size_bytes": 7 * MB,
                    },
                ],
            }
        )

        group = (
            intel.find_duplicate_candidates()[
                "groups"
            ][0]
        )

        assert group["confirmed"] is False
        assert group["match_level"] == (
            "possible (same name + same size)"
        )

    def test_reclaim_math_is_deterministic(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "r1",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                    {
                        "id": "p1",
                        "name": "photo.jpg",
                        "size_bytes": 10 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "r2",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                    {
                        "id": "p2",
                        "name": "photo.jpg",
                        "size_bytes": 10 * MB,
                    },
                ],
            }
        )

        result = intel.find_duplicate_candidates(
            scope_all=True
        )

        # Two groups of two: each can reclaim one copy.

        assert result["potential_reclaim_bytes"] == (
            52 * MB
        )
        assert result["group_count"] == 2

        reclaim_order = [
            group["name"]
            for group in result["groups"]
        ]

        # Sorted by largest reclaim potential first.

        assert reclaim_order[0] == "report.pdf"

    def test_three_copies_reclaim_two_copies_worth(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "c1",
                        "name": "set.rar",
                        "size_bytes": 3 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "c2",
                        "name": "set.rar",
                        "size_bytes": 3 * MB,
                    },
                    {
                        "id": "c3",
                        "name": "set.rar",
                        "size_bytes": 3 * MB,
                    },
                ],
            }
        )

        group = intel.find_duplicate_candidates(
            scope_all=True
        )[
            "groups"
        ][0]

        assert group["count"] == 3
        assert group[
            "potential_reclaim_bytes"
        ] == 6 * MB


# =========================================================
# PARTIAL FAILURE + TARGETING
# =========================================================


class TestFailureAndTargeting:

    def test_one_failed_account_still_scans_healthy(self):
        intel, manager, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "keep.zip",
                        "size_bytes": 9 * MB,
                    },
                ],
                "b@x.com": [],
            }
        )

        manager.get_session("account-1")
        manager.get_session("account-2")

        providers[
            "account-2"
        ].list_all_files_metadata = None

        result = (
            intel.find_duplicate_candidates(
                scope_all=True
            )
        )

        # account-2's provider lacks metadata listing.

        assert result["success"] is True
        assert result["succeeded_accounts"] == [
            "account-1"
        ]
        assert len(result["account_errors"]) == 1

    def test_zero_accounts_fails_cleanly(self):
        intel, _, _ = make_intelligence({})

        result = intel.find_duplicate_candidates()

        assert result["success"] is False
        assert "No connected" in result["error"]

    def test_multiple_accounts_without_scope_ask_user(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [],
                "b@x.com": [],
            }
        )

        result = intel.find_duplicate_candidates()

        assert result.get("needs_selection") is True


# =========================================================
# READ-ONLY PROOF
# =========================================================


class TestReadOnlyProof:

    def test_analysis_never_deletes_anything(self):
        intel, _, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "d1",
                        "name": "dup.bin",
                        "size_bytes": 5 * MB,
                    },
                    {
                        "id": "d2",
                        "name": "dup.bin",
                        "size_bytes": 5 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "d3",
                        "name": "dup.bin",
                        "size_bytes": 5 * MB,
                    },
                ],
            }
        )

        intel.find_duplicate_candidates(
            scope_all=True
        )

        for provider in providers.values():

            assert provider.download_calls == []
            assert provider.delete_calls == []
            assert provider.upload_calls == []
