
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
        r"\b(?:google\s+drive|gdrive|cloud)\b"
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

        return bool(re.search(r"\bdrive\b", text))

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
            }

        # =====================================================
        # GOOGLE DRIVE - SEARCH
        # =====================================================

        if self._is_cloud_search_request(text):

            patterns = [
                r"(?:search|find)\s+(?:for\s+)?(.+?)\s+in\s+(?:my\s+)?(?:google\s+)?drive",
                r"(?:search|find)\s+(?:my\s+)?(?:google\s+)?drive\s+(?:for\s+)?(.+)",
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
