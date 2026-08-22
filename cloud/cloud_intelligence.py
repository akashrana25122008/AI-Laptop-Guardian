"""
Read-only cloud storage intelligence.

This module turns per-account Google Drive metadata into
deterministic, cross-account storage facts:

    - storage quota per account,
    - a combined summary with honest partial failures,
    - large-file analysis by metadata only,
    - duplicate CANDIDATES by name + size,
    - deterministic insights.

Hard rules enforced everywhere in this module:

    - Every result retains its originating account
      identity. Files from different accounts are never
      merged into one ambiguous record.
    - Unknown values stay unknown. Nothing is ever
      guessed, defaulted to zero, or invented.
    - One failing account never hides information from
      healthy accounts.
    - This layer is strictly read-only: it never uploads,
      downloads, deletes, moves, or modifies anything.
"""

from agent.result_contract import sanitize_error

MB = 1024 * 1024

GB = MB * 1024

# Sensible default threshold for "large file" analysis.
# Explicit thresholds from the user override this.

DEFAULT_LARGE_FILE_MIN_MB = 100


def _to_int(value):
    """
    Convert a provider value to int when safely possible.

    Returns None for anything missing or malformed.
    Unknown stays unknown; it is never coerced into zero.
    """

    if value is None or value == "":
        return None

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def format_size(size_bytes):
    """
    Deterministic byte-size formatting for user-facing
    text.

    Uses binary units (1 KB = 1024 bytes) consistently.
    """

    size = _to_int(size_bytes)

    if size is None:
        return "unknown size"

    negative = size < 0

    magnitude = abs(float(size))

    if magnitude >= GB:

        text = f"{magnitude / GB:.2f} GB"

    elif magnitude >= MB:

        text = f"{magnitude / MB:.1f} MB"

    elif magnitude >= 1024:

        text = f"{magnitude / 1024:.1f} KB"

    else:

        text = f"{int(magnitude)} bytes"

    if negative:
        text = "-" + text

    return text


