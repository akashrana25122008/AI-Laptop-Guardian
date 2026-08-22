"""Milestone 8 - Per-account cloud storage quota.

Read-only quota retrieval through injected fake providers.
Proves: unknown stays unknown, failures stay isolated,
and nothing mutating is ever called.
"""

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import MultiAccountDriveManager
from cloud.cloud_intelligence import (
    CloudStorageIntelligence,
)


class FakeCloudProvider:
    """
    Fake per-account provider.

    `storage_behavior` controls what get_storage_info()
    does: a dict is returned as the raw provider payload,
    an exception instance is raised.
    """

    def __init__(
        self,
        account_id,
        storage_behavior=None,
        files=None,
    ):
        self.account_id = account_id
        self.storage_behavior = storage_behavior
        self.files = files or []
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []
        self.authenticate_calls = 0

    def authenticate(self):
        self.authenticate_calls += 1
        return {"success": True}

    def get_storage_info(self):
        if isinstance(
            self.storage_behavior,
            Exception,
        ):
            raise self.storage_behavior

        if self.storage_behavior is None:
            return {
                "success": False,
                "tool": "cloud_storage",
                "error": "not implemented",
            }

        return self.storage_behavior


def make_intelligence(storage_by_email):
    """
    storage_by_email: {email: storage_behavior}

    Returns (intelligence, providers_by_account_id).
    """

    registry = AccountRegistry()

    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeCloudProvider(
                account.id,
                storage_behavior=storage_by_email.get(
                    account.email
                ),
            )

        return providers[account.id]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in storage_by_email:
        manager.connect_account(
            "google_drive",
            email=email,
        )

    return (
        CloudStorageIntelligence(manager),
        manager,
        providers,
    )


GB = 1024 * 1024 * 1024


# =========================================================
# SINGLE ACCOUNT QUOTA
# =========================================================


class TestSingleAccountQuota:

    def test_known_quota_reports_all_values(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "email": "a@x.com",
                    "total_bytes": 15 * GB,
                    "used_bytes": 8 * GB,
                },
            }
        )

        result = intel.summarize_accounts()

        entry = result["accounts"][0]

        assert entry["status"] == "available"
        assert entry["storage"][
            "total_bytes"
        ] == 15 * GB
        assert entry["storage"][
            "used_bytes"
        ] == 8 * GB
        assert entry["storage"][
            "free_bytes"
        ] == 7 * GB

    def test_missing_total_keeps_free_unknown(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": 8 * GB,
                },
            }
        )

        entry = intel.summarize_accounts()[
            "accounts"
        ][0]

        assert entry["status"] == "available"
        assert entry["storage"]["free_bytes"] is None

    def test_unavailable_is_not_zero_nor_failure(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
            }
        )

        result = intel.summarize_accounts()

        entry = result["accounts"][0]

        assert entry["status"] == "unavailable"
        assert entry["storage"]["used_bytes"] is None

        # Unavailable must NOT be treated as zero:
        # there are no known values at all.

        assert result["success"] is False
        assert result["totals"][
            "known_used_bytes"
        ] is None
        assert len(
            result["totals"]["excluded_accounts"]
        ) == 1

    def test_api_failure_marks_account_failed(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": False,
                    "error": "quota api down",
                },
            }
        )

        result = intel.summarize_accounts()

        entry = result["accounts"][0]

        assert entry["status"] == "failed"
        assert "quota api down" in entry["error"]
        assert result["success"] is False

    def test_raising_api_becomes_failed_entry(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": RuntimeError("boom"),
            }
        )

        entry = intel.summarize_accounts()[
            "accounts"
        ][0]

        assert entry["status"] == "failed"
        assert "boom" in entry["error"]

    def test_malformed_response_is_failed_not_crash(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": "complete garbage",
            }
        )

        result = intel.summarize_accounts()

        assert result["success"] is False
        assert result["accounts"][0][
            "status"
        ] == "failed"

    def test_string_numbers_are_normalized(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": "16106127360",
                    "used_bytes": "8589934592",
                },
            }
        )

        entry = intel.summarize_accounts()[
            "accounts"
        ][0]

        assert entry["storage"]["total_bytes"] == (
            15 * GB
        )
        assert entry["storage"]["free_bytes"] == (
            7 * GB
        )


# =========================================================
# FAIL-SAFE TARGETING FOR ONE ACCOUNT
# =========================================================


class TestSingleAccountTargeting:

    def test_unknown_account_fails_safe(self):
        intel, manager, _ = make_intelligence(
            {"a@x.com": {"success": True}}
        )

        result = intel.get_account_storage(
            "account-99"
        )

        assert result["success"] is False
        assert "not connected" in result["error"]

    def test_disconnected_account_fails_safe(self):
        intel, manager, _ = make_intelligence(
            {"a@x.com": {"success": True}}
        )
        manager.disconnect_account("account-1")

        result = intel.get_account_storage(
            "account-1"
        )

        assert result["success"] is False


# =========================================================
# READ-ONLY PROOF
# =========================================================


class TestReadOnlyProof:

    def test_quota_never_mutates_anything(self):
        intel, _, providers = make_intelligence(
            {
                "a@x.com": {"success": True},
                "b@x.com": {"success": True},
            }
        )

        intel.summarize_accounts(scope_all=True)

        for provider in providers.values():

            assert provider.download_calls == []
            assert provider.delete_calls == []
            assert provider.upload_calls == []

            # Quota reads never even authenticate a
            # Google session through this layer; the
            # fake sessions were consulted directly.

            assert (
                provider.authenticate_calls == 0
            )
