"""
Multi-account cloud account registry.

This module stores ONLY safe, non-secret account
metadata:

    - internal account id        ("account-1", ...)
    - provider name              ("google_drive")
    - display email (if safely available)
    - display name (if safely available)
    - connection status          ("connected"/"disconnected")
    - a REFERENCE to the token storage location

OAuth tokens, passwords and client secrets are NEVER
stored in this registry. Token contents live only inside
the isolated token files referenced by `token_ref`.
"""

import json
import os


class CloudAccount:
    """
    One authorized cloud account (safe metadata only).
    """

    def __init__(
        self,
        account_id,
        provider,
        email=None,
        display_name=None,
        status="connected",
        token_ref=None,
    ):
        self.id = str(account_id)
        self.provider = str(provider)
        self.email = email
        self.display_name = display_name
        self.status = str(status)

        # Reference string only. Never token contents.
        self.token_ref = (
            str(token_ref)
            if token_ref
            else f"tokens/{self.id}.json"
        )

    def is_connected(self):
        return self.status == "connected"

    def safe_label(self):
        """
        Deterministic user-facing label.

        Prefers the email when available; falls back to
        the internal id so no secret ever needs to be
        displayed.
        """

        if self.email:
            return self.email

        return self.id

    def to_dict(self):
        return {
            "id": self.id,
            "provider": self.provider,
            "email": self.email,
            "name": self.display_name,
            "status": self.status,
            "token_ref": self.token_ref,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            account_id=data["id"],
            provider=data["provider"],
            email=data.get("email"),
            display_name=data.get("name"),
            status=data.get("status", "connected"),
            token_ref=data.get("token_ref"),
        )


class AccountRegistry:
    """
    Deterministic local registry of connected accounts.

    - Account ids are sequential ("account-1",
      "account-2", ...) per registry instance.
    - Re-adding an account with the same provider + email
      returns the existing record (idempotent).
    - Removing an account marks it disconnected AND drops
      it from the active list; the id is never reused for
      a different account.

    Optional JSON persistence can be enabled by providing
    `persist_path`. The persisted file contains ONLY safe
    metadata (no tokens, no secrets).
    """

    def __init__(self, persist_path=None):
        self.persist_path = persist_path

        self._accounts = {}

        self._next_number = 1

        if persist_path:
            self._load()

    # =====================================================
    # PERSISTENCE (SAFE METADATA ONLY)
    # =====================================================

    def _load(self):
        try:
            with open(
                self.persist_path,
                "r",
                encoding="utf-8",
            ) as handle:
                data = json.load(handle)

            for entry in data.get("accounts", []):

                account = CloudAccount.from_dict(
                    entry
                )

                self._accounts[account.id] = (
                    account
                )

            numbers = [
                int(a.id.rsplit("-", 1)[-1])
                for a in self._accounts.values()
                if a.id.startswith("account-")
                and a.id.rsplit("-", 1)[-1].isdigit()
            ]

            if numbers:
                self._next_number = max(numbers) + 1

        except (
            FileNotFoundError,
            OSError,
            ValueError,
        ):
            # Missing or unreadable state starts fresh;
            # never crash the agent on state problems.
            pass

    def _save(self):
        if not self.persist_path:
            return

        directory = os.path.dirname(
            self.persist_path
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True,
            )

        payload = {
            "accounts": [
                account.to_dict()
                for account in self._accounts.values()
            ]
        }

        with open(
            self.persist_path,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                indent=2,
            )

    # =====================================================
    # QUERIES
    # =====================================================

    def list_accounts(self, connected_only=True):
        """Deterministic ordered account list."""

        accounts = sorted(
            self._accounts.values(),
            key=lambda a: a.id,
        )

        if connected_only:
            accounts = [
                account
                for account in accounts
                if account.is_connected()
            ]

        return accounts

    def get_account(self, account_id):
        return self._accounts.get(str(account_id))

    def find_by_email(self, email):
        if not email:
            return None

        wanted = str(email).strip().lower()

        for account in self._accounts.values():

            if (
                account.email
                and account.email.lower() == wanted
            ):

                return account

        return None

    def count(self, connected_only=True):

        return len(
            self.list_accounts(
                connected_only=connected_only
            )
        )

    # =====================================================
    # MUTATIONS
    # =====================================================

    def add_account(
        self,
        provider,
        email=None,
        display_name=None,
    ):
        """
        Register an authorized account.

        Idempotent for the same provider+email pair.
        Returns the account record.
        """

        if not provider or not str(provider).strip():

            raise ValueError(
                "An account requires a provider."
            )

        existing = None

        if email:

            candidate = self.find_by_email(email)

            if (
                candidate
                and candidate.provider == provider
            ):
                existing = candidate

        if existing is not None:

            existing.status = "connected"

            self._save()

            return existing

        account = CloudAccount(
            account_id=f"account-{self._next_number}",
            provider=provider,
            email=email,
            display_name=display_name,
            status="connected",
        )

        self._next_number += 1

        self._accounts[account.id] = account

        self._save()

        return account

    def remove_account(self, account_id):
        """
        Disconnect an account by id.

        Returns the removed record, or None when unknown.
        The record is kept in a disconnected state so its
        id can never be silently reassigned.
        """

        account = self.get_account(account_id)

        if account is None:
            return None

        account.status = "disconnected"

        self._save()

        return account

    # =====================================================
    # SELECTION
    # =====================================================

    def resolve_selector(self, selector):
        """
        Resolve an explicit account reference.

        Accepted forms:

            "2"           -> second connected account
            2             -> second connected account
            "account-2"   -> exact internal id
            "user@x.com"  -> email match

        Returns the CloudAccount or None.
        """

        if selector is None:
            return None

        text = str(selector).strip()

        if not text:
            return None

        lowered = text.lower()

        if lowered in self._accounts:
            return self._accounts[lowered]

        by_email = self.find_by_email(text)

        if by_email is not None:
            return by_email

        digits = lowered.lstrip("#a")

        if not digits.isdigit():
            digits = lowered.replace(
                "account number ",
                "",
            ).replace("number ", "").strip()

        if digits.isdigit():

            position = int(digits)

            connected = self.list_accounts(
                connected_only=True
            )

            if 1 <= position <= len(connected):

                return connected[position - 1]

        return None
