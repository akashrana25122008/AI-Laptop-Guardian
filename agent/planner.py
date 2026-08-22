
import re


class Planner:
    """
    Decides which tool should handle the user's request.
    """

    # =====================================================
    # INTENT HELPERS
    # =====================================================

    # Explicit cloud targets.
    #
    # Examples:
    # Search my Google Drive
    # Download a file from gdrive
    # Upload report.pdf to the cloud

    CLOUD_EXPLICIT_PATTERN = re.compile(
        r"\b(?:google\s+drives?|gdrive|cloud)\b"
    )

    # Explicit multi-account references.
    #
    # Examples:
    #     Search account 2 for report.pdf
    #     Download backup.zip from account number 3
    #     Show files in account-1

    ACCOUNT_REF_PATTERN = re.compile(
        r"\baccounts?\s*(?:number\s*)?#?\s*(\d+)\b"
    )

    # Explicit ALL-accounts scoping.
    #
    # Example:
    #     Search all my connected Google Drives for x

    ALL_ACCOUNTS_PATTERN = re.compile(
        r"\ball\s+(?:my\s+)?(?:connected\s+)?"
        r"(?:google\s+)?drives?\b"
    )

    # Local machine drive references.
    #
    # Examples:
    # C drive, D: drive, c-drive
    # disk, hard disk, ssd, hdd
    # partition, volume, local drive

    LOCAL_DRIVE_PATTERN = re.compile(
        r"(?:"
        r"(?<![a-z0-9])[a-z]\s*[:\-\\]?\s*(?:drive|disk)\b"
        r"|\b(?:hard\s+)?disks?\b"
        r"|\b(?:ssd|hdd|nvme)\b"
        r"|\bpartitions?\b"
        r"|\bvolumes?\b"
        r"|\blocal\s+drive\b"
        r")"
    )

    # Local storage topics. Word boundaries prevent false
    # matches such as "temp" inside "temperature".

    STORAGE_KEYWORD_PATTERN = re.compile(
        r"\b(?:"
        r"storages?"
        r"|disks?"
        r"|drives?"
        r"|spaces?"
        r"|temps?"
        r"|temporary"
        r"|large\s+files?"
        r"|cleanup"
        r"|clean(?:\s+up)?"
        r"|ssd|hdd|nvme"
        r"|partitions?"
        r")\b"
    )

    def _targets_google_drive(self, text):
        """
        Decide whether a message refers to Google Drive
        or to a local drive such as C: or D:.

        Explicit cloud wording always wins:

            Search my Google Drive

        Local drive wording always stays local:

            Why is my C drive warning?

        A bare "drive" without local context is treated as
        Google Drive so that requests such as:

            Delete notes.txt from Drive
            Download report.pdf from drive

        keep working.
        """

        if self.CLOUD_EXPLICIT_PATTERN.search(text):
            return True

        if self.LOCAL_DRIVE_PATTERN.search(text):
            return False

        return bool(re.search(r"\bdrives?\b", text))

    def _is_cloud_search_request(self, text):
        """
        Decide whether a message is a Google Drive search.

        Explicit cloud wording always wins:

            Search my Google Drive
            What is in my Google Drive

        Otherwise a search/find verb is required together
        with a non-local drive reference:

            Search my drive for reports

        A bare "drive" without a search verb describes the
        laptop's own drive and stays local:

            My drive is running out of space
        """

        if self.CLOUD_EXPLICIT_PATTERN.search(text):
            return True

        if not re.search(r"\b(?:search|find)\b", text):
            return False

        return self._targets_google_drive(text)

    def plan(self, user_message: str):
        text = user_message.lower().strip()

        # =====================================================
        # MULTI-ACCOUNT CLOUD CONTEXT
        # =====================================================

        account_refs = (
            self.ACCOUNT_REF_PATTERN.findall(text)
        )

        scope_all = bool(
            self.ALL_ACCOUNTS_PATTERN.search(text)
        )

        # =====================================================
        # EXPLICIT ACCOUNT-REFERENCED CLOUD OPERATIONS
        # =====================================================
        # "Search account 2 for report.pdf" names a
        # connected account explicitly, which is cloud
        # intent even without the word "drive".
        #
        # Local drive references always stay local.
        # =====================================================

        if (
            account_refs
            and re.search(
                r"\b(?:search|find|download|upload|backup"
                r"|delete|remove)\b",
                text,
            )
            and not self.LOCAL_DRIVE_PATTERN.search(
                text
            )
            and not self.CLOUD_EXPLICIT_PATTERN.search(
                text
            )
        ):

            if re.search(
                r"\bdownload\b",
                text,
            ):

                query = None

                match = re.search(
                    r"download\s+(.+?)\s+from\s+"
                    r"accounts?\s*(?:number\s*)?\d+",
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()

                return {
                    "tool": "cloud_download",
                    "action": "download",
                    "query": query or "",
                    "account_refs": account_refs,
                }

            if re.search(
                r"\b(?:upload|backup)\b",
                text,
            ):

                query = None

                match = re.search(
                    r"(?:upload|backup)\s+(.+?)\s+to\s+"
                    r"accounts?\s*(?:number\s*)?\d+",
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()

                return {
                    "tool": "cloud_upload",
                    "action": "upload",
                    "path": query or "",
                    "account_refs": account_refs,
                }

            if re.search(
                r"\b(?:delete|remove)\b",
                text,
            ):

                query = None

                match = re.search(
                    r"(?:delete|remove)\s+(.+?)\s+from\s+"
                    r"accounts?\s*(?:number\s*)?\d+",
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()

                return {
                    "tool": "cloud_delete",
                    "action": "delete",
                    "query": query or "",
                    "account_refs": account_refs,
                }

            query = None

            for pattern in [
                r"(?:search|find)\s+accounts?\s*"
                r"(?:number\s*)?\d+\s+for\s+(.+)",
                r"(?:search|find)\s+(?:for\s+)?(.+?)\s+"
                r"(?:on|in|from)\s+accounts?\s*\d+",
            ]:

                match = re.search(
                    pattern,
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()
                    break

            return {
                "tool": "cloud_search",
                "action": "search",
                "query": query or "",
                "account_refs": account_refs,
            }

        # =====================================================
        # GOOGLE DRIVE - DELETE
        # =====================================================
        # Detect delete/remove requests BEFORE upload/search.
        #
        # Examples:
        # Delete upload_test_2.txt from Google Drive
        # Delete my report.pdf from Drive
        # Remove test.txt from Google Drive
        # Delete file named notes.txt from Drive

        if (
            re.search(r"\b(delete|remove)\b", text)
            and self._targets_google_drive(text)
        ):

            patterns = [
                r"(?:delete|remove)\s+(?:the\s+)?(?:file\s+)?(?:named\s+)?(.+?)\s+from\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:delete|remove)\s+(?:the\s+)?(?:file\s+)?(?:named\s+)?(.+?)\s+on\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:delete|remove)\s+(?:the\s+)?(?:file\s+)?(?:named\s+)?(.+?)\s+in\s+(?:my\s+)?(?:google\s+)?drive",
            ]

            query = None

            for pattern in patterns:
                match = re.search(
                    pattern,
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()
                    break

            if query:
                query = query.rstrip("?.!")

                query = re.sub(
                    r"^my\s+",
                    "",
                    query,
                    flags=re.IGNORECASE,
                )

            return {
                "tool": "cloud_delete",
                "action": "delete",
                "query": query or "",
                "account_refs": account_refs,
            }

        # =====================================================
        # GOOGLE DRIVE - DOWNLOAD
        # =====================================================

        if (
            re.search(r"\bdownload\b", text)
            and self._targets_google_drive(text)
        ):

            patterns = [
                r"download\s+(?:my\s+)?(?:the\s+)?(.+?)\s+from\s+(?:my\s+)?(?:google\s+)?drive",
                r"download\s+(?:my\s+)?(?:the\s+)?(.+?)\s+from\s+(?:my\s+)?drive",
            ]

            query = None

            for pattern in patterns:
                match = re.search(
                    pattern,
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()
                    break

            if query:
                query = query.rstrip("?.!")

            return {
                "tool": "cloud_download",
                "action": "download",
                "query": query or "",
                "account_refs": account_refs,
            }

        # =====================================================
        # GOOGLE DRIVE - UPLOAD
        # =====================================================

        if (
            re.search(r"\b(upload|backup)\b", text)
            and self._targets_google_drive(text)
        ):

            patterns = [
                r"(?:upload|backup)\s+(?:the\s+)?(?:file\s+)?(.+?)\s+to\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:upload|backup)\s+(?:the\s+)?(?:file\s+)?(.+?)\s+on\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:upload|backup)\s+(?:the\s+)?(?:file\s+)?(.+?)\s+to\s+(?:my\s+)?drive",
            ]

            file_path = None

            for pattern in patterns:
                match = re.search(
                    pattern,
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    file_path = match.group(1).strip()
                    break

            if file_path:
                file_path = file_path.rstrip("?.!")

                file_path = re.sub(
                    r"^my\s+",
                    "",
                    file_path,
                    flags=re.IGNORECASE,
                )

            return {
                "tool": "cloud_upload",
                "action": "upload",
                "path": file_path or "",
                "account_refs": account_refs,
            }

        # =====================================================
        # GOOGLE DRIVE - SEARCH
        # =====================================================

        if self._is_cloud_search_request(text):

            patterns = [
                r"(?:search|find)\s+(?:for\s+)?(.+?)\s+in\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:search|find)\s+(?:all\s+)?(?:my\s+)?(?:connected\s+)?(?:google\s+)?drives?\s+(?:for\s+)?(.+)",
                r"(?:files?\s+in\s+(?:my\s+)?(?:google\s+)?drive)\s+(?:about|named|called)\s+(.+)",
            ]

            query = None

            for pattern in patterns:
                match = re.search(
                    pattern,
                    user_message,
                    re.IGNORECASE,
                )

                if match:
                    query = match.group(1).strip()
                    break

            if query:
                query = query.rstrip("?.!")

                query = re.sub(
                    r"^(?:my|the)\s+",
                    "",
                    query,
                    flags=re.IGNORECASE,
                )

                query = re.sub(
                    r"\s+files?$",
                    "",
                    query,
                    flags=re.IGNORECASE,
                )

            return {
                "tool": "cloud_search",
                "action": "search",
                "query": query or "",
                "account_refs": account_refs,
                "scope": (
                    "all" if scope_all else None
                ),
            }

        # =====================================================
        # SYSTEM HEALTH
        # =====================================================

        if any(phrase in text for phrase in [
            "system health",
            "laptop health",
            "system status",
            "overall status",
            "laptop doing",
            "anything wrong",
            "is my laptop healthy",
            "is my system healthy",
            "health report",
        ]):
            return {
                "tool": "health",
                "action": "status",
            }

        # =====================================================
        # FILE INSPECTOR
        # =====================================================

        if any(phrase in text for phrase in [
            "what is in",
            "what's in",
            "whats in",
            "contents of",
            "content of",
            "inspect file",
            "inspect the file",
            "file contents",
            "file content",
            "any errors in",
        ]):

            match = re.search(
                r"(?:in|of)\s+([^\s?]+(?:\.[a-zA-Z0-9]+)?)",
                user_message,
                re.IGNORECASE,
            )

            if match:
                return {
                    "tool": "file_inspector",
                    "action": "inspect",
                    "path": match.group(1),
                }

        # =====================================================
        # DUPLICATE FILES (LOCAL, READ-ONLY)
        # =====================================================

        if re.search(r"\bduplicat", text):

            return {
                "tool": "duplicates",
                "action": "scan",
            }

        # =====================================================
        # LARGE FILES (LOCAL, READ-ONLY)
        # =====================================================

        if re.search(
            r"\blarge(?:st)?\s+files?\b",
            text,
        ):

            return {
                "tool": "large_files",
                "action": "scan",
            }

        # =====================================================
        # CLEANUP - DESTRUCTIVE INTENT
        # =====================================================
        # A delete/remove verb combined with temporary-file
        # wording becomes a PROPOSAL request. The actual
        # deletion always requires explicit confirmation
        # through agent.action_safety.
        #
        # Word boundaries keep "temperature" away from
        # "temp".
        #
        # This block sits AFTER every Google Drive block,
        # so remaining requests are purely local.
        # =====================================================

        if (
            re.search(
                r"\b(?:delete|remove)\b",
                text,
            )
            and re.search(
                r"\b(?:"
                r"temps?"
                r"|temporary"
                r"|tmp"
                r"|junk"
                r"|cleanup"
                r"|candidates?"
                r")\b",
                text,
            )
        ):

            return {
                "tool": "cleanup_delete",
                "action": "request",
            }

        # =====================================================
        # CLEANUP - PREVIEW INTENT
        # =====================================================
        # Local drive questions such as "Clean up my local
        # drive" keep their Milestone 3 behavior and stay
        # with the storage analyzer.
        # =====================================================

        cleanup_preview_requested = bool(
            re.search(
                r"\b(?:"
                r"cleanup"
                r"|clean\s*up"
                r"|junk"
                r"|candidates?"
                r"|free\s*up\s+(?:some\s*)?space"
                r")\b",
                text,
            )
            or any(
                phrase in text
                for phrase in [
                    "safely clean",
                    "safe to clean",
                    "safe to delete",
                    "safe to remove",
                    "what can i delete",
                    "what can be cleaned",
                    "what can be safely cleaned",
                    "show cleanup candidates",
                ]
            )
        )

        if (
            cleanup_preview_requested
            and not self.LOCAL_DRIVE_PATTERN.search(
                text
            )
        ):

            return {
                "tool": "cleanup_preview",
                "action": "preview",
            }

        # =====================================================
        # STORAGE
        # =====================================================

        if self.STORAGE_KEYWORD_PATTERN.search(text):
            return {
                "tool": "storage",
                "action": "analyze",
            }

        # =====================================================
        # BATTERY
        # =====================================================

        if any(word in text for word in [
            "battery",
            "charging",
            "charge",
        ]):
            return {
                "tool": "battery",
                "action": "health",
            }

        # =====================================================
        # CPU
        # =====================================================

        if any(word in text for word in [
            "cpu",
            "processor",
            "temperature",
        ]):
            return {
                "tool": "cpu",
                "action": "status",
            }

        # =====================================================
        # RAM
        # =====================================================

        if any(word in text for word in [
            "ram",
            "memory",
        ]):
            return {
                "tool": "ram",
                "action": "status",
            }

        # =====================================================
        # GENERAL CONVERSATION
        # =====================================================

        return {
            "tool": "chat",
            "action": "general",
        }
