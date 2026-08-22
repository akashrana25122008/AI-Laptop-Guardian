"""Milestone 8 - Cross-account identity preservation.

Analytics results must never silently merge accounts:
every file keeps its originating account id/email, and
the same filename living in two accounts stays two
distinct records with distinct file ids.
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
        large_files=None,
        all_files=None,
    ):
        self.account_id = account_id
        self.large_files = large_files or []
        self.all_files = all_files or []
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
        return {
            "success": True,
            "files": list(self.large_files),
        }

    def list_all_files_metadata(self, limit=200):
        return {
            "success": True,
            "files": list(self.all_files),
        }


def make_intelligence(large_by_email, all_by_email):
    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeCloudProvider(
                account.id,
                large_files=(
                    large_by_email.get(account.email)
                ),
                all_files=(
                    all_by_email.get(account.email)
                ),
            )

        return providers[account.id]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in dict.fromkeys(
        list(large_by_email) + list(all_by_email)
    ):
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
# LARGE FILES KEEP THEIR ORIGIN
# =========================================================


class TestLargeFileIdentity:

    def test_same_filename_two_accounts_stays_separate(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "file-a-1",
                        "name": "backup.zip",
                        "size_bytes": 500 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "file-b-9",
                        "name": "backup.zip",
                        "size_bytes": 500 * MB,
                    },
                ],
            },
            {},
        )

        result = intel.find_large_files(
            min_mb=100,
            scope_all=True,
        )

        assert result["count"] == 2

        ids = sorted(
            file["id"] for file in result["files"]
        )

        assert ids == ["file-a-1", "file-b-9"]

        by_account = {
            file["account_id"]: file
            for file in result["files"]
        }

        assert len(by_account) == 2

        assert (
            by_account["account-1"]["id"]
            == "file-a-1"
        )
        assert (
            by_account["account-1"]["account_email"]
            == "a@x.com"
        )
        assert (
            by_account["account-2"]["id"]
            == "file-b-9"
        )
        assert (
            by_account["account-2"]["account_email"]
            == "b@x.com"
        )

    def test_modified_time_is_preserved(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "big.mov",
                        "size_bytes": 900 * MB,
                        "modified_time": (
                            "2026-01-15T10:00:00Z"
                        ),
                    },
                ],
            },
            {},
        )

        file = intel.find_large_files(
            min_mb=100,
        )["files"][0]

        assert file["modified_time"] == (
            "2026-01-15T10:00:00Z"
        )

    def test_exact_file_ids_survive_end_to_end(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "EXACT-ID-42",
                        "name": "video.mp4",
                        "size_bytes": 2 * MB * MB,
                    },
                ],
            },
            {},
        )

        files = intel.find_large_files(
            min_mb=100,
        )["files"]

        assert files[0]["id"] == "EXACT-ID-42"


# =========================================================
# DUPLICATE COPIES KEEP THEIR ORIGIN
# =========================================================


class TestDuplicateCopyIdentity:

    def test_cross_account_copies_named_per_account(self):
        intel, _, _ = make_intelligence(
            {},
            {
                "a@x.com": [
                    {
                        "id": "orig-1",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                ],
                "b@x.com": [
                    {
                        "id": "copy-7",
                        "name": "report.pdf",
                        "size_bytes": 42 * MB,
                    },
                ],
            },
        )

        result = intel.find_duplicate_candidates(
            scope_all=True
        )

        assert result["group_count"] == 1

        group = result["groups"][0]

        copy_accounts = sorted(
            copy["account_id"]
            for copy in group["copies"]
        )

        assert copy_accounts == [
            "account-1",
            "account-2",
        ]

        copy_emails = sorted(
            copy["account_email"]
            for copy in group["copies"]
        )

        assert copy_emails == [
            "a@x.com",
            "b@x.com",
        ]

        copy_ids = sorted(
            copy["file_id"]
            for copy in group["copies"]
        )

        assert copy_ids == ["copy-7", "orig-1"]

    def test_copies_within_one_account_also_attributed(self):
        intel, _, _ = make_intelligence(
            {},
            {
                "solo@x.com": [
                    {
                        "id": "d1",
                        "name": "data.csv",
                        "size_bytes": 5 * MB,
                    },
                    {
                        "id": "d2",
                        "name": "data.csv",
                        "size_bytes": 5 * MB,
                    },
                ],
            },
        )

        group = intel.find_duplicate_candidates()[
            "groups"
        ][0]

        assert group["count"] == 2

        assert all(
            copy["account_id"] == "account-1"
            for copy in group["copies"]
        )

    def test_analytics_never_mutate_anything(self):
        intel, _, providers = make_intelligence(
            {
                "a@x.com": [
                    {
                        "id": "f1",
                        "name": "huge.iso",
                        "size_bytes": 800 * MB,
                    },
                ],
            },
            {
                "b@x.com": [
                    {
                        "id": "f2",
                        "name": "huge.iso",
                        "size_bytes": 800 * MB,
                    },
                ],
            },
        )

        intel.find_large_files(min_mb=100)
        intel.find_duplicate_candidates(
            scope_all=True
        )

        for provider in providers.values():

            assert provider.download_calls == []
            assert provider.delete_calls == []
            assert provider.upload_calls == []
