import os
import time
from pathlib import Path

from tools.file_inspector.inspector import FileInspector
from tools.cleanup.cleanup import CleanupTool


class LocalCleaner:
    """
    Executes ONLY an explicitly approved set of files.

    Safety architecture:

        - Deletion is never triggered by this class
          spontaneously. It requires an approved snapshot:
          the exact list produced by a cleanup preview and
          confirmed through agent.action_safety.

        - Every item is re-verified immediately before
          removal:

              * must be a regular file (no directories,
                no symlinks),
              * must NOT match the sensitive-path policy,
              * must still classify as a safe candidate,
              * size and modification time must match the
                approved snapshot exactly.

        - Any mismatch fails safely for THAT file only;
          other approved files are unaffected.

        - Nothing outside the approved snapshot can ever be
          removed, even if similar files appeared later.
    """

    def __init__(self):
        self.classifier = CleanupTool()
        self.inspector = FileInspector()

    # =====================================================
    # VERIFICATION
    # =====================================================

    def _normalize_path(self, path):
        return os.path.normcase(
            str(Path(path).resolve())
        )

    def _classify_current_state(self, path):
        """
        Classify the file AS IT IS NOW using the shared,
        deterministic cleanup rules.
        """

        stat = path.stat()

        age_days = (
            time.time() - stat.st_mtime
        ) / (60 * 60 * 24)

        return self.classifier.classify_file(
            {
                "path": str(path),
                "name": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "size_mb": round(
                    stat.st_size / (1024 ** 2),
                    2,
                ),
                "age_days": round(age_days, 1),
            }
        )

    def _verify_item(self, item):
        """
        Verify one approved item against current reality.

        Returns (ok, reason, path).
        """

        if not isinstance(item, dict):
            return False, "Invalid approval entry.", None

        raw_path = item.get("path")

        if not raw_path or not str(raw_path).strip():
            return False, "No path in approval.", None

        try:
            path = Path(str(raw_path))
        except (TypeError, ValueError):
            return False, "Invalid path.", None

        if path.is_symlink():
            return False, "Refusing symlink.", path

        if not path.exists():
            return False, "File no longer exists.", path

        if not path.is_file():
            return (
                False,
                "Not a regular file.",
                path,
            )

        if self.inspector._is_sensitive_path(path):
            return (
                False,
                "Protected path.",
                path,
            )

        try:
            stat = path.stat()

            expected_size = item.get("size_bytes")

            if (
                expected_size is None
                or stat.st_size != expected_size
            ):
                return (
                    False,
                    "File changed since approval "
                    "(size mismatch).",
                    path,
                )

            expected_mtime = item.get("mtime")

            if (
                expected_mtime is None
                or stat.st_mtime != expected_mtime
            ):
                return (
                    False,
                    "File changed since approval "
                    "(modified time mismatch).",
                    path,
                )

            classification = (
                self._classify_current_state(path)
            )

            if classification.get("status") != "safe":
                return (
                    False,
                    "No longer classified as a safe "
                    f"candidate ({classification.get('status')}).",
                    path,
                )

        except OSError as error:
            return (
                False,
                f"Inaccessible: {error}",
                path,
            )

        return True, "ok", path

    # =====================================================
    # APPROVED DELETION
    # =====================================================

    def delete_approved(self, items):
        """
        Delete exactly the approved items.

        Each item must be the snapshot dictionary captured
        when the deletion was proposed:

            {"path": ..., "size_bytes": ..., "mtime": ...}

        Returns a normalized result with a full report.
        """

        if not isinstance(items, list) or not items:
            return {
                "success": False,
                "tool": "cleanup_delete",
                "error": (
                    "No approved cleanup items "
                    "were provided."
                ),
            }

        seen_paths = set()
        deleted = []
        skipped = []
        freed_bytes = 0

        for item in items:

            ok, reason, path = self._verify_item(item)

            if not ok:

                skipped.append(
                    {
                        "path": (
                            str(path)
                            if path is not None
                            else str(
                                item.get("path", "")
                                if isinstance(item, dict)
                                else ""
                            )
                        ),
                        "reason": reason,
                    }
                )

                continue

            normalized = self._normalize_path(path)

            if normalized in seen_paths:
                skipped.append(
                    {
                        "path": str(path),
                        "reason": (
                            "Duplicate approval entry."
                        ),
                    }
                )
                continue

            seen_paths.add(normalized)

            try:
                size = path.stat().st_size

                os.remove(path)

            except OSError as error:
                skipped.append(
                    {
                        "path": str(path),
                        "reason": (
                            f"Could not remove: {error}"
                        ),
                    }
                )
                continue

            deleted.append(
                {
                    "path": str(path),
                    "size_bytes": size,
                }
            )

            freed_bytes += size

        resolved_all = (
            len(deleted) + len(skipped)
            == len(items)
        )

        result = {
            "success": resolved_all,
            "tool": "cleanup_delete",
            "data": {
                "deleted_count": len(deleted),
                "skipped_count": len(skipped),
                "freed_bytes": freed_bytes,
                "freed_mb": round(
                    freed_bytes / (1024 ** 2),
                    2,
                ),
                "deleted": deleted,
                "skipped": skipped,
            },
        }

        if not deleted and skipped:
            result["message"] = (
                "Nothing was deleted. Every approved "
                "file failed the final safety check."
            )

        elif deleted and skipped:
            result["message"] = (
                f"Deleted {len(deleted)} file(s), "
                f"freed {result['data']['freed_mb']} MB. "
                f"{len(skipped)} file(s) were skipped "
                f"because they changed or disappeared."
            )

        elif deleted:
            result["message"] = (
                f"Deleted {len(deleted)} file(s) and "
                f"freed {result['data']['freed_mb']} MB."
            )

        return result