class CloudStorageIntelligence:
    """
    Deterministic cross-account storage analysis.

    Built on top of MultiAccountDriveManager without
    changing any Milestone 7 behavior.
    """

    def __init__(self, drive_manager):

        self.manager = drive_manager

    # =====================================================
    # TARGET RESOLUTION (SAME RULES AS SEARCH)
    # =====================================================

    def _resolve_targets(
        self,
        account_ids=None,
        scope_all=False,
        tool_name="cloud_storage",
    ):
        """
        Resolve target accounts deterministically:

            - explicit account ids are validated and
              never silently replaced,
            - ALL connected accounts only when clearly
              requested,
            - the single connected account is used
              automatically,
            - multiple connected accounts without an
              explicit choice produce a needs_selection
              result instead of a silent pick.

        Returns (targets, error_result).
        """

        connected = (
            self.manager.registry.list_accounts(
                connected_only=True
            )
        )

        if not connected:

            return None, {
                "success": False,
                "tool": tool_name,
                "error": (
                    "No connected Google Drive "
                    "accounts."
                ),
            }

        if account_ids:

            targets = []

            for candidate in account_ids:

                account = (
                    self.manager.registry.get_account(
                        candidate
                    )
                )

                if (
                    account is None
                    or not account.is_connected()
                ):

                    return None, {
                        "success": False,
                        "tool": tool_name,
                        "error": (
                            f"Account '{candidate}' "
                            f"is not connected."
                        ),
                    }

                targets.append(account)

            return targets, None

        if scope_all:

            return list(connected), None

        if len(connected) == 1:

            return [connected[0]], None

        return None, {
            "success": False,
            "tool": tool_name,
            "needs_selection": True,
            "error": (
                "Multiple Google Drive accounts "
                "are connected."
            ),
            "accounts": (
                self.manager.describe_accounts()
            ),
        }

    # =====================================================
    # PER-ACCOUNT STORAGE QUOTA
    # =====================================================

    def _fetch_storage_entry(self, account):
        """
        Fetch ONE account's storage quota as an entry
        record.

        Status semantics:

            - "available"   : at least one quota value
                              was reported by the API,
            - "unavailable" : the call succeeded but no
                              usable values were provided,
            - "failed"      : session problem, exception,
                              or explicit failure result.

        Unavailable is NEVER treated as zero.
        """

        entry = {
            "account_id": account.id,
            "provider": account.provider,
            "email": account.email,
            "label": account.safe_label(),
            "status": "failed",
            "storage": {
                "total_bytes": None,
                "used_bytes": None,
                "free_bytes": None,
            },
            "error": None,
        }

        session = self.manager.get_session(
            account.id
        )

        if session is None:

            entry["error"] = (
                "No available session for this "
                "account."
            )

            return entry

        if not hasattr(
            session,
            "get_storage_info",
        ):

            entry["error"] = (
                "Provider does not expose storage "
                "information."
            )

            return entry

        try:

            raw = session.get_storage_info()

        except Exception as error:

            entry["error"] = sanitize_error(error)

            return entry

        if not isinstance(raw, dict):

            entry["error"] = (
                "Provider returned an invalid "
                "storage response."
            )

            return entry

        if not raw.get("success"):

            entry["error"] = sanitize_error(
                raw.get("error", "Unknown error.")
            )

            return entry

        total = _to_int(raw.get("total_bytes"))

        used = _to_int(raw.get("used_bytes"))

        # Free space is computed ONLY from two known
        # values. It is never derived from guesses.

        free = None

        if total is not None and used is not None:

            free = total - used

        entry["storage"]["total_bytes"] = total

        entry["storage"]["used_bytes"] = used

        entry["storage"]["free_bytes"] = free

        if total is None and used is None:

            entry["status"] = "unavailable"

            entry["error"] = (
                "Google did not report storage "
                "values for this account."
            )

        else:

            entry["status"] = "available"

        return entry

    def get_account_storage(self, account_id):
        """
        Read-only storage information for ONE exact
        account.

        Unknown or disconnected accounts fail safely;
        another account's data is never substituted.
        """

        account = (
            self.manager.registry.get_account(
                account_id
            )
        )

        if (
            account is None
            or not account.is_connected()
        ):

            return {
                "success": False,
                "tool": "cloud_storage",
                "error": (
                    f"Account '{account_id}' is "
                    f"not connected."
                ),
            }

        entry = self._fetch_storage_entry(
            account
        )

        if entry["status"] != "available":

            return {
                "success": False,
                "tool": "cloud_storage",
                "account_id": account.id,
                "error": (
                    entry.get("error")
                    or (
                        "Storage information is "
                        "unavailable for this "
                        "account."
                    )
                ),
                "entry": entry,
            }

        return {
            "success": True,
            "tool": "cloud_storage",
            "entry": entry,
        }

    # =====================================================
    # MULTI-ACCOUNT STORAGE SUMMARY
    # =====================================================

    def summarize_accounts(
        self,
        account_ids=None,
        scope_all=False,
    ):
        """
        Summarize storage across explicitly resolved
        accounts.

        Aggregation rules:

            - totals include ONLY known values,
            - unavailable values are never treated as
              zero,
            - excluded (failed/unavailable) accounts are
              listed explicitly so incomplete data is
              never presented as complete.
        """

        targets, error = self._resolve_targets(
            account_ids=account_ids,
            scope_all=scope_all,
            tool_name="cloud_storage",
        )

        if error is not None:
            return error

        entries = []

        for account in targets:

            entries.append(
                self._fetch_storage_entry(
                    account
                )
            )

        available = [
            entry
            for entry in entries
            if entry["status"] == "available"
        ]

        used_values = [
            entry["storage"]["used_bytes"]
            for entry in available
            if entry["storage"]["used_bytes"]
            is not None
        ]

        free_values = [
            entry["storage"]["free_bytes"]
            for entry in available
            if entry["storage"]["free_bytes"]
            is not None
        ]

        totals = {
            "known_used_bytes": (
                sum(used_values)
                if used_values
                else None
            ),
            "known_free_bytes": (
                sum(free_values)
                if free_values
                else None
            ),
            "included_account_ids": [
                entry["account_id"]
                for entry in available
            ],
            "excluded_accounts": [
                {
                    "account_id": entry[
                        "account_id"
                    ],
                    "label": entry["label"],
                    "status": entry["status"],
                    **(
                        {"error": entry["error"]}
                        if entry.get("error")
                        else {}
                    ),
                }
                for entry in entries
                if entry["status"] != "available"
            ],
        }

        insights = self._compute_insights(
            entries
        )

        errors_joined = "; ".join(
            entry["error"]
            for entry in entries
            if entry["status"] == "failed"
            and entry.get("error")
        )

        return {
            "success": len(available) > 0,
            "tool": "cloud_storage",
            "accounts": entries,
            "totals": totals,
            "insights": insights,
            "succeeded_accounts": totals[
                "included_account_ids"
            ],
            "account_errors": [
                {
                    "account_id": entry[
                        "account_id"
                    ],
                    "error": entry["error"],
                }
                for entry in entries
                if entry["status"] == "failed"
            ],
            "error": (
                errors_joined
                if not available
                else None
            ),
        }

    def _compute_insights(self, entries):
        """
        Deterministic insights from per-account storage
        entries.

        Comparisons happen ONLY between accounts that
        actually reported the relevant value.
        """

        largest_used = None

        most_free = None

        for entry in entries:

            if entry["status"] != "available":
                continue

            used = entry["storage"]["used_bytes"]

            if used is not None:

                if (
                    largest_used is None
                    or used
                    > largest_used["used_bytes"]
                ):

                    largest_used = {
                        "account_id": entry[
                            "account_id"
                        ],
                        "label": entry["label"],
                        "used_bytes": used,
                    }

            free = entry["storage"][
                "free_bytes"
            ]

            if free is not None:

                if (
                    most_free is None
                    or free > most_free["free_bytes"]
                ):

                    most_free = {
                        "account_id": entry[
                            "account_id"
                        ],
                        "label": entry["label"],
                        "free_bytes": free,
                    }

        return {
            "largest_used_account": largest_used,
            "most_free_account": most_free,
        }

    # =====================================================
    # CROSS-ACCOUNT LARGE FILES (METADATA ONLY)
    # =====================================================

    def find_large_files(
        self,
        min_mb=None,
        account_ids=None,
        scope_all=False,
        limit_per_account=50,
    ):
        """
        Identify large files across explicitly resolved
        accounts using METADATA ONLY.

        Files are never downloaded and their contents
        are never read.
        """

        tool_name = "cloud_large_files"

        if min_mb is None:

            effective_mb = (
                DEFAULT_LARGE_FILE_MIN_MB
            )

        else:

            try:

                effective_mb = float(min_mb)

            except (
                TypeError,
                ValueError,
            ):

                effective_mb = (
                    DEFAULT_LARGE_FILE_MIN_MB
                )

        min_bytes = int(effective_mb * MB)

        targets, error = self._resolve_targets(
            account_ids=account_ids,
            scope_all=scope_all,
            tool_name=tool_name,
        )

        if error is not None:
            return error

        collected = []
        succeeded = []
        account_errors = []

        for account in targets:

            session = self.manager.get_session(
                account.id
            )

            if session is None:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            "No available session "
                            "for this account."
                        ),
                    }
                )

                continue

            if not hasattr(
                session,
                "list_large_files",
            ):

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            "Provider does not "
                            "support large-file "
                            "listing."
                        ),
                    }
                )

                continue

            try:

                result = (
                    session.list_large_files(
                        min_size_bytes=min_bytes,
                        limit=limit_per_account,
                    )
                )

            except Exception as listing_error:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": sanitize_error(
                            listing_error
                        ),
                    }
                )

                continue

            if (
                not isinstance(result, dict)
                or not result.get("success")
            ):

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": sanitize_error(
                            result.get(
                                "error",
                                "Unknown error.",
                            )
                            if isinstance(
                                result,
                                dict,
                            )
                            else (
                                "Invalid provider "
                                "result."
                            )
                        ),
                    }
                )

                continue

            succeeded.append(account.id)

            for file in result.get("files", []):

                if not isinstance(file, dict):
                    continue

                size = _to_int(
                    file.get("size_bytes")
                )

                if size is None or size <= 0:
                    continue

                # Defensive re-check so threshold
                # semantics hold even if a provider
                # pre-filter misbehaves.

                if size < min_bytes:
                    continue

                tagged = dict(file)

                tagged["size_bytes"] = size

                tagged["account_id"] = account.id

                if account.email:
                    tagged["account_email"] = (
                        account.email
                    )

                collected.append(tagged)

        collected.sort(
            key=lambda file: file["size_bytes"],
            reverse=True,
        )

        all_failed = (
            not succeeded and bool(account_errors)
        )

        return {
            "success": not all_failed,
            "tool": tool_name,
            "min_mb": effective_mb,
            "min_size_bytes": min_bytes,
            "files": collected,
            "count": len(collected),
            "accounts": (
                self.manager.describe_accounts()
            ),
            "succeeded_accounts": succeeded,
            "account_errors": account_errors,
            "error": (
                "; ".join(
                    entry["error"]
                    for entry in account_errors
                )
                if all_failed
                else None
            ),
        }

    # =====================================================
    # CROSS-ACCOUNT DUPLICATE CANDIDATES
    # =====================================================

    def find_duplicate_candidates(
        self,
        account_ids=None,
        scope_all=False,
        limit_per_account=200,
    ):
        """
        Identify LIKELY duplicate files across accounts
        by matching name + exact size.

        These are candidates, NOT proof of identical
        content:

            - match_level is always
              "possible (same name + same size)",
            - confirmed is always False,
            - content hashes are NEVER computed here
              because that would require reading file
              contents,

        and nothing is ever deleted or modified based on
        this analysis.
        """

        tool_name = "cloud_duplicates"

        targets, error = self._resolve_targets(
            account_ids=account_ids,
            scope_all=scope_all,
            tool_name=tool_name,
        )

        if error is not None:
            return error

        scanned = []
        succeeded = []
        account_errors = []

        for account in targets:

            session = self.manager.get_session(
                account.id
            )

            if session is None:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            "No available session "
                            "for this account."
                        ),
                    }
                )

                continue

            if not hasattr(
                session,
                "list_all_files_metadata",
            ):

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": (
                            "Provider does not "
                            "support metadata "
                            "listing."
                        ),
                    }
                )

                continue

            try:

                result = (
                    session.list_all_files_metadata(
                        limit=limit_per_account
                    )
                )

            except Exception as listing_error:

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": sanitize_error(
                            listing_error
                        ),
                    }
                )

                continue

            if (
                not isinstance(result, dict)
                or not result.get("success")
            ):

                account_errors.append(
                    {
                        "account_id": account.id,
                        "error": sanitize_error(
                            result.get(
                                "error",
                                "Unknown error.",
                            )
                            if isinstance(
                                result,
                                dict,
                            )
                            else (
                                "Invalid provider "
                                "result."
                            )
                        ),
                    }
                )

                continue

            succeeded.append(account.id)

            for file in result.get("files", []):

                if not isinstance(file, dict):
                    continue

                name = file.get("name")

                if (
                    not name
                    or not str(name).strip()
                ):
                    continue

                tagged = dict(file)

                tagged["account_id"] = account.id

                if account.email:
                    tagged["account_email"] = (
                        account.email
                    )

                scanned.append(tagged)

        groups_map = {}

        for file in scanned:

            size = _to_int(
                file.get("size_bytes")
            )

            # Files without a real reported size can
            # never participate in size-based
            # candidate matching.

            if size is None or size <= 0:
                continue

            key = (
                str(file.get("name"))
                .strip()
                .lower(),
                size,
            )

            groups_map.setdefault(
                key,
                [],
            ).append(file)

        groups = []

        for key, members in groups_map.items():

            if len(members) < 2:
                continue

            name, size = key

            copies = []

            for member in members:

                copies.append(
                    {
                        "file_id": member.get(
                            "id"
                        ),
                        "name": member.get(
                            "name"
                        ),
                        "account_id": member.get(
                            "account_id"
                        ),
                        "account_email": (
                            member.get(
                                "account_email"
                            )
                        ),
                        "modified_time": (
                            member.get(
                                "modified_time"
                            )
                        ),
                    }
                )

            groups.append(
                {
                    "name": name,
                    "size_bytes": size,
                    "count": len(members),
                    "copies": copies,
                    "match_level": (
                        "possible (same name "
                        "+ same size)"
                    ),
                    "confirmed": False,
                    "potential_reclaim_bytes": (
                        size * (len(members) - 1)
                    ),
                }
            )

        groups.sort(
            key=lambda group: (
                -group["potential_reclaim_bytes"],
                group["name"],
            )
        )

        potential_reclaim_total = sum(
            group["potential_reclaim_bytes"]
            for group in groups
        )

        all_failed = (
            not succeeded and bool(account_errors)
        )

        return {
            "success": not all_failed,
            "tool": tool_name,
            "files_scanned": len(scanned),
            "groups": groups,
            "group_count": len(groups),
            "potential_reclaim_bytes": (
                potential_reclaim_total
            ),
            "accounts": (
                self.manager.describe_accounts()
            ),
            "succeeded_accounts": succeeded,
            "account_errors": account_errors,
            "error": (
                "; ".join(
                    entry["error"]
                    for entry in account_errors
                )
                if all_failed
                else None
            ),
        }