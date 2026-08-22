from types import SimpleNamespace

import pytest

from tools.storage import scanner as scanner_module
from tools.storage.scanner import StorageScanner


GIB = 1024 ** 3


@pytest.mark.parametrize(
    ("usage", "expected_status"),
    [(0, "Healthy"), (69.99, "Healthy"), (70, "Warning"), (89.99, "Warning"), (90, "Critical")],
)
def test_get_drive_status_uses_expected_thresholds(usage, expected_status):
    assert StorageScanner().get_drive_status(usage) == expected_status


def test_get_drive_info_collects_accessible_drives_and_skips_inaccessible_ones(monkeypatch):
    partitions = [
        SimpleNamespace(device="C:", mountpoint="C:\\"),
        SimpleNamespace(device="D:", mountpoint="D:\\"),
    ]
    usage = SimpleNamespace(total=100 * GIB, used=75 * GIB, free=25 * GIB, percent=75.0)
    monkeypatch.setattr(scanner_module.psutil, "disk_partitions", lambda: partitions)

    def disk_usage(mountpoint):
        if mountpoint == "D:\\":
            raise PermissionError("not accessible")
        return usage

    monkeypatch.setattr(scanner_module.psutil, "disk_usage", disk_usage)

    assert StorageScanner().get_drive_info() == [{
        "drive": "C:",
        "mount": "C:\\",
        "total_gb": 100.0,
        "used_gb": 75.0,
        "free_gb": 25.0,
        "percent_used": 75.0,
        "status": "Warning",
    }]


def test_get_folder_size_ignores_unreadable_files(monkeypatch):
    monkeypatch.setattr(scanner_module.os.path, "exists", lambda path: True)
    monkeypatch.setattr(
        scanner_module.os,
        "walk",
        lambda path: [("C:\\temp", [], ["first.tmp", "missing.tmp"])],
    )

    def getsize(path):
        if path.endswith("missing.tmp"):
            raise FileNotFoundError(path)
        return 3 * GIB

    monkeypatch.setattr(scanner_module.os.path, "getsize", getsize)

    assert StorageScanner().get_folder_size("C:\\temp") == 3.0


def test_get_temp_files_size_uses_configured_user_temp(monkeypatch):
    scanner = StorageScanner()
    monkeypatch.setenv("TEMP", "C:\\UserTemp")
    sizes = {"C:\\UserTemp": 1.25, r"C:\Windows\Temp": 2.5}
    monkeypatch.setattr(scanner, "get_folder_size", lambda path: sizes[path])

    assert scanner.get_temp_files_size() == {
        "user_temp_gb": 1.25,
        "windows_temp_gb": 2.5,
    }
