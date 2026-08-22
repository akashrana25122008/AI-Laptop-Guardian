"""
Deterministic action safety layer.

Natural-language intent must never directly authorize a
destructive mutation. This module holds small, explicit,
deterministic state for actions that require confirmation:

    User request
        -> Planner / intent
        -> THIS safety layer
        -> explicit confirmation
        -> ToolRouter
        -> Tool

No AI model is involved in any safety decision here.
"""

# =========================================================
# CONFIRMATION / CANCELLATION PHRASES
# =========================================================
#
# Only exact matches (after normalization) count.
# Unrelated messages are NEVER treated as confirmation.

CONFIRMATION_PHRASES = {
    "yes",
    "y",
    "yes please",
    "confirm",
    "confirmed",
    "confirm delete",
    "confirm deletion",
    "yes delete",
    "yes delete it",
}

CANCELLATION_PHRASES = {
    "no",
    "n",
    "no thanks",
    "cancel",
    "cancelled",
    "canceled",
    "stop",
    "stop it",
    "do not delete",
    "dont delete",
    "don't delete",
}


def normalize_phrase(message):
    """
    Normalize a message for deterministic phrase matching.
    """

    return " ".join(
        str(message)
        .lower()
        .strip()
        .replace("!", "")
        .replace(".", "")
        .replace(",", "")
        .replace("?", "")
        .split()
    )


def is_confirmation(message):
    """True only for an exact, explicit confirmation phrase."""

    return normalize_phrase(message) in CONFIRMATION_PHRASES


def is_cancellation(message):
    """True only for an exact, explicit cancellation phrase."""

    return normalize_phrase(message) in CANCELLATION_PHRASES


# =========================================================
# PENDING ACTION
# =========================================================


class PendingAction:
    """
    One proposed destructive action awaiting confirmation.

    The confirmation is bound to the exact target recorded
    here; it can never authorize a different file or action.
    """

    def __init__(self, action_type, target_id, target_name):
        self.action_type = str(action_type)
        self.target_id = str(target_id)
        self.target_name = str(target_name)

    def describe(self):
        """Human-readable description of the proposed action."""

        if self.action_type == "cloud_delete":
            return (
                f"Permanently delete '{self.target_name}' "
                f"from Google Drive"
            )

        return (
            f"{self.action_type} on "
            f"'{self.target_name}'"
        )


# =========================================================
# SAFETY MANAGER
# =========================================================


class ActionSafety:
    """
    Holds at most one pending destructive action.

    Rules:

        - A new proposal replaces any previous pending one.
        - Confirmation only matches the stored target.
        - Completion, cancellation, or an unrelated message
          invalidates the pending action.
    """

    def __init__(self):
        self._pending = None

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    def has_pending(self):
        """True when a destructive action awaits confirmation."""

        return self._pending is not None

    def get_pending(self):
        """Return the pending action, or None."""

        return self._pending

    # -----------------------------------------------------
    # PROPOSE
    # -----------------------------------------------------

    def propose_delete(self, target_id, target_name):
        """
        Propose a Google Drive deletion.

        Does NOT perform any deletion itself.
        """

        if not target_id or not str(target_id).strip():
            raise ValueError(
                "A pending delete requires a target id."
            )

        self._pending = PendingAction(
            "cloud_delete",
            target_id,
            target_name,
        )

        return self._pending

    # -----------------------------------------------------
    # RESOLVE
    # -----------------------------------------------------

    def validate_confirmation(self, message):
        """
        Return the pending action when the message is an
        explicit confirmation of the stored target,
        otherwise None.
        """

        if self._pending is None:
            return None

        if is_confirmation(message):
            return self._pending

        return None

    def cancel(self):
        """
        Cancel and invalidate any pending action.
        Returns the cancelled action, or None.
        """

        pending = self._pending
        self._pending = None
        return pending

    def clear(self):
        """
        Invalidate the pending action after completion,
        failure, or expiry.
        """

        self._pending = None
