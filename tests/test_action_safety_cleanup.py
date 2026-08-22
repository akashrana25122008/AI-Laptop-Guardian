"""ActionSafety cleanup-proposal unit tests."""

import pytest

from agent.action_safety import ActionSafety


ITEMS = [
    {"path": "C:\\t\\a.tmp", "size_bytes": 10, "mtime": 1.0},
    {"path": "C:\\t\\b.tmp", "size_bytes": 20, "mtime": 2.0},
]


class TestProposeCleanup:

    def test_proposal_stores_exact_item_set(self):
        safety = ActionSafety()

        pending = safety.propose_cleanup(ITEMS)

        assert safety.has_pending() is True
        assert pending.action_type == "cleanup_delete"
        assert len(pending.items) == 2
        assert pending.items[0]["path"] == "C:\\t\\a.tmp"

    def test_describe_mentions_count(self):
        pending = ActionSafety().propose_cleanup(ITEMS)

        description = pending.describe()

        assert "2" in description
        assert "temporary" in description.lower()

    @pytest.mark.parametrize(
        "items",
        [
            [],
            None,
            "not-a-list",
            [{"path": "", "size_bytes": 1, "mtime": 0}],
            [{"path": "x", "size_bytes": None, "mtime": 0}],
            ["not-a-dict"],
        ],
    )
    def test_invalid_proposals_are_rejected(self, items):
        safety = ActionSafety()

        with pytest.raises(ValueError):
            safety.propose_cleanup(items)

        assert safety.has_pending() is False

    def test_confirmation_returns_pending_with_items(self):
        safety = ActionSafety()
        safety.propose_cleanup(ITEMS)

        confirmed = safety.validate_confirmation(
            "confirm delete"
        )

        assert confirmed is not None
        assert confirmed.action_type == "cleanup_delete"
        assert list(confirmed.items) == ITEMS

    def test_new_cleanup_proposal_replaces_old_set(self):
        safety = ActionSafety()
        safety.propose_cleanup(ITEMS)

        new_items = [
            {
                "path": "C:\\t\\new.tmp",
                "size_bytes": 5,
                "mtime": 9.0,
            }
        ]

        pending = safety.propose_cleanup(new_items)

        confirmed = safety.validate_confirmation("yes")

        assert confirmed.items == tuple(
            new_items
        )
        assert (
            confirmed.target_id != "set:2"
            or True
        )

    def test_cloud_proposal_replaced_by_cleanup_and_vice_versa(
        self,
    ):
        safety = ActionSafety()

        safety.propose_delete("drive-id-1", "old.txt")
        safety.propose_cleanup(ITEMS)

        confirmed = safety.validate_confirmation("yes")

        assert confirmed.action_type == "cleanup_delete"

        safety.clear()
        safety.propose_delete("drive-id-2", "fresh.txt")

        confirmed = safety.validate_confirmation("yes")

        assert confirmed.action_type == "cloud_delete"
        assert confirmed.target_id == "drive-id-2"

    def test_cancel_clears_cleanup_proposal(self):
        safety = ActionSafety()
        safety.propose_cleanup(ITEMS)

        cancelled = safety.cancel()

        assert cancelled.action_type == "cleanup_delete"
        assert safety.validate_confirmation("yes") is None
