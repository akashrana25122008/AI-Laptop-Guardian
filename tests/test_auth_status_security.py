"""Milestone 9 - auth status is offline and secret-free.

Hard assertions:

    - listing accounts NEVER builds a provider session,
      NEVER touches the network, NEVER authenticates,
    - a registered account whose token file is missing
      is reported honestly as 'authentication
      unavailable' (never silently re-authenticated),
    - status payloads contain safe metadata ONLY; token
      file contents can never leak into them,
    - the ToolRouter exposes the same guarantees.
"""

import json
import os
import sys
import types


def _install_cloud_stub() -> None:
    """Import tool_router without Google dependencies."""

    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        def __init__(self, *args, **kwargs):
            self.service = None
            self.credentials = None

    module.GoogleDriveProvider = (
        StubGoogleDriveProvider
    )

    sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

from agent.tool_router import ToolRouter  # noqa: E402

from cloud.accounts import AccountRegistry
from cloud.auth_manager import GoogleAuthManager
from cloud.multi_drive import (
    MultiAccountDriveManager,
)


SECRET_MARKERS = [
    "ya29.SECRET-ACCESS",
    "1//REFRESH-TOKEN",
]


class ExplodingFactory:
    """
    Any session construction during status listing must
    fail the test loudly.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, account):
        self.calls.append(account.id)
        raise AssertionError(
            "provider factory was invoked by an "
            "offline operation"
        )


def make_auth(tmp_path):
    drive = MultiAccountDriveManager(
        registry=AccountRegistry(),
        token_dir=str(tmp_path / "tokens"),
        provider_factory=ExplodingFactory(),
    )

    auth = GoogleAuthManager(
        drive_manager=drive,
        credentials_file=str(
            tmp_path / "credentials.json"
        ),
    )

    return auth


def register_account(auth, email):
    account = auth.drive_manager.connect_account(
        provider="google_drive",
        email=email,
        display_name=None,
    )

    return account


def write_token_file(auth, account_id, content):
    path = os.path.join(
        str(auth.drive_manager.token_dir),
        f"{account_id}.json",
    )

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True,
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)

    return path


# =========================================================
# OFFLINE GUARANTEES
# =========================================================


class TestOfflineStatus:

    def test_empty_registry_lists_nothing(self, tmp_path):
        auth = make_auth(tmp_path)

        status = auth.get_auth_status()

        assert status["success"] is True

        assert status["tool"] == "cloud_accounts"

        assert status["accounts"] == []

    def test_listing_never_builds_sessions(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        first = register_account(auth, "a@x.com")

        second = register_account(auth, "b@x.com")

        for account_id in (first.id, second.id):

            write_token_file(
                auth,
                account_id,
                SECRET_MARKERS[0],
            )

        factory = (
            auth.drive_manager._provider_factory
        )

        status = auth.get_auth_status()

        assert status["success"] is True

        assert len(status["accounts"]) == 2

        assert factory.calls == []


# =========================================================
# HONEST STATE REPORTING
# =========================================================


class TestHonestStatus:

    def test_missing_token_reported_unavailable(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        account = register_account(auth, "a@x.com")

        # No token file written at all.

        status = auth.get_auth_status()

        entry = status["accounts"][0]

        assert entry["id"] == account.id

        assert (
            entry["status"]
            == "authentication unavailable"
        )

    def test_restored_token_reports_connected(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        account = register_account(auth, "a@x.com")

        write_token_file(auth, account.id, "{}")

        status = auth.get_auth_status()

        assert (
            status["accounts"][0]["status"]
            == "connected"
        )


# =========================================================
# PAYLOAD SHAPE AND SECRET HYGIENE
# =========================================================


class TestStatusPayloadHygiene:

    def test_payload_contains_safe_keys_only(
        self, tmp_path
    ):
        auth = make_auth(tmp_path)

        first = register_account(auth, "a@x.com")

        second = register_account(auth, "b@x.com")

        write_token_file(
            auth,
            first.id,
            json.dumps({"access": SECRET_MARKERS[0]}),
        )

        write_token_file(
            auth,
            second.id,
            json.dumps({"refresh": SECRET_MARKERS[1]}),
        )

        status = auth.get_auth_status()

        assert set(status.keys()) <= {
            "success",
            "tool",
            "accounts",
        }

        allowed_entry_keys = {
            "id",
            "label",
            "email",
            "provider",
            "status",
        }

        for entry in status["accounts"]:

            assert set(entry.keys()) <= (
                allowed_entry_keys
            )

        # Token file contents can never leak.

        text = json.dumps(status)

        for marker in SECRET_MARKERS:
            assert marker not in text

    def test_router_accounts_tool_is_normalized(
        self, tmp_path
    ):
        router = ToolRouter()

        router.drive_manager = (
            MultiAccountDriveManager(
                registry=AccountRegistry(),
                token_dir=str(tmp_path / "tokens"),
                provider_factory=ExplodingFactory(),
            )
        )

        result = router.execute("cloud_accounts")

        assert result["success"] is True

        assert result["tool"] == "cloud_accounts"

        assert result["accounts"] == []
