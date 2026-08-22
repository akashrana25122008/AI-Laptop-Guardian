"""Milestone 7 - CloudAccount and AccountRegistry.

Pure metadata registry tests. No network, no OAuth,
no Google libraries, no secrets anywhere.
"""

import json

import pytest

from cloud.accounts import AccountRegistry
from cloud.accounts import CloudAccount


# =========================================================
# CLOUD ACCOUNT RECORD
# =========================================================


class TestCloudAccount:

    def test_safe_metadata_fields(self):
        account = CloudAccount(
            account_id="account-1",
            provider="google_drive",
            email="user@example.com",
            display_name="Work",
        )

        data = account.to_dict()

        assert data["id"] == "account-1"
        assert data["provider"] == "google_drive"
        assert data["email"] == "user@example.com"
        assert data["name"] == "Work"
        assert data["status"] == "connected"

    def test_token_ref_is_reference_not_content(self):
        account = CloudAccount(
            account_id="account-2",
            provider="google_drive",
        )

        # The default reference points at an isolated
        # token file; it must never contain token data.

        assert account.token_ref == (
            "tokens/account-2.json"
        )

        assert "secret" not in account.to_dict()
        assert "token" not in str(
            {k: v for k, v in account.to_dict().items()
             if k != "token_ref"}
        )

    def test_safe_label_prefers_email(self):
        labeled = CloudAccount(
            account_id="account-1",
            provider="google_drive",
            email="a@x.com",
        )

        anonymous = CloudAccount(
            account_id="account-2",
            provider="google_drive",
        )

        assert labeled.safe_label() == "a@x.com"
        assert anonymous.safe_label() == "account-2"

    def test_roundtrip_from_dict(self):
        original = CloudAccount(
            account_id="account-7",
            provider="google_drive",
            email="z@x.com",
            display_name="Personal",
            status="connected",
            token_ref="tokens/account-7.json",
        )

        copy = CloudAccount.from_dict(
            original.to_dict()
        )

        assert copy.id == original.id
        assert copy.email == original.email
        assert copy.token_ref == original.token_ref
        assert copy.is_connected() is True


# =========================================================
# REGISTRY BASICS
# =========================================================


class TestRegistryBasics:

    def test_add_assigns_sequential_ids(self):
        registry = AccountRegistry()

        first = registry.add_account(
            "google_drive", "a@x.com"
        )
        second = registry.add_account(
            "google_drive", "b@x.com"
        )

        assert first.id == "account-1"
        assert second.id == "account-2"

    def test_readd_same_provider_email_is_idempotent(self):
        registry = AccountRegistry()

        first = registry.add_account(
            "google_drive", "a@x.com"
        )
        again = registry.add_account(
            "google_drive", "a@x.com"
        )

        assert again.id == first.id
        assert registry.count() == 1

    def test_same_email_different_provider_is_new(self):
        registry = AccountRegistry()

        drive = registry.add_account(
            "google_drive", "a@x.com"
        )
        other = registry.add_account(
            "dropbox", "a@x.com"
        )

        assert other.id != drive.id
        assert registry.count() == 2

    def test_empty_provider_rejected(self):
        registry = AccountRegistry()

        with pytest.raises(ValueError):
            registry.add_account("   ")

    def test_count_and_listing_are_ordered(self):
        registry = AccountRegistry()

        registry.add_account("google_drive", "b@x.com")
        registry.add_account("google_drive", "a@x.com")

        accounts = registry.list_accounts()

        assert [a.id for a in accounts] == [
            "account-1",
            "account-2",
        ]
        assert registry.count() == 2


# =========================================================
# DISCONNECTION SEMANTICS
# =========================================================


