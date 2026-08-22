"""Milestone 8 - Multi-account storage summary.

Deterministic aggregation with honest partial failures:
one broken account never hides healthy accounts, and
unavailable values are never treated as zero.
"""

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import MultiAccountDriveManager
from cloud.cloud_intelligence import (
    CloudStorageIntelligence,
)


GB = 1024 * 1024 * 1024


class FakeCloudProvider:

    def __init__(
        self,
        account_id,
        storage_behavior=None,
    ):
        self.account_id = account_id
        self.storage_behavior = storage_behavior
        self.download_calls = []
        self.delete_calls = []
        self.upload_calls = []

    def authenticate(self):
        return {"success": True}

    def get_storage_info(self):

        if isinstance(
            self.storage_behavior,
            Exception,
        ):
            raise self.storage_behavior

        return self.storage_behavior


def make_intelligence(behavior_by_email):
    registry = AccountRegistry()
    providers = {}

    def factory(account):

        if account.id not in providers:

            providers[account.id] = FakeCloudProvider(
                account.id,
                storage_behavior=(
                    behavior_by_email.get(
                        account.email
                    )
                ),
            )

        return providers[account.id]

    manager = MultiAccountDriveManager(
        registry=registry,
        provider_factory=factory,
    )

    for email in behavior_by_email:
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
# AGGREGATION
# =========================================================


class TestAggregation:

    def test_all_accounts_succeed(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": 15 * GB,
                    "used_bytes": 8 * GB,
                },
                "b@x.com": {
                    "success": True,
                    "total_bytes": 15 * GB,
                    "used_bytes": 12 * GB,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        assert result["success"] is True

        totals = result["totals"]

        assert totals["known_used_bytes"] == 20 * GB
        assert totals["known_free_bytes"] == 10 * GB
        assert totals["excluded_accounts"] == []
        assert len(
            totals["included_account_ids"]
        ) == 2

    def test_one_failed_account_does_not_hide_others(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 3 * GB,
                },
                "b@x.com": RuntimeError("auth dead"),
                "c@x.com": {
                    "success": True,
                    "total_bytes": 20 * GB,
                    "used_bytes": 5 * GB,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        # Healthy accounts remain fully available.

        assert result["success"] is True

        statuses = {
            entry["label"]: entry["status"]
            for entry in result["accounts"]
        }

        assert statuses["a@x.com"] == "available"
        assert statuses["c@x.com"] == "available"
        assert statuses["b@x.com"] == "failed"

        # Totals only include known values.

        totals = result["totals"]

        assert totals["known_used_bytes"] == 8 * GB

        excluded = totals["excluded_accounts"]

        assert len(excluded) == 1
        assert excluded[0]["account_id"] == (
            "account-2"
        )
        assert excluded[0]["status"] == "failed"

    def test_unavailable_value_not_summed_as_zero(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
                "b@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 4 * GB,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        totals = result["totals"]

        # Only account B's known values are summed.

        assert totals["known_used_bytes"] == 4 * GB

        # The unavailable account is explicit.

        labels = [
            entry["label"]
            for entry in totals[
                "excluded_accounts"
            ]
        ]

        assert labels == ["a@x.com"]

    def test_only_unknown_values_give_no_totals(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
                "b@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        totals = result["totals"]

        assert totals[
            "known_used_bytes"
        ] is None
        assert totals[
            "known_free_bytes"
        ] is None


# =========================================================
# TARGETING RULES
# =========================================================


class TestSummaryTargeting:

    def test_zero_connected_accounts_fails_cleanly(self):
        intel, _, _ = make_intelligence({})

        result = intel.summarize_accounts()

        assert result["success"] is False
        assert "No connected" in result["error"]

    def test_single_account_used_automatically(self):
        intel, _, _ = make_intelligence(
            {
                "only@x.com": {
                    "success": True,
                    "total_bytes": 5 * GB,
                    "used_bytes": 1 * GB,
                },
            }
        )

        result = intel.summarize_accounts()

        assert result["success"] is True
        assert len(result["accounts"]) == 1

    def test_multiple_accounts_without_scope_ask_user(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {"success": True},
                "b@x.com": {"success": True},
            }
        )

        result = intel.summarize_accounts()

        assert result.get("needs_selection") is True
        assert len(result.get("accounts", [])) == 2

    def test_explicit_unknown_id_fails_safe(self):
        intel, _, _ = make_intelligence(
            {"a@x.com": {"success": True}}
        )

        result = intel.summarize_accounts(
            account_ids=["account-42"]
        )

        assert result["success"] is False
        assert "not connected" in result["error"]


# =========================================================
# INSIGHTS INSIDE THE SUMMARY
# =========================================================


class TestSummaryInsights:

    def test_insights_identify_extremes(self):
        intel, _, _ = make_intelligence(
            {
                "small@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 2 * GB,
                },
                "big@x.com": {
                    "success": True,
                    "total_bytes": 15 * GB,
                    "used_bytes": 12 * GB,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        insights = result["insights"]

        assert insights["largest_used_account"][
            "label"
        ] == "big@x.com"
        assert insights["most_free_account"][
            "label"
        ] == "small@x.com"

    def test_insights_absent_without_data(self):
        intel, _, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
            }
        )

        insights = intel.summarize_accounts()[
            "insights"
        ]

        assert insights[
            "largest_used_account"
        ] is None
        assert insights["most_free_account"] is None
