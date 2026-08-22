"""Milestone 9 - token isolation and lazy-session rules.

Invariants under test:

    - every account owns EXACTLY ONE token file named
      <account_id>.json inside the shared token dir,
    - an in-progress connection lives ONLY in a hidden
      .pending-* temp file and never touches existing
      accounts' files,
    - completing a connection never materializes a
      cached provider session (lazy reload preserved),
    - disconnecting one account never mutates another
      account's registration, token, or cached session.
"""

import os

from cloud.accounts import AccountRegistry
from cloud.auth_manager import GoogleAuthManager
from cloud.multi_drive import (
    MultiAccountDriveManager,
)


class FakeAuthProvider:
    """Minimal fake for the connect handshake."""

    def __init__(self, identity, token_path=None):
        self.identity = identity

        self.token_path = token_path

    def authenticate(self):
        # Mirror reality: successful consent persists the
        # token into the provider's bound file.

        if self.token_path is not None:

            with open(
                self.token_path,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    '{"refresh_token": '
                    '"1//REFRESH-TOKEN"}'
                )

        return {"success": True}

    def get_account_identity(self):
        return dict(self.identity)


def make_auth(tmp_path):

    drive = MultiAccountDriveManager(
        registry=AccountRegistry(),
        token_dir=str(tmp_path / "tokens"),
        # Any accidental session build must explode
        # loudly: this suite proves sessions stay LAZY.
        provider_factory=_forbidden_factory,
    )

    identities = iter(
        [
            {"success": True, "email": "a@x.com"},
            {"success": True, "email": "b@x.com"},
        ]
    )

    def pending_factory(token_path):
        return FakeAuthProvider(
            next(identities),
            token_path=token_path,
        )

    auth = GoogleAuthManager(
        drive_manager=drive,
        credentials_file=str(
            tmp_path / "credentials.json"
        ),
        pending_provider_factory=pending_factory,
    )

    (tmp_path / "credentials.json").write_text(
        "{}",
        encoding="utf-8",
    )

    return auth


def _forbidden_factory(account):
    raise AssertionError(
        "provider session was built during account "
        "management; sessions must stay lazy"
    )


def regular_tokens(token_dir):

    return sorted(
        name
        for name in os.listdir(str(token_dir))
        if name.endswith(".json")
        and not name.startswith(".pending-")
    )


# =========================================================
# ISOLATION DURING AND AFTER CONNECT
# =========================================================


class TestTokenIsolation:

    def test_pending_connection_touches_no_existing_token(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        first = auth.connect_account()

        first_id = first["account"]["id"]

        token_dir = str(auth.token_dir)

        assert regular_tokens(token_dir) == [
            f"{first_id}.json"
        ]

        started = auth.start_authentication()

        assert started["success"] is True

        # Mid-flow state: exactly one HIDDEN pending file;
        # no second regular token exists yet.

        pending = [
            name
            for name in os.listdir(token_dir)
            if name.startswith(".pending-")
        ]

        assert len(pending) == 1

        assert regular_tokens(token_dir) == [
            f"{first_id}.json"
        ]

        completed = auth.complete_authentication(
            started["pending"]
        )

        assert completed["success"] is True

        assert len(regular_tokens(token_dir)) == 2

    def test_complete_never_builds_a_cached_session(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        result = auth.connect_account()

        account_id = result["account"]["id"]

        # The forbidden factory would have raised if any
        # session had been created.

        assert (
            account_id
            not in auth.drive_manager._sessions
        )

    def test_each_account_owns_exactly_one_file(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        first = auth.connect_account()

        second = auth.connect_account()

        first_id = first["account"]["id"]

        second_id = second["account"]["id"]

        assert first_id != second_id

        token_dir = str(auth.token_dir)

        assert regular_tokens(token_dir) == [
            f"{first_id}.json",
            f"{second_id}.json",
        ]


# =========================================================
# DISCONNECT SCOPING
# =========================================================


class TestDisconnectScoping:

    def test_disconnect_never_touches_other_accounts(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        first = auth.connect_account()

        second = auth.connect_account()

        first_id = first["account"]["id"]

        second_id = second["account"]["id"]

        result = auth.disconnect_account(second_id)

        assert result["success"] is True

        token_dir = str(auth.token_dir)

        assert regular_tokens(token_dir) == [
            f"{first_id}.json"
        ]

        status = auth.get_auth_status()

        listed = [
            entry["id"]
            for entry in status["accounts"]
        ]

        assert listed == [first_id]

    def test_disconnect_twice_fails_safely(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        result = auth.connect_account()

        account_id = result["account"]["id"]

        assert auth.disconnect_account(
            account_id
        )["success"] is True

        again = auth.disconnect_account(account_id)

        assert again["success"] is False
