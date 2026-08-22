from pathlib import Path
import os


class FileInspector:
    """
    Safely inspect files and return useful information.

    This tool NEVER modifies or deletes files.
    """

    MAX_TEXT_SIZE_MB = 10

    TEXT_EXTENSIONS = {
        ".txt", ".log", ".json", ".xml", ".csv",
        ".ini", ".cfg", ".conf", ".md",
        ".py", ".java", ".c", ".cpp", ".h",
        ".html", ".css", ".js", ".yaml", ".yml",
    }

    BINARY_EXTENSIONS = {
        ".exe", ".dll", ".sys", ".node", ".msi", ".bin",
    }

    def find_file(self, filename):
        """
        Safely locate a file by filename.
        This method NEVER modifies or deletes files.
        """

        filename = str(filename).strip()

        if not filename:
            return {
                "success": False,
                "tool": "file_inspector",
                "error": "No filename provided.",
            }

        direct_path = Path(filename)

        if direct_path.exists() and direct_path.is_file():
            return {
                "success": True,
                "tool": "file_inspector",
                "path": str(direct_path),
            }

        temp_directory = Path(os.environ.get("TEMP", ""))

        if temp_directory.exists():
            try:
                for path in temp_directory.rglob(filename):
                    if path.is_file():
                        return {
                            "success": True,
                            "tool": "file_inspector",
                            "path": str(path),
                        }
            except (PermissionError, OSError):
                pass

        return {
            "success": False,
            "tool": "file_inspector",
            "error": f"File '{filename}' was not found.",
        }

    def analyze_log_content(self, content):
        """
        Analyze log messages by their explicit log level.
        """

        errors = []
        warnings = []
        info = []

        for line in content.splitlines():
            stripped = line.strip()

            if not stripped:
                continue

            upper_line = stripped.upper()

            if upper_line.startswith("ERROR"):
                errors.append(stripped)

            elif upper_line.startswith("WARNING"):
                warnings.append(stripped)

            elif upper_line.startswith("INFO"):
                info.append(stripped)

        return {
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "info_count": len(info),
            "has_errors": len(errors) > 0,
            "has_warnings": len(warnings) > 0,
        }

    def inspect(self, file_path):
        """
        Inspect a file without modifying it.
        """

        path = Path(file_path)

        if not path.exists():
            return {
                "success": False,
                "tool": "file_inspector",
                "error": "File does not exist.",
            }

        if not path.is_file():
            return {
                "success": False,
                "tool": "file_inspector",
                "error": "The provided path is not a file.",
            }

        try:
            stat = path.stat()

            size_bytes = stat.st_size
            size_mb = round(size_bytes / (1024 ** 2), 2)
            extension = path.suffix.lower()

            metadata = {
                "name": path.name,
                "path": str(path),
                "extension": extension or "[none]",
                "size_bytes": size_bytes,
                "size_mb": size_mb,
            }

        except OSError as error:
            return {
                "success": False,
                "tool": "file_inspector",
                "error": str(error),
            }

        # Binary
        if extension in self.BINARY_EXTENSIONS:
            return {
                "success": True,
                "tool": "file_inspector",
                "data": {
                    "type": "binary",
                    "metadata": metadata,
                    "message": (
                        "This is a binary file. "
                        "Its raw contents should not "
                        "be displayed as normal text."
                    ),
                },
            }

        # Large text
        if (
            extension in self.TEXT_EXTENSIONS
            and size_mb > self.MAX_TEXT_SIZE_MB
        ):
            return {
                "success": True,
                "tool": "file_inspector",
                "data": {
                    "type": "large_text",
                    "metadata": metadata,
                    "message": (
                        "This is a text-based file, "
                        "but it is too large to load completely."
                    ),
                },
            }

        # Text
        if extension in self.TEXT_EXTENSIONS:
            try:
                with open(
                    path,
                    "r",
                    encoding="utf-8-sig",
                    errors="replace",
                ) as file:
                    content = file.read()

                data = {
                    "type": "text",
                    "metadata": metadata,
                    "content": content,
                }

                # Log-specific structured analysis
                if extension == ".log":
                    analysis = self.analyze_log_content(content)

                    data["analysis"] = analysis

                    # Explicit machine-readable error result
                    if analysis["has_errors"]:
                        data["error_summary"] = (
                            f"There are {analysis['error_count']} "
                            f"error(s) in the file."
                        )
                    else:
                        data["error_summary"] = (
                            "There are no errors in the file."
                        )

                return {
                    "success": True,
                    "tool": "file_inspector",
                    "data": data,
                }

            except (PermissionError, OSError) as error:
                return {
                    "success": False,
                    "tool": "file_inspector",
                    "error": f"Unable to read file: {error}",
                }

        # Unknown
        return {
            "success": True,
            "tool": "file_inspector",
            "data": {
                "type": "unknown",
                "metadata": metadata,
                "message": (
                    "The file type is not recognized "
                    "as a standard text format. "
                    "Only metadata was inspected."
                ),
            },
        }