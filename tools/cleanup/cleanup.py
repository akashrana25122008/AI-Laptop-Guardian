import os
import time


class CleanupTool:
    """
    Safe TEMP cleanup scanner.

    IMPORTANT:
    This tool only analyzes files.
    It NEVER deletes files.
    """

    SAFE_EXTENSIONS = {
        ".tmp",
    }

    REVIEW_EXTENSIONS = {
        ".log",
    }

    PROTECTED_EXTENSIONS = {
        ".exe",
        ".msi",
        ".dll",
        ".sys",
        ".node",
    }

    PROTECTED_DIRECTORIES = {
        "winget",
    }

    # Normal temporary files
    MIN_AGE_DAYS = 3
    MIN_SIZE_MB = 1

    # Large temporary files get higher priority
    # even when they are newer.
    LARGE_FILE_MB = 50

    def __init__(self):
        self.user_temp = os.environ.get("TEMP")

    # =====================================================
    # SCAN
    # =====================================================

    def scan(self):
        """Scan the TEMP directory."""

        if not self.user_temp:
            return {
                "success": False,
                "tool": "cleanup",
                "error": "TEMP environment variable not found.",
                "message": "TEMP environment variable not found.",
            }

        if not os.path.isdir(self.user_temp):
            return {
                "success": False,
                "tool": "cleanup",
                "error": "TEMP directory does not exist.",
                "message": "TEMP directory does not exist.",
            }

        files = []
        total_size = 0

        for root, dirs, filenames in os.walk(self.user_temp):

            for filename in filenames:

                path = os.path.join(root, filename)

                try:
                    size = os.path.getsize(path)
                    modified = os.path.getmtime(path)

                    age_days = (
                        time.time() - modified
                    ) / (60 * 60 * 24)

                    extension = os.path.splitext(
                        filename
                    )[1].lower()

                    file_info = {
                        "path": path,
                        "name": filename,
                        "extension": extension,
                        "size_bytes": size,
                        "size_mb": round(
                            size / (1024 ** 2),
                            2,
                        ),
                        "age_days": round(
                            age_days,
                            1,
                        ),
                    }

                    files.append(file_info)
                    total_size += size

                except (
                    PermissionError,
                    FileNotFoundError,
                    OSError,
                ):
                    continue

        return {
            "success": True,
            "tool": "cleanup",
            "data": {
                "location": self.user_temp,
                "file_count": len(files),
                "total_size_mb": round(
                    total_size / (1024 ** 2),
                    2,
                ),
                "files": files,
            },
        }

    # =====================================================
    # PROTECTED DIRECTORY
    # =====================================================

    def is_protected_directory(self, path):
        """Check whether the file is inside a protected directory."""

        normalized = os.path.normcase(path)

        parts = normalized.replace(
            "/",
            "\\",
        ).split("\\")

        protected = {
            directory.lower()
            for directory in self.PROTECTED_DIRECTORIES
        }

        return any(
            part.lower() in protected
            for part in parts
        )

    # =====================================================
    # LOCK CHECK
    # =====================================================

    def is_locked(self, path):
        """Check whether a file is currently inaccessible."""

        try:
            with open(path, "rb"):
                return False

        except (
            PermissionError,
            OSError,
        ):
            return True

    # =====================================================
    # CLASSIFICATION
    # =====================================================

    def classify_file(self, file):

        path = file["path"]
        extension = file["extension"]
        size_mb = file["size_mb"]
        age_days = file["age_days"]

        # -------------------------------------------------
        # Protected directory
        # -------------------------------------------------

        if self.is_protected_directory(path):

            return {
                "status": "protected",
                "risk": "high",
                "reason": (
                    "File is inside a protected directory."
                ),
            }

        # -------------------------------------------------
        # Locked file
        # -------------------------------------------------

        if self.is_locked(path):

            return {
                "status": "locked",
                "risk": "high",
                "reason": "File is currently locked.",
            }

        # -------------------------------------------------
        # LARGE .TMP FILE
        # -------------------------------------------------

        if (
            extension in self.SAFE_EXTENSIONS
            and size_mb >= self.LARGE_FILE_MB
        ):

            return {
                "status": "safe",
                "risk": "low",
                "reason": (
                    "Large temporary file "
                    f"({size_mb} MB)."
                ),
            }

        # -------------------------------------------------
        # NORMAL .TMP FILE
        # -------------------------------------------------

        if extension in self.SAFE_EXTENSIONS:

            if age_days >= self.MIN_AGE_DAYS:

                if size_mb >= self.MIN_SIZE_MB:

                    return {
                        "status": "safe",
                        "risk": "low",
                        "reason": (
                            "Temporary .tmp file older "
                            "than 3 days and larger "
                            "than 1 MB."
                        ),
                    }

            return {
                "status": "unknown",
                "risk": "unknown",
                "reason": (
                    "Temporary file is either too "
                    "new or too small."
                ),
            }

        # -------------------------------------------------
        # LOG FILE
        # -------------------------------------------------

        if extension in self.REVIEW_EXTENSIONS:

            if (
                age_days >= self.MIN_AGE_DAYS
                and size_mb >= self.MIN_SIZE_MB
            ):

                return {
                    "status": "review",
                    "risk": "medium",
                    "reason": (
                        "Old log file. "
                        "Review before deleting."
                    ),
                }

            return {
                "status": "unknown",
                "risk": "unknown",
                "reason": (
                    "Log file is too new or too small."
                ),
            }

        # -------------------------------------------------
        # Executable / binary files
        # -------------------------------------------------

        if extension in self.PROTECTED_EXTENSIONS:

            return {
                "status": "unknown",
                "risk": "unknown",
                "reason": (
                    f"{extension} file outside a "
                    "protected directory. "
                    "Review manually."
                ),
            }

        # -------------------------------------------------
        # Everything else
        # -------------------------------------------------

        return {
            "status": "unknown",
            "risk": "unknown",
            "reason": (
                f"File type "
                f"{extension or '[none]'} "
                "is not approved."
            ),
        }

    # =====================================================
    # PREVIEW
    # =====================================================

    def preview(self):
        """
        Generate cleanup safety report.

        NOTHING IS DELETED.
        """

        result = self.scan()

        if not result["success"]:
            return result

        files = result["data"]["files"]

        safe_candidates = []
        review_files = []
        protected_files = []
        locked_files = []
        unknown_files = []

        for file in files:

            classification = self.classify_file(file)

            file["classification"] = (
                classification["status"]
            )

            file["risk"] = classification["risk"]
            file["reason"] = classification["reason"]

            status = classification["status"]

            if status == "safe":
                safe_candidates.append(file)

            elif status == "review":
                review_files.append(file)

            elif status == "protected":
                protected_files.append(file)

            elif status == "locked":
                locked_files.append(file)

            else:
                unknown_files.append(file)

        # -------------------------------------------------
        # Sort largest first
        # -------------------------------------------------

        for collection in (
            safe_candidates,
            review_files,
            protected_files,
            locked_files,
            unknown_files,
        ):
            collection.sort(
                key=lambda x: x["size_bytes"],
                reverse=True,
            )

        # -------------------------------------------------
        # Calculate sizes
        # -------------------------------------------------

        safe_size = sum(
            x["size_bytes"]
            for x in safe_candidates
        )

        review_size = sum(
            x["size_bytes"]
            for x in review_files
        )

        protected_size = sum(
            x["size_bytes"]
            for x in protected_files
        )

        locked_size = sum(
            x["size_bytes"]
            for x in locked_files
        )

        unknown_size = sum(
            x["size_bytes"]
            for x in unknown_files
        )

        # -------------------------------------------------
        # Return report
        # -------------------------------------------------

        return {
            "success": True,
            "tool": "cleanup_preview",

            "data": {
                "location": result["data"]["location"],

                "total_files": len(files),

                "total_size_mb": (
                    result["data"]["total_size_mb"]
                ),

                "safe_candidates": len(
                    safe_candidates
                ),

                "safe_size_mb": round(
                    safe_size / (1024 ** 2),
                    2,
                ),

                "review_files": len(
                    review_files
                ),

                "review_size_mb": round(
                    review_size / (1024 ** 2),
                    2,
                ),

                "protected_files": len(
                    protected_files
                ),

                "protected_size_mb": round(
                    protected_size / (1024 ** 2),
                    2,
                ),

                "locked_files": len(
                    locked_files
                ),

                "locked_size_mb": round(
                    locked_size / (1024 ** 2),
                    2,
                ),

                "unknown_files": len(
                    unknown_files
                ),

                "unknown_size_mb": round(
                    unknown_size / (1024 ** 2),
                    2,
                ),

                "candidates": safe_candidates,
                "review": review_files,
                "protected": protected_files,
                "locked": locked_files,
                "unknown": unknown_files,
            },
        }