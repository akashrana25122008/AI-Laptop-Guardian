"""Milestone 8 - Deterministic storage insights.

Insights compare ONLY accounts that actually reported
the relevant value; unknown or failed accounts are never
ranked and never guessed into a winner.
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

    def authenticate(self):
        return {"success": True}

    def get_storage_info(self):
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
    )


class TestAccountInsights:

    def test_largest_use_and_most_free_identified(self):
        intel, _ = make_intelligence(
            {
                "a@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 2 * GB,
                },
                "b@x.com": {
                    "success": True,
                    "total_bytes": 15 * GB,
                    "used_bytes": 12 * GB,
                },
            }
        )

        insights = intel.summarize_accounts(
            scope_all=True
        )[
            "insights"
        ]

        assert insights["largest_used_account"] == {
            "account_id": "account-2",
            "label": "b@x.com",
            "used_bytes": 12 * GB,
        }
        assert insights["most_free_account"] == {
            "account_id": "account-1",
            "label": "a@x.com",
            "free_bytes": 8 * GB,
        }

    def test_most_free_is_about_free_space_not_small_usage(self):
        """
        An account can use the MOST space and still have
        the MOST free space.
        """

        intel, _ = make_intelligence(
            {
                "huge@x.com": {
                    "success": True,
                    "total_bytes": 100 * GB,
                    "used_bytes": 90 * GB,
                },
                "tiny@x.com": {
                    "success": True,
                    "total_bytes": 15 * GB,
                    "used_bytes": 8 * GB,
                },
            }
        )

        insights = (
            intel.summarize_accounts(
                scope_all=True
            )[
                "insights"
            ]
        )

        assert insights[
            "largest_used_account"
        ]["label"] == "huge@x.com"
        assert insights["most_free_account"][
            "label"
        ] == "huge@x.com"

    def test_failed_account_never_wins_a_comparison(self):
        intel, _ = make_intelligence(
            {
                "a@x.com": RuntimeError("dead"),
                "b@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 9 * GB,
                },
            }
        )

        result = intel.summarize_accounts(
            scope_all=True
        )

        assert result["success"] is True

        insights = result["insights"]

        assert insights["largest_used_account"][
            "label"
        ] == "b@x.com"
        assert insights["most_free_account"][
            "label"
        ] == "b@x.com"

    def test_unknown_values_are_never_ranked(self):
        """
        An available entry without usable values must not
        become an insight winner just for existing.
        """

        intel, _ = make_intelligence(
            {
                "mystery@x.com": {
                    "success": True,
                    "total_bytes": None,
                    "used_bytes": None,
                },
                "known@x.com": {
                    "success": True,
                    "total_bytes": 5 * GB,
                    "used_bytes": 1 * GB,
                },
            }
        )

        insights = intel.summarize_accounts(
            scope_all=True
        )[
            "insights"
        ]

        assert insights[
            "largest_used_account"
        ]["label"] == "known@x.com"
        assert insights["most_free_account"][
            "label"
        ] == "known@x.com"

    def test_no_data_means_no_insights(self):
        intel, _ = make_intelligence(
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
        )[
            "insights"
        ]

        assert result["largest_used_account"] is None
        assert result["most_free_account"] is None

    def test_ties_resolve_deterministically(self):
        intel, _ = make_intelligence(
            {
                "first@x.com": {
                    "success": True,
                    "total_bytes": 10 * GB,
                    "used_bytes": 5 * GB,
                },
                "second@x.com": {
                    "success": True,
                    "total_bytes": 20 * GB,
                    "used_bytes": 5 * GB,
                },
            }
        )

        insights = intel.summarize_accounts(
            scope_all=True
        )[
            "insights"
        ]

        # Equal usage: first connected account wins,
        # deterministically.

        assert insights[
            "largest_used_account"
        ]["label"] == "first@x.com"

        # Free space differs and decides on its own.

        assert insights["most_free_account"][
            "label"
        ] == "second@x.com"
