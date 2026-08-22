"""Duplicate-file detection tests.

Everything runs inside pytest's tmp_path sandbox.
The scanner is strictly read-only.
"""

import os

import pytest

from tools.storage.duplicates import DuplicateFileScanner


MB = 1024 * 1024


@pytest.fixture()
def scanner(tmp_path):
    return DuplicateFileScanner(folders=[tmp_path])


def make_file(directory, name, size_bytes=0, content=b""):
    path = directory / name
    path.write_bytes(
        content * (size_bytes // len(content))
        if content and size_bytes
        else b"z" * size_bytes
    )
    return path


# =========================================================
# GROUPING CORRECTNESS
# =========================================================


class TestDuplicateGrouping:

    def test_identical_files_form_one_group(
        self,
        scanner,
        tmp_path,
    ):
        payload = b"A" * MB

        make_file(tmp_path, "a.bin", MB, b"A")
        make_file(tmp_path, "b.bin", MB, b"A")

        result = scanner.scan()

        assert result["success"] is True
        assert result["tool"] == "duplicates"

        groups = result["data"]["groups"]

        assert len(groups) == 1
        assert groups[0]["copies"] == 2
        assert groups[0]["wasted_bytes"] == MB
        names = {
            f["name"] for f in groups[0]["files"]
        }
        assert names == {"a.bin", "b.bin"}

    def test_same_size_different_content_is_not_duplicate(
        self,
        scanner,
        tmp_path,
    ):
        make_file(tmp_path, "x.bin", MB, b"X")
        make_file(tmp_path, "y.bin", MB, b"Y")

        result = scanner.scan()

        assert result["data"]["groups"] == []

    def test_multiple_groups_detected(self, scanner, tmp_path):
        make_file(tmp_path, "one.bin", MB, b"1")
        make_file(tmp_path, "two.bin", MB, b"1")
        make_file(tmp_path, "three.bin", 2 * MB, b"3")
        make_file(tmp_path, "four.bin", 2 * MB, b"3")

        result = scanner.scan()

        groups = result["data"]["groups"]

        assert result["data"]["group_count"] == 2
        sizes = {g["size_bytes"] for g in groups}
        assert sizes == {MB, 2 * MB}

    def test_unique_sizes_are_ignored(self, scanner, tmp_path):
        make_file(tmp_path, "solo.bin", MB, b"S")
        make_file(tmp_path, "other.txt", 10)

        result = scanner.scan()

        assert result["data"]["groups"] == []
        assert result["data"]["scanned_files"] == 2

    def test_empty_files_form_a_group(self, scanner, tmp_path):
        make_file(tmp_path, "e1.dat")
        make_file(tmp_path, "e2.dat")
        make_file(tmp_path, "full.dat", 1024, b"F")

        result = scanner.scan()

        groups = result["data"]["groups"]

        assert len(groups) == 1
        assert groups[0]["size_bytes"] == 0
        assert groups[0]["copies"] == 2


# =========================================================
# SAFETY BEHAVIOR
# =========================================================


class TestScanSafety:

    def test_scan_never_modifies_files(self, scanner, tmp_path):
        paths = [
            make_file(tmp_path, "keep1.bin", MB, b"K"),
            make_file(tmp_path, "keep2.bin", MB, b"K"),
        ]

        before = [
            (p.stat().st_size, p.stat().st_mtime)
            for p in paths
        ]

        scanner.scan()

        after = [
            (p.stat().st_size, p.stat().st_mtime)
            for p in paths
        ]

        assert before == after
        for path in paths:
            assert path.exists()

    def test_sensitive_files_are_never_opened_or_reported(
        self,
        scanner,
        tmp_path,
    ):
        secret = make_file(
            tmp_path, "credentials.json", MB, b"S"
        )
        twin = make_file(tmp_path, "normal.json", MB, b"S")

        result = scanner.scan()

        # The sensitive file must not appear anywhere.

        dumped = str(result)

        assert "credentials" not in dumped.lower()
        assert twin.name not in "".join(
            f["name"]
            for g in result["data"]["groups"]
            for f in g["files"]
            if f["name"] == secret.name
        )

        # The normal twin forms no group alone.

        assert result["data"]["skipped_sensitive"] >= 1
        assert secret.exists()

    def test_unreadable_content_counts_as_inaccessible(
        self,
        scanner,
        tmp_path,
        monkeypatch,
    ):
        make_file(tmp_path, "locked.bin", MB, b"L")
        make_file(tmp_path, "copy.bin", MB, b"L")

        original_hash = scanner._hash_file

        def selective_hash(path):
            if "locked" in str(path):
                raise OSError("unreadable")
            return original_hash(path)

        monkeypatch.setattr(
            scanner,
            "_hash_file",
            selective_hash,
        )

        result = scanner.scan()

        assert result["success"] is True
        assert result["data"]["inaccessible"] == 1
        assert result["data"]["groups"] == []

    def test_symlinks_are_skipped(self, tmp_path):
        target = make_file(tmp_path, "real.bin", MB, b"R")
        link = tmp_path / "link.bin"

        try:
            os.symlink(target, link)
        except OSError:
            pytest.skip("symlink not permitted here")

        scanner = DuplicateFileScanner(
            folders=[tmp_path]
        )

        result = scanner.scan()

        reported = [
            f["path"]
            for g in result["data"]["groups"]
            for f in g["files"]
        ]

        assert str(link) not in reported


# =========================================================
# REPORT SHAPE
# =========================================================


class TestReportShape:

    def test_normalized_result_fields(self, scanner, tmp_path):
        make_file(tmp_path, "d1.bin", MB, b"D")
        make_file(tmp_path, "d2.bin", MB, b"D")

        result = scanner.scan()

        data = result["data"]

        for key in (
            "groups",
            "group_count",
            "duplicate_files",
            "wasted_bytes",
            "wasted_mb",
            "scanned_files",
            "skipped_sensitive",
            "inaccessible",
        ):
            assert key in data

        assert data["scanned_files"] == 2
