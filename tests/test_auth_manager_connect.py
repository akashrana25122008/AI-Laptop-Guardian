"""Milestone 9 - GoogleAuthManager connect/disconnect flows.

Unit coverage over a fake OAuth provider:

    - explicit connect registers exactly one account and
      relocates the token into its OWN isolated file,
    - reconnecting the same email is idempotent,
    - every failure path cleans temporary state and
      never leaves a half-registered account,
    - disconnect removes ONLY that account's local
      authorization state,
    - no secret ever appears in any returned payload.

No test here performs real OAuth, network access, or
browser interaction.
"""

import json
import os

import pytest

from cloud.accounts import AccountRegistry
from cloud.auth_manager import GoogleAuthManager
from cloud.multi_drive import (
    MultiAccountDriveManager,
)


FAKE_CLIENT_SECRET = (
    '{"installed": {"client_secret": "SUPERSECRET"}}'
)

FORBIDDEN = ["SUPERSECRET", "ya29.", "1//refresh"]


class FakeAuthProvider:
    """
    Configurable stand-in for GoogleDriveProvider during
    an in-progress connection.
    """

    def __init__(
        self,
        identity=None,
        auth_result=True,
        auth_error=None,
        identity_error=None,
        token_path=None,
    ):
        self.identity = identity or {
            "success": True,
            "email": "new@x.com",
            "display_name": "New User",
        }

        self.auth_result = auth_result

        self.auth_error = auth_error

        self.identity_error = identity_error

        # The provider owns its token file location, like
        # the real GoogleDriveProvider.

        self.token_path = token_path

        self.authenticate_calls = 0

    def _handshake_succeeded(self):
        if isinstance(self.auth_result, dict):
            return bool(
                self.auth_result.get("success")
            )

        return bool(self.auth_result)

    def authenticate(self):
        self.authenticate_calls += 1

        if self.auth_error is not None:
            raise RuntimeError(self.auth_error)

        if self._handshake_succeeded():

            # Mirror reality: a successful consent flow
            # persists the token to the bound file.

            if self.token_path is not None:

                with open(
                    self.token_path,
                    "w",
                    encoding="utf-8",
                ) as handle:
                    handle.write(
                        '{"access_token": '
                        '"ya29.SECRET-ACCESS"}'
                    )

        return self.auth_result

    def get_account_identity(self):
        if self.identity_error is not None:
            raise RuntimeError(
                self.identity_error
            )

        return dict(self.identity)


def make_auth(tmp_path, provider_factory):
    """
    Auth manager over an isolated temp token dir with an
    injected pending provider factory.
    """

    drive = MultiAccountDriveManager(
        registry=AccountRegistry(),
        token_dir=str(tmp_path / "tokens"),
    )

    auth = GoogleAuthManager(
        drive_manager=drive,
        credentials_file=str(
            tmp_path / "credentials.json"
        ),
        pending_provider_factory=provider_factory,
    )

    return auth


def write_credentials(tmp_path):
    path = tmp_path / "credentials.json"

    path.write_text(
        FAKE_CLIENT_SECRET,
        encoding="utf-8",
    )

    return path


def pending_files(token_dir):

    return [
        name
        for name in os.listdir(str(token_dir))
        if name.startswith(".pending-")
    ]


def account_token_files(token_dir):

    return [
        name
        for name in os.listdir(str(token_dir))
        if name.endswith(".json")
        and not name.startswith(".pending-")
    ]


def assert_no_secrets(payload):

    text = json.dumps(payload, default=str)

    for forbidden in FORBIDDEN:
        assert forbidden not in text


# =========================================================
# MISSING OAUTH CLIENT CONFIGURATION
# =========================================================


class TestMissingCredentials:

    def test_missing_file_fails_without_state(
        self, tmp_path
    ):

        auth = make_auth(
            tmp_path,
            provider_factory=lambda p: None,
        )

        result = auth.connect_account()

        assert result["success"] is False

        assert (
            result["error_code"]
            == "missing_credentials"
        )

        # The credentials file CONTENTS are never read;
        # only existence is checked.

        assert "SUPERSECRET" not in json.dumps(
            result
        )

        # No registration happened.

        assert (
            auth.drive_manager.registry.count()
            == 0
        )


# =========================================================
# HAPPY PATH
# =========================================================


