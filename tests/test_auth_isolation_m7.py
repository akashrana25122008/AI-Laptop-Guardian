"""Milestone 7 - Per-account authentication isolation.

Proves that:

    - every account gets its OWN provider instance with
      its own token file path,
    - constructing sessions and registering accounts
      never authenticates (lazy auth preserved),
    - one account's authentication never leaks into
      another account's session.

Google Drive is fully stubbed; no network is touched.
The stub is activated per-test so this file is immune
to stub ordering across the wider suite.
"""

import os
import sys
import types

import pytest

from cloud.accounts import AccountRegistry
from cloud.multi_drive import (
    MultiAccountDriveManager,
)


def _activate_recording_stub(monkeypatch):
    """
    Install a fresh Google Drive stub for exactly one
    test and restore any previous entry afterwards.
    """

    module = types.ModuleType("cloud.google_drive")

    class RecordingProvider:
        instances = []

        def __init__(self, *args, **kwargs):
            self.token_file = kwargs.get("token_file")
            self.service = None
            self.credentials = None

            RecordingProvider.instances.append(self)

        def authenticate(self):
            self.service = object()
            return {"success": True}

    module.GoogleDriveProvider = RecordingProvider

    monkeypatch.setitem(
        sys.modules,
        "cloud.google_drive",
        module,
    )

    return RecordingProvider


def make_manager(token_dir):
    registry = AccountRegistry()

    return MultiAccountDriveManager(
        registry=registry,
        token_dir=str(token_dir),
    )


# =========================================================
# TOKEN FILE ISOLATION
# =========================================================


class TestTokenIsolation:

    def test_each_account_gets_its_own_token_path(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        manager.connect_account(
            "google_drive", "a@x.com"
        )
        manager.connect_account(
            "google_drive", "b@x.com"
        )

        session_a = manager.get_session("account-1")
        session_b = manager.get_session("account-2")

        assert session_a.token_file == os.path.join(
            str(tmp_path),
            "account-1.json",
        )
        assert session_b.token_file == os.path.join(
            str(tmp_path),
            "account-2.json",
        )
        assert (
            session_a.token_file != session_b.token_file
        )

    def test_sessions_are_isolated_instances(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        manager.connect_account(
            "google_drive", "a@x.com"
        )
        manager.connect_account(
            "google_drive", "b@x.com"
        )

        session_a = manager.get_session("account-1")
        session_b = manager.get_session("account-2")

        assert session_a is not session_b

    def test_sessions_are_cached_per_account(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        manager.connect_account(
            "google_drive", "a@x.com"
        )

        first = manager.get_session("account-1")
        second = manager.get_session("account-1")

        assert first is second


# =========================================================
# LAZY AUTHENTICATION PRESERVED
# =========================================================


class TestLazyAuthentication:

    def test_registration_never_constructs_sessions(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)
        manager.connect_account(
            "google_drive", "a@x.com"
        )

        # No session was built just by connecting.

        assert manager._sessions == {}

    def test_get_session_does_not_authenticate(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        manager.connect_account(
            "google_drive", "a@x.com"
        )

        session = manager.get_session("account-1")

        # Lazy-auth contract from Milestone 5: the
        # service stays None until authenticate().

        assert session.service is None


# =========================================================
# NO CROSS-ACCOUNT AUTH LEAKAGE
# =========================================================


class TestNoCrossAccountLeakage:

    def test_authenticating_one_account_leaves_other_alone(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        manager.connect_account(
            "google_drive", "a@x.com"
        )
        manager.connect_account(
            "google_drive", "b@x.com"
        )

        session_a = manager.get_session("account-1")
        session_b = manager.get_session("account-2")

        result = manager.authenticate_account(
            "account-1"
        )

        assert result["success"] is True

        assert session_a.service is not None
        assert session_b.service is None

    def test_disconnect_clears_cached_session(
        self,
        tmp_path,
        monkeypatch,
    ):
        recording = _activate_recording_stub(
            monkeypatch
        )
        recording.instances = []

        manager = make_manager(tmp_path)

        account = manager.connect_account(
            "google_drive", "a@x.com"
        )

        original = manager.get_session(account.id)

        manager.disconnect_account(account.id)

        # After disconnection the session must be gone.

        assert (
            manager.get_session(account.id) is None
        )

        # Reconnecting the same email reactivates the
        # SAME registry record but builds a FRESH
        # provider instance.

        manager.connect_account(
            "google_drive", "a@x.com"
        )

        rebuilt = manager.get_session(account.id)

        assert rebuilt is not original

        # Exactly two providers were ever constructed.

        assert len(recording.instances) == 2

    def test_unknown_account_has_no_session(
        self,
        tmp_path,
        monkeypatch,
    ):
        _activate_recording_stub(monkeypatch)

        manager = make_manager(tmp_path)

        assert (
            manager.get_session("account-99") is None
        )
