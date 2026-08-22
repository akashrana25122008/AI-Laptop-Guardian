"""
Multi-account Google Drive manager.

Architecture:

    CloudAccount  (safe metadata, cloud/accounts.py)
        |
        |  one isolated session per account
        v
    MultiAccountDriveManager  (this module)
        |
        v
    GoogleDriveProvider       (isolated token file)

Isolation guarantees:

    - Every account gets its OWN GoogleDriveProvider
      instance with its own token file:

          <token_dir>/<account_id>.json

      Account A can never load Account B's credentials.

    - Sessions are created lazily. Constructing this
      manager never touches Google.

    - No global active-provider state: every operation
      names the exact account it operates on.

This module NEVER logs or returns token contents.
"""

import os


class MultiAccountDriveManager:
    """
    Coordinates multiple isolated Google Drive sessions.
    """

    def __init__(
        self,
        registry=None,
        token_dir=os.path.join(
            "cloud_data",
            "tokens",
        ),
        provider_factory=None,
    ):
        if registry is None:
            from cloud.accounts import (
                AccountRegistry,
            )

            registry = AccountRegistry()

        self.registry = registry

        self.token_dir = token_dir

        # Tests inject a provider factory so NO real
        # Google provider is ever constructed.

        self._provider_factory = (
            provider_factory
            or self._default_provider_factory
        )

        self._sessions = {}

    # =====================================================
    # SESSIONS (LAZY, ISOLATED PER ACCOUNT)
    # =====================================================

    def _default_provider_factory(self, account):
        """
        Build a real provider bound to ONE account's
        isolated token file.

        Imported lazily so importing this module never
        requires the Google client libraries.
        """

        from cloud.google_drive import (
            GoogleDriveProvider,
        )

        token_path = os.path.join(
            self.token_dir,
            f"{account.id}.json",
        )

        return GoogleDriveProvider(
            token_file=token_path,
        )

    def get_session(self, account_id):
        """
        Return the provider session for ONE account.

        Returns None for unknown or disconnected
        accounts (fail-safe).
        """

        account = self.registry.get_account(
            account_id
        )

        if account is None:
            return None

        if not account.is_connected():
            return None

        key = str(account_id)

        if key not in self._sessions:

            self._sessions[key] = (
                self._provider_factory(account)
            )

        return self._sessions[key]

    # =====================================================
    # ACCOUNT LIFECYCLE
    # =====================================================

    def connect_account(
        self,
        provider="google_drive",
        email=None,
        display_name=None,
    ):
        """
        Register an authorized account.

        This does NOT authenticate and does NOT touch the
        network. Authorization itself belongs to the
        official OAuth flow executed explicitly by the
        user later.
        """

        return self.registry.add_account(
            provider=provider,
            email=email,
            display_name=display_name,
        )

    def disconnect_account(self, account_id):

        removed = self.registry.remove_account(
            account_id
        )

        if removed is not None:

            self._sessions.pop(
                str(removed.id),
                None,
            )

        return removed

    def authenticate_account(self, account_id):
        """
        Explicitly run the OAuth flow for ONE account.

        This is ONLY invoked by a deliberate user action;
        it is never part of registration or of any other
        operation. The token for this account is stored in
        that account's isolated token file only.

        Returns the provider's result dict (or a safe
        failure).
        """

        session = self.get_session(account_id)

        if session is None:

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    f"No connected Google Drive "
                    f"session for account "
                    f"'{account_id}'."
                ),
            }

        try:

            return session.authenticate()

        except Exception as error:

            return {
                "success": False,
                "tool": "cloud_auth",
                "account_id": account_id,
                "error": str(error),
            }

    def describe_accounts(self):
        """Safe metadata list for user-facing messages."""

        return [
            {
                "id": account.id,
                "label": account.safe_label(),
                "provider": account.provider,
                "status": account.status,
            }
            for account in (
                self.registry.list_accounts()
            )
        ]

    # =====================================================
    # NORMALIZATION HELPERS
    # =====================================================

    @staticmethod
    def _tag_match(match, account):
        tagged = dict(match)

        tagged["account_id"] = account.id

        if account.email:
            tagged["account_email"] = (
                account.email
            )

        return tagged

    # =====================================================
    # MULTI-ACCOUNT SEARCH (READ-ONLY)
    # =====================================================

    def search_accounts(
        self,
        query,
        account_ids=None,
        scope_all=False,
    ):
        """
        Search one specific account, explicitly selected
        accounts, or ALL connected accounts.

        Rules:

            - Never silently picks between multiple
              ambiguous accounts.
            - Results always carry their originating
              account identity.
            - Per-account failures are reported; they are
              never converted into fake successes.
        """

        if not query or not str(query).strip():

            return {
                "success": False,
                "tool": "cloud_search",
                "error": (
                    "No Google Drive search query "
                    "provided."
                ),
            }

        connected = (
            self.registry.list_accounts(
                connected_only=True
            )
        )

        if not connected:

            return {
                "success": False,
                "tool": "cloud_search",
                "error": (
                    "No connected Google Drive "
                    "accounts."
                ),
            }

        # -------------------------------------------------
        # Resolve target accounts deterministically.
        # -------------------------------------------------

        if account_ids:

            targets = []

            for candidate in account_ids:

                account = (
                    self.registry.get_account(
                        candidate
                    )
                )

                if (
                    account is None
                    or not account.is_connected()
                ):

                    return {
                        "success": False,
                        "tool": "cloud_search",
                        "error": (
                            f"Account '{candidate}' "
                            f"is not connected."
                        ),
                    }

                targets.append(account)

        elif scope_all:

            targets = list(connected)

        elif len(connected) == 1:

            targets = [connected[0]]

        else:

            return {
                "success": False,
                "tool": "cloud_search",
                "needs_selection": True,
                "error": (
                    "Multiple Google Drive accounts "
                    "are connected."
                ),
                "accounts": (
                    self.describe_accounts()
                ),
            }

        # -------------------------------------------------
        # Execute per-account searches.
        # -------------------------------------------------

        matches = []
        account_errors = []
        succeeded = []

        for account in targets:

            session = self.get_session(account.id)

            if session is None:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            "No available session for "
                            "this account."
                        ),
                    }
                )

                continue

            try:

                result = session.search_files(
                    query
                )

            except Exception as error:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": str(error),
                    }
                )

                continue

            if isinstance(result, dict) and (
                result.get("success")
            ):

                succeeded.append(account.id)

                for match in result.get(
                    "matches",
                    [],
                ):
                    matches.append(
                        self._tag_match(
                            match,
                            account,
                        )
                    )

            else:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            result.get(
                                "error",
                                "Unknown error.",
                            )
                            if isinstance(result, dict)
                            else "Invalid result."
                        ),
                    }
                )

        return {
            "success": len(succeeded) > 0,
            "tool": "cloud_search",
            "matches": matches,
            "accounts": self.describe_accounts(),
            "succeeded_accounts": succeeded,
            "account_errors": account_errors,
            "error": (
                "; ".join(
                    entry["error"]
                    for entry in account_errors
                )
                if account_errors and not succeeded
                else None
            ),
        }

    # =====================================================
    # BOUND DOWNLOAD / DELETE / UPLOAD (EXACT TARGET ONLY)
    # =====================================================

    def _bound_operation(
        self,
        tool_name,
        account_id,
        func_name,
        *args,
    ):
        """
        Run ONE operation against ONE exact account.

        Unknown or disconnected accounts fail safely
        instead of falling back to another account's
        session.
        """

        session = self.get_session(account_id)

        if session is None:

            return {
                "success": False,
                "tool": tool_name,
                "error": (
                    f"No connected Google Drive "
                    f"session for account "
                    f"'{account_id}'."
                ),
            }

        try:

            result = getattr(session, func_name)(
                *args
            )

        except Exception as error:

            return {
                "success": False,
                "tool": tool_name,
                "account_id": account_id,
                "error": str(error),
            }

        if not isinstance(result, dict):

            return {
                "success": False,
                "tool": tool_name,
                "account_id": account_id,
                "error": "Invalid provider result.",
            }

        result.setdefault("account_id", account_id)

        account = self.registry.get_account(
            account_id
        )

        if account is not None and account.email:

            result.setdefault(
                "account_email",
                account.email,
            )

        return result

    def download_from_account(
        self,
        account_id,
        file_id,
    ):

        if not file_id or not str(file_id).strip():

            return {
                "success": False,
                "tool": "cloud_download",
                "error": "No file ID provided.",
            }

        return self._bound_operation(
            "cloud_download",
            account_id,
            "download_file_by_id",
            str(file_id).strip(),
        )

    def delete_from_account(
        self,
        account_id,
        file_id,
    ):

        if not file_id or not str(file_id).strip():

            return {
                "success": False,
                "tool": "cloud_delete",
                "error": "No file ID provided.",
            }

        return self._bound_operation(
            "cloud_delete",
            account_id,
            "delete_file_by_id",
            str(file_id).strip(),
        )

    def upload_to_account(
        self,
        account_id,
        local_path,
    ):

        if not local_path or not str(local_path).strip():

            return {
                "success": False,
                "tool": "cloud_upload",
                "error": "No local file provided.",
            }

        return self._bound_operation(
            "cloud_upload",
            account_id,
            "upload_file",
            str(local_path).strip(),
        )
