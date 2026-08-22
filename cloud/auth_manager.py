"""
Explicit Google account connection management.

This module owns the user-facing account lifecycle:

    connect    -> official Google OAuth consent flow
    complete   -> safe identity + isolated token placement
    status     -> offline listing of connected accounts
    disconnect -> removal of LOCAL authorization state

Hard rules enforced here:

    - Authentication NEVER starts implicitly. Importing
      modules, constructing the agent/router/planner, or
      asking local questions (CPU/RAM/storage/battery)
      can never trigger this code. Only an explicit user
      request to CONNECT a Google account does.

    - The OAuth flow itself is always Google's official
      installed-app consent flow. The user's Google
      password is never requested, accepted, or stored by
      this application.

    - Tokens are never printed, logged, or returned.
      Each account's authorization lives ONLY in its own
      isolated token file:

          <token_dir>/<account_id>.json

    - Disconnecting one account never touches another
      account, and never deletes anything from Google
      Drive or from local disks. It only removes THIS
      application's stored authorization for that one
      account.
"""

import os
import uuid

from agent.result_contract import sanitize_error


class PendingAuthentication:
    """
    Internal state for ONE in-progress connection.

    Holds the provider bound to a TEMPORARY isolated
    token file until the connection is completed or
    cancelled. This object is never placed into prompts,
    never serialized into results, and its provider is
    never exposed beyond the auth manager.
    """

    def __init__(self, provider, token_path):
        self.provider = provider

        self.token_path = str(token_path)


