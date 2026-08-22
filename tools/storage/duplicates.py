import hashlib
import os
from pathlib import Path

from tools.file_inspector.inspector import FileInspector


class DuplicateFileScanner:
    """
    Safe duplicate-file detector.

    Strategy (deterministic, read-only):

        1. Collect files from known user folders.
        2. Group candidates by exact file size.
        3. Hash only same-size candidates.
        4. Files with identical size AND identical hash
           form one duplicate group.

    This tool NEVER deletes, moves or renames anything.
    Sensitive files are excluded by name/path policy and
    are never opened.
    """

    HASH_CHUNK_BYTES = 64 * 1024

    def __init__(self, folders=None):
        self.folders = folders

    # =====================================================
    # LOCATIONS
    # =====================================================

    def get_scan_locations(self):
        """
        Returns common user folders.
        Tests may inject their own sandbox folders.
        """

        if self.folders is not None:
            return [
                Path(folder)
                for folder in self.folders
                if Path(folder).exists()
            ]

        home = Path.home()

        folders = [
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
            home / "Pictures",
            home / "Videos",
        ]

        return [folder for folder in folders if folder.exists()]

    # =====================================================
    # COLLECTION
    # =====================================================

    def _collect_files(self):
        """
        Walk scan locations and collect safe regular files.

        Skips:
            - sensitive paths (never opened),
            - symlinks / junctions,
            - inaccessible entries.
        """

        inspector = FileInspector()

        collected = []
        skipped_sensitive = 0
        inaccessible = 0

        for folder in self.get_scan_locations():

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

                    for filename in files:

                        path = Path(root) / filename

                        try:

                            if path.is_symlink():
                                continue

                            if (
                                inspector._is_sensitive_path(
                                    path
                                )
                            ):
                                skipped_sensitive += 1
                                continue

                            if not path.is_file():
                                continue

                            size = path.stat().st_size

                            collected.append(
                                {
                                    "path": str(path),
                                    "name": filename,
                                    "size_bytes": size,
                                }
                            )

                        except OSError:
                            inaccessible += 1
                            continue

            except OSError:
                continue

        return {
            "files": collected,
            "skipped_sensitive": skipped_sensitive,
            "inaccessible": inaccessible,
        }

    # =====================================================
    # HASHING
    # =====================================================

    def _hash_file(self, path):
        """
        Stream-hash a file without loading it fully into
        memory. Contents never leave this function.
        """

        digest = hashlib.sha256()

        with open(path, "rb") as handle:

            while True:

                chunk = handle.read(
                    self.HASH_CHUNK_BYTES
                )

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    # =====================================================
    # SCAN
    # =====================================================

    def scan(self):
        """
        Find duplicate groups.

        Returns a normalized result. Nothing is modified.
        """

        collection = self._collect_files()

        files = collection["files"]

        # -----------------------------------------------------
        # Group by size first: cheap, no content access.
        # -----------------------------------------------------

        by_size = {}

        for entry in files:
            by_size.setdefault(
                entry["size_bytes"],
                [],
            ).append(entry)

        candidate_sizes = [
            size
            for size, group in by_size.items()
            if len(group) > 1
        ]

        # -----------------------------------------------------
        # Hash only same-size candidates.
        # -----------------------------------------------------

        groups_by_content = {}
        hash_failures = 0

        for size in candidate_sizes:

            for entry in by_size[size]:

                try:
                    content_hash = self._hash_file(
                        entry["path"]
                    )

                except OSError:
                    hash_failures += 1
                    continue

                key = (size, content_hash)

                groups_by_content.setdefault(
                    key,
                    [],
                ).append(entry)

        duplicate_groups = []

        wasted_bytes = 0

        for (size, content_hash), members in (
            groups_by_content.items()
        ):

            if len(members) < 2:
                continue

            members_sorted = sorted(
                members,
                key=lambda item: item["path"].lower(),
            )

            duplicate_groups.append(
                {
                    "hash": content_hash,
                    "size_bytes": size,
                    "size_mb": round(
                        size / (1024 ** 2),
                        2,
                    ),
                    "copies": len(members_sorted),
                    "wasted_bytes": size
                    * (len(members_sorted) - 1),
                    "files": [
                        {
                            "name": member["name"],
                            "path": member["path"],
                        }
                        for member in members_sorted
                    ],
                }
            )

            wasted_bytes += size * (
                len(members_sorted) - 1
            )

        duplicate_groups.sort(
            key=lambda group: (
                group["wasted_bytes"],
                group["hash"],
            ),
            reverse=True,
        )

        duplicate_files = sum(
            group["copies"]
            for group in duplicate_groups
        )

        return {
            "success": True,
            "tool": "duplicates",
            "data": {
                "groups": duplicate_groups,
                "group_count": len(duplicate_groups),
                "duplicate_files": duplicate_files,
                "wasted_bytes": wasted_bytes,
                "wasted_mb": round(
                    wasted_bytes / (1024 ** 2),
                    2,
                ),
                "scanned_files": len(files),
                "skipped_sensitive": collection[
                    "skipped_sensitive"
                ],
                "inaccessible": collection[
                    "inaccessible"
                ]
                + hash_failures,
            },
        }
