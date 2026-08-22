"""Unit tests for the deterministic action safety layer."""

import pytest

from agent.action_safety import (
    ActionSafety,
    PendingAction,
    is_cancellation,
    is_confirmation,
    normalize_phrase,
)


# =========================================================
# PHRASE CLASSIFICATION
# =========================================================


class TestPhraseClassification:

    @pytest.mark.parametrize(
        "message",
        [
            "yes",
            "Yes",
            "  YES  ",
            "y",
            "confirm",
            "Confirm!",
            "CONFIRM DELETE",
            "confirmed.",
            "yes delete it",
        ],
    )
    def test_explicit_confirmations(self, message):
        assert is_confirmation(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "no",
            "No!",
            "cancel",
            "CANCEL.",
            "stop",
            "do not delete",
            "no thanks",
        ],
    )
    def test_explicit_cancellations(self, message):
        assert is_cancellation(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "yes please delete everything else too",
            "ok",
            "sure",
            "go ahead",
            "delete it",
            "why not",
            "yeah whatever you want",
            "",
            "maybe",
        ],
    )
    def test_unrelated_messages_never_confirm(self, message):
        assert is_confirmation(message) is False

    @pytest.mark.parametrize(
        "message",
        [
            "stop the music",
            "cancel my subscription",
            "no way that can be right, explain",
        ],
    )
    def test_phrases_must_match_exactly(self, message):
        # Multi-word sentences containing cancel-words are
        # NOT cancellations; only exact phrases are.
        assert is_cancellation(message) is False

    def test_normalize_collapses_whitespace_and_punctuation(
        self,
    ):
        assert (
            normalize_phrase("  Confirm   Delete!?  ")
            == "confirm delete"
        )


# =========================================================
# PENDING ACTION LIFECYCLE
# =========================================================


class TestPendingActionLifecycle:

    def test_no_pending_initially(self):
        safety = ActionSafety()

        assert safety.has_pending() is False
        assert safety.get_pending() is None

    def test_propose_creates_bound_pending_delete(self):
        safety = ActionSafety()

        pending = safety.propose_delete("id-123", "a.txt")

        assert safety.has_pending() is True
        assert pending.action_type == "cloud_delete"
        assert pending.target_id == "id-123"
        assert pending.target_name == "a.txt"

    def test_propose_requires_target_id(self):
        safety = ActionSafety()

        with pytest.raises(ValueError):
            safety.propose_delete("  ", "a.txt")

        assert safety.has_pending() is False

    def test_confirmation_returns_only_exact_target(self):
        safety = ActionSafety()
        safety.propose_delete("id-123", "a.txt")

        confirmed = safety.validate_confirmation(
            "confirm delete"
        )

        assert confirmed is not None
        assert confirmed.target_id == "id-123"

    def test_unrelated_message_is_not_a_confirmation(self):
        safety = ActionSafety()
        safety.propose_delete("id-123", "a.txt")

        assert safety.validate_confirmation("ok sure") is None
        # The pending action remains until explicitly
        # cancelled, expired, or used.
        assert safety.has_pending() is True

    def test_cancel_invalidates_pending_action(self):
        safety = ActionSafety()
        safety.propose_delete("id-123", "a.txt")

        cancelled = safety.cancel()

        assert cancelled.target_id == "id-123"
        assert safety.has_pending() is False
        assert safety.validate_confirmation("yes") is None

    def test_clear_invalidates_after_use(self):
        safety = ActionSafety()
        safety.propose_delete("id-123", "a.txt")
        safety.clear()

        assert safety.has_pending() is False

    def test_new_proposal_replaces_previous_target(self):
        safety = ActionSafety()
        safety.propose_delete("id-1", "one.txt")
        safety.propose_delete("id-2", "two.txt")

        confirmed = safety.validate_confirmation("yes")

        # Only the most recent proposal can ever be confirmed.
        assert confirmed.target_id == "id-2"
        assert confirmed.target_name == "two.txt"

    def test_describe_mentions_destructive_intent(self):
        action = PendingAction("cloud_delete", "x", "a.txt")

        description = action.describe()

        assert "delete" in description.lower()
        assert "a.txt" in description
