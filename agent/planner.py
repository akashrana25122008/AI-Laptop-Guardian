
import re


class Planner:
    """
    Decides which tool should handle the user's request.
    """

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
            and re.search(r"\b(drive|google drive)\b", text)
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
            and re.search(r"\b(drive|google drive)\b", text)
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
            and re.search(r"\b(drive|google drive)\b", text)
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

        if re.search(r"\b(drive|google drive)\b", text):

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

        if any(word in text for word in [
            "storage",
            "disk",
            "drive",
            "space",
            "temp",
            "large file",
            "cleanup",
            "clean",
        ]):
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
