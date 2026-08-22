"""LocalCleaner unit tests.

The cleaner only ever executes an explicitly approved
snapshot set. Every test proves fail-safe behavior.
"""

import os
import time

import pytest

from tools.storage.cleaner import LocalCleaner


MB = 1024 * 1024

DAYS = 60 * 60 * 24


def make_old_tmp(directory, name, size_bytes=2 * MB):
    """
    Create a file that classifies as a SAFE cleanup
    candidate: .tmp, older than 3 days, larger than 1 MB.
    """

    path = directory / name
    path.write_bytes(b"T" * size_bytes)

    old = time.time() - 10 * DAYS
    os.utime(path, (old, old))

    return path


def snapshot(path):
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
    }


@pytest.fixture()
def cleaner():
    return LocalCleaner()


# =========================================================
# HAPPY PATH
# =========================================================


class TestApprovedDeletion:

    def test_exact_approved_file_is_deleted(
        self,
        cleaner,
        tmp_path,
    ):
        target = make_old_tmp(tmp_path, "junk1.tmp")
        size = target.stat().st_size

        result = cleaner.delete_approved(
            [snapshot(target)]
        )

        assert result["success"] is True
        assert result["tool"] == "cleanup_delete"
        assert result["data"]["deleted_count"] == 1
        assert result["data"]["freed_bytes"] == size
        assert not target.exists()

    def test_freed_bytes_reported(self, cleaner, tmp_path):
        a = make_old_tmp(tmp_path, "a.tmp", MB)
        b = make_old_tmp(tmp_path, "b.tmp", 3 * MB)

        result = cleaner.delete_approved(
            [snapshot(a), snapshot(b)]
        )

        assert result["data"]["freed_bytes"] == 4 * MB
        assert not a.exists()
        assert not b.exists()


# =========================================================
# FAIL-SAFE VERIFICATION
# =========================================================


class TestFailSafeVerification:

    def test_missing_file_is_skipped_not_deleted(
        self,
        cleaner,
        tmp_path,
    ):
        gone = make_old_tmp(tmp_path, "gone.tmp")
        keep = make_old_tmp(tmp_path, "keep.tmp")

        approved = [snapshot(gone), snapshot(keep)]
        gone.unlink()

        result = cleaner.delete_approved(approved)

        skipped = result["data"]["skipped"]

        assert result["data"]["deleted_count"] == 1
        assert len(skipped) == 1
        assert "no longer exists" in (
            skipped[0]["reason"].lower()
        )
        assert not keep.exists()

    def test_changed_size_fails_safely(
        self,
        cleaner,
        tmp_path,
    ):
        target = make_old_tmp(tmp_path, "grew.tmp")
        approved = [snapshot(target)]

        with open(target, "ab") as handle:
            handle.write(b"extra data")

        result = cleaner.delete_approved(approved)

        assert result["data"]["deleted_count"] == 0
        assert target.exists()
        assert "size mismatch" in str(result).lower()

    def test_changed_mtime_fails_safely(
        self,
        cleaner,
        tmp_path,
    ):
        target = make_old_tmp(tmp_path, "touched.tmp")
        approved = [snapshot(target)]

        now = time.time()
        os.utime(target, (now, now))

        result = cleaner.delete_approved(approved)

        assert result["data"]["deleted_count"] == 0
        assert target.exists()
        assert "time mismatch" in str(result).lower()

    def test_protected_extension_never_executes(
        self,
        cleaner,
        tmp_path,
    ):
        # Old + large, but an executable: never safe.

        exe = tmp_path / "installer.exe"
        exe.write_bytes(b"M" * (2 * MB))

        old = time.time() - 10 * DAYS
        os.utime(exe, (old, old))

        result = cleaner.delete_approved([snapshot(exe)])

        assert result["data"]["deleted_count"] == 0
        assert exe.exists()

    def test_review_log_files_cannot_be_deleted(
        self,
        cleaner,
        tmp_path,
    ):
        log = tmp_path / "system.log"
        log.write_bytes(b"L" * (2 * MB))

        old = time.time() - 10 * DAYS
        os.utime(log, (old, old))

        result = cleaner.delete_approved([snapshot(log)])

        assert result["data"]["deleted_count"] == 0
        assert log.exists()

    def test_directory_paths_are_refused(self, cleaner, tmp_path):
        folder = tmp_path / "not_a_file"
        folder.mkdir()

        result = cleaner.delete_approved(
            [
                {
                    "path": str(folder),
                    "size_bytes": 0,
                    "mtime": 0,
                }
            ]
        )

        assert result["data"]["deleted_count"] == 0
        assert folder.exists()

    def test_sensitive_paths_are_refused(self, cleaner, tmp_path):
        secret = tmp_path / "token.json"
        secret.write_text("SECRET CONTENT")

        result = cleaner.delete_approved(
            [
                {
                    "path": str(secret),
                    "size_bytes": secret.stat().st_size,
                    "mtime": secret.stat().st_mtime,
                }
            ]
        )

        assert result["data"]["deleted_count"] == 0
        assert secret.exists()

    def test_symlinks_are_refused(self, cleaner, tmp_path):
        real = make_old_tmp(tmp_path, "real.tmp")
        link = tmp_path / "link.tmp"

        try:
            os.symlink(real, link)
        except OSError:
            pytest.skip("symlink not permitted here")

        result = cleaner.delete_approved(
            [snapshot(link)]
        )

        assert result["data"]["deleted_count"] == 0
        assert link.exists() or not link.is_symlink()

    def test_duplicate_approval_entries_execute_once(
        self,
        cleaner,
        tmp_path,
    ):
        target = make_old_tmp(tmp_path, "dup.tmp")
        snap = snapshot(target)

        result = cleaner.delete_approved([snap, dict(snap)])

        assert result["data"]["deleted_count"] == 1
        assert result["success"] is True
        assert not target.exists()


# =========================================================
# CONTRACT
# =========================================================


class TestContract:

    def test_empty_approval_list_is_rejected(self, cleaner):
        result = cleaner.delete_approved([])

        assert result["success"] is False
        assert "error" in result

    def test_non_list_input_rejected(self, cleaner):
        result = cleaner.delete_approved("junk.tmp")

        assert result["success"] is False

    def test_every_item_resolved_in_report(
        self,
        cleaner,
        tmp_path,
    ):
        good = make_old_tmp(tmp_path, "good.tmp")
        bad = make_old_tmp(tmp_path, "bad.tmp")

        approved = [snapshot(good), snapshot(bad)]
        bad.unlink()

        result = cleaner.delete_approved(approved)

        data = result["data"]

        assert (
            data["deleted_count"]
            + data["skipped_count"]
            == 2
        )
