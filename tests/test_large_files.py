"""Large-file scanner tests (read-only, sandboxed)."""

import os
from pathlib import Path

import pytest

import tools.storage.large_files as large_files_module
from tools.storage.large_files import LargeFileScanner


MB = 1024 * 1024


@pytest.fixture()
def scanner():
    return LargeFileScanner(min_size_mb=1)


def make_file(directory, name, size_bytes):
    path = directory / name
    path.write_bytes(b"L" * size_bytes)
    return path


class TestThresholdBehavior:

    def test_files_at_or_above_threshold_are_reported(
        self,
        scanner,
        tmp_path,
    ):
        big = make_file(tmp_path, "big.bin", 2 * MB)
        exact = make_file(tmp_path, "exact.bin", MB)
        small = make_file(tmp_path, "small.bin", MB - 1)

        result = scanner.scan(folders=[str(tmp_path)])

        names = {f["name"] for f in result}

        assert "big.bin" in names
        assert "exact.bin" in names
        assert "small.bin" not in names

        assert big.exists()
        assert exact.exists()
        assert small.exists()

    def test_results_sorted_largest_first(
        self,
        scanner,
        tmp_path,
    ):
        make_file(tmp_path, "mid.bin", 2 * MB)
        make_file(tmp_path, "huge.bin", 3 * MB)

        result = scanner.scan(folders=[str(tmp_path)])

        sizes = [f["size_gb"] for f in result]

        assert sizes == sorted(sizes, reverse=True)


class TestSafetyBehavior:

    def test_sensitive_files_never_listed(self, scanner, tmp_path):
        make_file(tmp_path, "credentials.json", 5 * MB)
        make_file(tmp_path, "movie.bin", 2 * MB)

        result = scanner.scan(folders=[str(tmp_path)])

        names = {f["name"] for f in result}

        assert "credentials.json" not in names
        assert "movie.bin" in names

    def test_scan_never_opens_any_file(
        self,
        scanner,
        tmp_path,
        monkeypatch,
    ):
        make_file(tmp_path, "data.bin", 2 * MB)

        def no_open(*args, **kwargs):
            raise AssertionError(
                "Scanner attempted to open file contents."
            )

        monkeypatch.setattr(
            "builtins.open",
            no_open,
        )
        monkeypatch.setattr(
            os,
            "open",
            no_open,
            raising=False,
        )

        result = scanner.scan(folders=[str(tmp_path)])

        assert result[0]["name"] == "data.bin"

    def test_inaccessible_files_are_skipped_not_fatal(
        self,
        scanner,
        tmp_path,
        monkeypatch,
    ):
        make_file(tmp_path, "good.bin", 2 * MB)
        locked = make_file(tmp_path, "locked.bin", 2 * MB)

        real_stat = Path.stat

        def selective_stat(self, *args, **kwargs):
            if self.name == "locked.bin":
                raise PermissionError("denied")
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", selective_stat)

        result = scanner.scan(folders=[str(tmp_path)])

        names = {f["name"] for f in result}

        assert names == {"good.bin"}
        # os.path.exists bypasses the patched Path.stat.
        assert os.path.exists(str(locked))

    def test_inaccessible_folder_is_skipped(self, scanner):
        result = scanner.scan(folders=["Z:\\definitely-missing"])

        assert result == []

    def test_report_includes_sizes(self, scanner, tmp_path):
        make_file(tmp_path, "one.bin", MB + 512)

        result = scanner.scan(folders=[str(tmp_path)])

        entry = result[0]

        for key in (
            "name",
            "path",
            "size_gb",
            "size_mb",
            "size_bytes",
        ):
            assert key in entry

        assert entry["size_bytes"] == MB + 512
