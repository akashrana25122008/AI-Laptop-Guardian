import os
from pathlib import Path


class LargeFileScanner:
    """
    Scans common user folders for large files.
    """

    def __init__(self, min_size_mb=500):
        self.min_size_bytes = min_size_mb * 1024 * 1024

    def get_scan_locations(self):
        """
        Returns common user folders.
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

    def scan(self):
        """
        Returns a list of large files.
        """
        results = []

        for folder in self.get_scan_locations():

            for root, dirs, files in os.walk(folder):

                for file in files:

                    try:
                        file_path = os.path.join(root, file)

                        size = os.path.getsize(file_path)

                        if size >= self.min_size_bytes:

                            results.append({
                                "name": file,
                                "path": file_path,
                                "size_gb": round(size / (1024 ** 3), 2)
                            })

                    except (PermissionError, FileNotFoundError):
                        continue

        results.sort(
            key=lambda file: file["size_gb"],
            reverse=True
        )

        return results