class GoogleAuthManager:
    """
    Coordinates explicit multi-account Google OAuth.

    Built on top of the existing MultiAccountDriveManager
    so registration, session isolation, and token layout
    follow exactly one architecture.
    """

    def __init__(
        self,
        drive_manager=None,
        credentials_file="credentials.json",
        pending_provider_factory=None,
    ):
        if drive_manager is None:
            from cloud.multi_drive import (
                MultiAccountDriveManager,
            )

            drive_manager = (
                MultiAccountDriveManager()
            )

        self.drive_manager = drive_manager

        self.token_dir = (
            drive_manager.token_dir
        )

        # Path of the OAuth CLIENT configuration file.
        # Its CONTENTS are never read, printed, or logged
        # by this module; only its existence is checked.

        self.credentials_file = str(credentials_file)

        self._pending_factory = (
            pending_provider_factory
            or self._default_pending_factory
        )

        # Optional hook for REMOTE token revocation via
        # Google's official revocation mechanism.
        #
        # Callable(account_id, token_file) -> bool
        #
        # It stays None by default: plain disconnect only
        # removes the LOCAL authorization state and never
        # reads token file contents. Remote revocation can
        # be enabled deliberately in a future milestone.

        self.remote_revoker = None

    # =====================================================
    # PROVIDER CONSTRUCTION (LAZY IMPORT)
    # =====================================================

    def _default_pending_factory(self, token_path):
        """
        Build a real provider bound to a TEMPORARY token
        file. Imported lazily so importing this module
        never requires the Google client libraries and
        never has side effects.
        """

        from cloud.google_drive import (
            GoogleDriveProvider,
        )

        return GoogleDriveProvider(
            credentials_file=self.credentials_file,
            token_file=token_path,
        )

    def _token_path_for(self, account_id):
        return os.path.join(
            self.token_dir,
            f"{account_id}.json",
        )

    # =====================================================
    # CONNECT: START (EXPLICIT USER INITIATION ONLY)
    # =====================================================

    def start_authentication(self):
        """
        Begin connecting ONE new Google account through
        the official OAuth consent flow.

        This runs ONLY when the user explicitly asks to
        connect a Google account. The user chooses the
        Google identity on Google's own consent screen;
        the application never asks for a password.
        """

        if not os.path.exists(
            self.credentials_file
        ):

            return {
                "success": False,
                "tool": "cloud_auth",
                "error_code": "missing_credentials",
                "error": (
                    "Google OAuth client file "
                    "'credentials.json' was not found."
                ),
            }

        try:

            os.makedirs(
                self.token_dir,
                exist_ok=True,
            )

        except OSError as error:

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": sanitize_error(error),
            }

        temp_name = (
            f".pending-{uuid.uuid4().hex}.json"
        )

        temp_path = os.path.join(
            self.token_dir,
            temp_name,
        )

        try:

            provider = self._pending_factory(
                temp_path
            )

        except Exception as error:

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": sanitize_error(error),
            }

        pending = PendingAuthentication(
            provider=provider,
            token_path=temp_path,
        )

        try:

            authenticated = (
                pending.provider.authenticate()
            )

        except Exception as error:

            # Covers closed consent windows, network
            # problems, and any other interruption.

            self.cancel_authentication(pending)

            return {
                "success": False,
                "tool": "cloud_auth",
                "cancelled": True,
                "error": sanitize_error(error),
            }

        if isinstance(authenticated, dict):

            if not authenticated.get("success"):

                self.cancel_authentication(
                    pending
                )

                return {
                    "success": False,
                    "tool": "cloud_auth",
                    "cancelled": True,
                    "error": (
                        authenticated.get(
                            "error",
                            "Google sign-in did "
                            "not complete.",
                        )
                    ),
                }

        elif not authenticated:

            self.cancel_authentication(pending)

            return {
                "success": False,
                "tool": "cloud_auth",
                "cancelled": True,
                "error": (
                    "Google sign-in was cancelled or "
                    "did not complete."
                ),
            }

        return {
            "success": True,
            "tool": "cloud_auth",
            "pending": pending,
        }

    # =====================================================
    # CONNECT: COMPLETE (IDENTITY + ISOLATED STORAGE)
    # =====================================================

    def complete_authentication(self, pending):
        """
        Finish a started connection:

            1. read the SAFE identity Google reports,
            2. register/update the CloudAccount
               (idempotent for the same email),
            3. move the temporary token into that
               account's OWN isolated token file.

        Other accounts are never touched. No secret ever
        enters the registry or any result.
        """

        if pending is None:

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    "There is no Google sign-in in "
                    "progress."
                ),
            }

        try:

            identity = (
                pending.provider.get_account_identity()
            )

        except Exception:

            # Raw exception text could embed sensitive
            # material from the OAuth layer; the payload
            # stays fully generic.

            self.cancel_authentication(pending)

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    "Google sign-in could not be "
                    "completed."
                ),
            }

        if (
            not isinstance(identity, dict)
            or not identity.get("success")
        ):

            self.cancel_authentication(pending)

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    "Google did not confirm the "
                    "account identity."
                ),
            }

        email = identity.get("email")

        if (
            not email
            or not str(email).strip()
        ):

            self.cancel_authentication(pending)

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    "Google did not report an email "
                    "address for this account."
                ),
            }

        email = str(email).strip()

        display_name = identity.get(
            "display_name"
        )

        existed_before = (
            self.drive_manager.registry.find_by_email(
                email
            )
            is not None
        )

        account = (
            self.drive_manager.connect_account(
                provider="google_drive",
                email=email,
                display_name=display_name,
            )
        )

        final_path = self._token_path_for(
            account.id
        )

        try:

            os.replace(
                pending.token_path,
                final_path,
            )

        except OSError as error:

            # Registration must not survive without its
            # isolated authorization state.

            self.cancel_authentication(pending)

            if not existed_before:

                self.drive_manager.registry.remove_account(
                    account.id
                )

            return {
                "success": False,
                "tool": "cloud_auth",
                "error": (
                    "The Google sign-in could not be "
                    "stored securely for this "
                    "account."
                ),
                "detail": sanitize_error(error),
            }

        # Drop any cached session so future operations
        # rebuild against the relocated token file.

        self.drive_manager._sessions.pop(
            account.id,
            None,
        )

        return {
            "success": True,
            "tool": "cloud_auth",
            "created_new": not existed_before,
            "total_accounts": (
                self.drive_manager.registry.count(
                    connected_only=True
                )
            ),
            "account": {
                "id": account.id,
                "label": account.safe_label(),
                "email": account.email,
                "provider": account.provider,
            },
        }

    def cancel_authentication(self, pending):
        """
        Abort a pending connection and remove its
        temporary authorization state.
        """

        if pending is None:
            return

        try:

            if os.path.exists(pending.token_path):
                os.remove(pending.token_path)

        except OSError:
            pass

    def connect_account(self):
        """
        One explicit user action:

            start -> authenticate -> complete

        Returns a contract-shaped result with SAFE
        metadata only.
        """

        started = self.start_authentication()

        if not started.get("success"):
            return started

        return self.complete_authentication(
            started["pending"]
        )

    # =====================================================
    # STATUS (OFFLINE, NO SECRETS)
    # =====================================================

    def get_auth_status(self):
        """
        Offline status of all connected accounts.

        A registered account whose isolated token file is
        missing is reported honestly as 'authentication
        unavailable' instead of pretending to work.
        """

        accounts = []

        for account in (
            self.drive_manager.registry.list_accounts(
                connected_only=True
            )
        ):

            token_exists = os.path.exists(
                self._token_path_for(account.id)
            )

            accounts.append(
                {
                    "id": account.id,
                    "label": account.safe_label(),
                    "email": account.email,
                    "provider": account.provider,
                    "status": (
                        "connected"
                        if token_exists
                        else "authentication unavailable"
                    ),
                }
            )

        return {
            "success": True,
            "tool": "cloud_accounts",
            "accounts": accounts,
        }

    # =====================================================
    # DISCONNECT (LOCAL AUTHORIZATION STATE ONLY)
    # =====================================================

    def disconnect_account(
        self,
        account_id,
        revoke_remote=False,
    ):
        """
        Disconnect EXACTLY ONE account:

            - mark its registration disconnected,
            - drop its cached session,
            - delete ONLY its isolated token file.

        This never deletes files from Google Drive,
        never touches local user files, and never
        affects any other account.

        `revoke_remote` is designed for Google's official
        revocation mechanism but is opt-in; with the
        default setup no remote call and no token-file
        read happens at all.
        """

        account = (
            self.drive_manager.registry.get_account(
                account_id
            )
        )

        if (
            account is None
            or not account.is_connected()
        ):

            return {
                "success": False,
                "tool": "cloud_disconnect",
                "error": (
                    f"Account '{account_id}' is not "
                    f"connected."
                ),
            }

        if revoke_remote and (
            self.remote_revoker is not None
        ):

            try:

                self.remote_revoker(
                    account.id,
                    self._token_path_for(
                        account.id
                    ),
                )

            except Exception:
                # Revocation problems must never block
                # removing the local authorization.

                pass

        removed = (
            self.drive_manager.disconnect_account(
                account.id
            )
        )

        if removed is None:

            return {
                "success": False,
                "tool": "cloud_disconnect",
                "error": (
                    f"Account '{account_id}' could not "
                    f"be disconnected."
                ),
            }

        token_path = self._token_path_for(
            account.id
        )

        local_removed = False

        try:

            if os.path.exists(token_path):
                os.remove(token_path)
                local_removed = True

        except OSError:
            pass

        return {
            "success": True,
            "tool": "cloud_disconnect",
            "local_authorization_removed": (
                local_removed
            ),
            "account": {
                "id": removed.id,
                "label": removed.safe_label(),
                "email": removed.email,
                "provider": removed.provider,
            },
        }