class TestDisconnection:

    def test_remove_marks_disconnected(self):
        registry = AccountRegistry()
        account = registry.add_account(
            "google_drive", "a@x.com"
        )

        removed = registry.remove_account(account.id)

        assert removed.status == "disconnected"
        assert account.is_connected() is False
        assert registry.count() == 0

    def test_removed_id_is_never_reused(self):
        registry = AccountRegistry()
        first = registry.add_account(
            "google_drive", "a@x.com"
        )
        registry.remove_account(first.id)

        replacement = registry.add_account(
            "google_drive", "b@x.com"
        )

        assert replacement.id == "account-2"

    def test_disconnected_accounts_stay_resolvable_by_id(
        self,
    ):
        registry = AccountRegistry()
        account = registry.add_account(
            "google_drive", "a@x.com"
        )
        registry.remove_account(account.id)

        fetched = registry.get_account(account.id)

        assert fetched is not None
        assert fetched.is_connected() is False

    def test_unknown_remove_returns_none(self):
        registry = AccountRegistry()

        assert registry.remove_account(
            "account-99"
        ) is None


# =========================================================
# SELECTION RESOLUTION
# =========================================================


class TestSelectorResolution:

    def _registry(self):
        registry = AccountRegistry()
        registry.add_account("google_drive", "one@x.com")
        registry.add_account("google_drive", "two@x.com")
        return registry

    def test_resolve_by_number_string(self):
        registry = self._registry()

        assert registry.resolve_selector(
            "2"
        ).email == "two@x.com"

    def test_resolve_by_int_position(self):
        registry = self._registry()

        assert registry.resolve_selector(
            1
        ).email == "one@x.com"

    def test_resolve_by_internal_id(self):
        registry = self._registry()

        assert registry.resolve_selector(
            "account-2"
        ).id == "account-2"

    def test_resolve_by_email(self):
        registry = self._registry()

        assert registry.resolve_selector(
            "TWO@x.com"
        ).email == "two@x.com"

    def test_hash_prefix_number(self):
        registry = self._registry()

        assert registry.resolve_selector(
            "#1"
        ).email == "one@x.com"

    def test_out_of_range_returns_none(self):
        registry = self._registry()

        assert registry.resolve_selector("9") is None
        assert registry.resolve_selector("0") is None

    def test_unknown_text_returns_none(self):
        registry = self._registry()

        assert (
            registry.resolve_selector("nonsense") is None
        )

    def test_positional_resolution_skips_disconnected(self):
        registry = AccountRegistry()
        registry.add_account("google_drive", "one@x.com")
        second = registry.add_account(
            "google_drive", "two@x.com"
        )
        registry.remove_account(second.id)
        registry.add_account("google_drive", "three@x.com")

        # Only one connected account remains.

        resolved = registry.resolve_selector("1")

        assert resolved.email == "one@x.com"


# =========================================================
# OPTIONAL PERSISTENCE (SAFE METADATA ONLY)
# =========================================================


class TestPersistence:

    def test_roundtrip_through_json_file(self, tmp_path):
        path = tmp_path / "accounts.json"

        first = AccountRegistry(persist_path=str(path))
        first.add_account(
            "google_drive",
            "keep@x.com",
            display_name="Kept",
        )

        reloaded = AccountRegistry(
            persist_path=str(path)
        )

        accounts = reloaded.list_accounts()

        assert len(accounts) == 1
        assert accounts[0].email == "keep@x.com"
        assert accounts[0].display_name == "Kept"

        fresh = reloaded.add_account(
            "google_drive", "new@x.com"
        )

        # Id numbering continues after reload.

        assert fresh.id == "account-2"

    def test_persisted_file_contains_no_secret_keys(
        self,
        tmp_path,
    ):
        path = tmp_path / "accounts.json"

        registry = AccountRegistry(
            persist_path=str(path)
        )
        registry.add_account(
            "google_drive", "a@x.com"
        )

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        serialized = json.dumps(payload).lower()

        for forbidden in (
            "refresh_token",
            "client_secret",
            "access_token",
            "password",
        ):

            assert forbidden not in serialized

    def test_corrupt_state_starts_fresh(self, tmp_path):
        path = tmp_path / "accounts.json"
        path.write_text("{ not json", encoding="utf-8")

        registry = AccountRegistry(
            persist_path=str(path)
        )

        assert registry.count() == 0

        added = registry.add_account(
            "google_drive", "fresh@x.com"
        )

        assert added.id == "account-1"

    def test_missing_file_starts_fresh(self, tmp_path):
        registry = AccountRegistry(
            persist_path=str(
                tmp_path / "does_not_exist.json"
            )
        )

        assert registry.count() == 0