class TestConnectHappyPath:

    def test_connect_registers_and_relocates_token(
        self, tmp_path
    ):

        write_credentials(tmp_path)

        created = []

        def factory(token_path):
            provider = FakeAuthProvider(token_path=token_path)
            created.append(provider)
            return provider

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert_no_secrets(result)

        assert result["success"] is True

        assert result["created_new"] is True

        assert result["total_accounts"] == 1

        assert (
            result["account"]["email"]
            == "new@x.com"
        )

        account_id = result["account"]["id"]

        # Exactly ONE isolated token file named after
        # the account id; no temporary files remain.

        token_dir = str(auth.token_dir)

        assert account_token_files(token_dir) == [
            f"{account_id}.json"
        ]

        assert pending_files(token_dir) == []

        # OAuth consent ran exactly once.

        assert (
            created[0].authenticate_calls == 1
        )

    def test_reconnect_same_email_is_idempotent(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                token_path=token_path
            )

        auth = make_auth(tmp_path, factory)

        first = auth.connect_account()

        second = auth.connect_account()

        assert first["success"] is True

        assert second["success"] is True

        assert second["created_new"] is False

        assert second["total_accounts"] == 1

        assert second["account"]["id"] == (
            first["account"]["id"]
        )

        token_dir = str(auth.token_dir)

        assert len(account_token_files(token_dir)) == 1

        assert pending_files(token_dir) == []


# =========================================================
# FAILURE PATHS (ALWAYS CLEAN UP)
# =========================================================


class TestConnectFailures:

    def test_authentication_exception_cleans_up(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                auth_error="consent window closed",
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        assert result.get("cancelled") is True

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

        assert pending_files(
            str(auth.token_dir)
        ) == []

    def test_dict_failure_result_is_treated_as_cancel(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                auth_result={"success": False},
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        assert result.get("cancelled") is True

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

        assert pending_files(
            str(auth.token_dir)
        ) == []

    def test_false_result_is_treated_as_cancel(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                auth_result=False,
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        assert result.get("cancelled") is True

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

    def test_identity_without_email_never_registers(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                identity={
                    "success": True,
                    "display_name": "No Email",
                },
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

        assert pending_files(
            str(auth.token_dir)
        ) == []

    def test_identity_exception_reports_sanitized_failure(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        def factory(token_path):
            return FakeAuthProvider(
                identity_error=(
                    "token endpoint said "
                    "SUPERSECRET-value"
                ),
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        assert_no_secrets(result)

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

    def test_storage_failure_rolls_back_new_registration(
        self, tmp_path, monkeypatch
    ):
        import cloud.auth_manager as module

        write_credentials(tmp_path)

        def broken_replace(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(
            module.os,
            "replace",
            broken_replace,
        )

        def factory(token_path):
            return FakeAuthProvider(
                token_path=token_path
            )

        auth = make_auth(tmp_path, factory)

        result = auth.connect_account()

        assert result["success"] is False

        # The new registration must NOT survive without
        # its isolated authorization state.

        assert (
            auth.drive_manager.registry.count()
            == 0
        )

        assert pending_files(
            str(auth.token_dir)
        ) == []


# =========================================================
# DISCONNECT
# =========================================================


class TestDisconnect:

    def _connect_two(self, tmp_path):
        write_credentials(tmp_path)

        emails = iter(
            [
                {
                    "success": True,
                    "email": "a@x.com",
                },
                {
                    "success": True,
                    "email": "b@x.com",
                },
            ]
        )

        def factory(token_path):
            return FakeAuthProvider(
                identity=next(emails),
                token_path=token_path,
            )

        auth = make_auth(tmp_path, factory)

        first = auth.connect_account()

        second = auth.connect_account()

        return auth, first, second

    def test_disconnect_removes_only_that_account(
        self, tmp_path
    ):
        auth, first, second = self._connect_two(
            tmp_path
        )

        token_dir = str(auth.token_dir)

        first_id = first["account"]["id"]

        second_id = second["account"]["id"]

        result = auth.disconnect_account(first_id)

        assert_no_secrets(result)

        assert result["success"] is True

        assert (
            result["local_authorization_removed"]
            is True
        )

        # Only the FIRST account's token file is gone.

        assert account_token_files(token_dir) == [
            f"{second_id}.json"
        ]

        # Registration state matches reality: the record
        # is kept in a DISCONNECTED state (its id can
        # never be silently reassigned), while the other
        # account stays fully connected.

        first_record = (
            auth.drive_manager.registry.get_account(
                first_id
            )
        )

        assert (
            first_record.is_connected() is False
        )

        assert (
            auth.drive_manager.registry.get_account(
                second_id
            ).is_connected()
        )

    def test_disconnect_unknown_account_fails_safely(
        self, tmp_path
    ):
        auth, _, _ = self._connect_two(tmp_path)

        result = auth.disconnect_account(
            "account-999"
        )

        assert result["success"] is False

        assert (
            auth.drive_manager.registry.count() == 2
        )

    def test_cancel_removes_temporary_state_only(
        self, tmp_path
    ):
        write_credentials(tmp_path)

        holder = {}

        def factory(token_path):
            holder["provider"] = FakeAuthProvider(
                token_path=token_path
            )

            return holder["provider"]

        auth = make_auth(tmp_path, factory)

        started = auth.start_authentication()

        assert started["success"] is True

        pending = started["pending"]

        token_dir = str(auth.token_dir)

        assert len(pending_files(token_dir)) == 1

        auth.cancel_authentication(pending)

        assert pending_files(token_dir) == []

        # Cancellation never touches registrations.

        assert (
            auth.drive_manager.registry.count()
            == 0
        )
