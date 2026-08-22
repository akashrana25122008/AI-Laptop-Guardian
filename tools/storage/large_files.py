import os
from pathlib import Path

from tools.file_inspector.inspector import FileInspector


class LargeFileScanner:
    """
    Scans common user folders for large files.

    Safety properties:

        - Never reads file contents.
        - Never modifies anything.
        - Skips symlinks and junctions.
        - Excludes sensitive files (credentials, keys,
          tokens) by deterministic path policy.
        - Handles inaccessible files/folders gracefully.
    """

    def __init__(self, min_size_mb=500):
        self.min_size_bytes = min_size_mb * 1024 * 1024

    def get_scan_locations(self):
        """
        Returns common user folders.
        Tests may inject their own sandbox folders.
        """
        home = Path.home()

        folders = [
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
            home / "Pictures",
            home / "Videos",
        ]

        return [folder for folder in folders if folder.exists()]

    def scan(self, folders=None):
        """
        Returns a list of large files, largest first.

        `folders` allows callers (and tests) to restrict the
        scan to specific directories. Defaults to the
        standard user folders.
        """

        if folders is not None:
            locations = [
                Path(folder)
                for folder in folders
                if Path(folder).exists()
            ]

        else:
            locations = self.get_scan_locations()

        inspector = FileInspector()

        results = []

        for folder in locations:

            try:

                for root, dirs, files in os.walk(folder):

                    # Do not descend into links/junctions.

                    dirs[:] = [
                        d
                        for d in dirs
                        if not (
                            Path(root) / d
                        ).is_symlink()
                    ]

                    for file in files:

                        try:
                            file_path = Path(root) / file

                            if file_path.is_symlink():
                                continue

                            if (
                                inspector._is_sensitive_path(
                                    file_path
                                )
                            ):
                                continue

                            size = file_path.stat().st_size

                            if size >= self.min_size_bytes:

                                results.append({
                                    "name": file,
                                    "path": str(file_path),
                                    "size_gb": round(
                                        size / (1024 ** 3),
                                        2,
                                    ),
                                    "size_mb": round(
                                        size / (1024 ** 2),
                                        2,
                                    ),
                                    "size_bytes": size,
                                })

                        except (
                            PermissionError,
                            FileNotFoundError,
                            OSError,
                        ):
                            continue

            except (
                PermissionError,
                FileNotFoundError,
                OSError,
            ):
                continue

        results.sort(
            key=lambda file: file["size_gb"],
            reverse=True
        )

        return results
