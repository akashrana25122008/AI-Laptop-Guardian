"""Cleanup tool preview-only guarantees.

The cleanup tool must remain strictly read-only:
scan and classify only, never delete.
"""

import inspect as python_inspect

import pytest

from tools.cleanup.cleanup import CleanupTool


@pytest.fixture()
def cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path))
    return CleanupTool()


def make_file(directory, name, size_bytes):
    path = directory / name
    path.write_bytes(b"x" * size_bytes)
    return path


# =========================================================
# NO DESTRUCTIVE CAPABILITY
# =========================================================


class TestNoDestructiveCapability:

    def test_class_has_no_delete_like_methods(self):
        forbidden_prefixes = (
            "delete",
            "remove",
            "purge",
            "clean_",
            "wipe",
            "execute",
        )

        methods = [
            name
            for name, _ in python_inspect.getmembers(
                CleanupTool,
                predicate=python_inspect.isfunction,
            )
            if not name.startswith("__")
        ]

        destructive = [
            method
            for method in methods
            if method.lower().startswith(
                forbidden_prefixes
            )
        ]

        assert destructive == []

    def test_module_never_imports_deletion_primitives(self):
        import tools.cleanup.cleanup as module

        source = python_inspect.getsource(module)

        for primitive in (
            "os.remove",
            "os.unlink",
            "os.rmdir",
            "shutil.rmtree",
            "Path.unlink",
        ):
            assert primitive not in source


# =========================================================
# PREVIEW NEVER MODIFIES FILES
# =========================================================


class TestPreviewNeverDeletes:

    def test_scan_and_preview_preserve_all_files(
        self,
        cleanup,
        tmp_path,
    ):
        created = [
            make_file(tmp_path, "old.tmp", 2 * 1024 * 1024),
            make_file(tmp_path, "app.log", 2 * 1024 * 1024),
            make_file(tmp_path, "tool.exe", 1024),
            make_file(
                tmp_path,
                "random.dat",
                4096,
            ),
        ]

        scan_result = cleanup.scan()
        preview_result = cleanup.preview()

        assert scan_result["success"] is True
        assert preview_result["success"] is True
        assert (
            preview_result["tool"]
            == "cleanup_preview"
        )

        for path in created:
            assert path.exists(), (
                f"PREVIEW DELETED A FILE: {path.name}"
            )

    def test_preview_report_structure_is_preserved(
        self,
        cleanup,
        tmp_path,
    ):
        make_file(tmp_path, "old.tmp", 2 * 1024 * 1024)

        report = cleanup.preview()

        data = report["data"]

        for key in (
            "total_files",
            "total_size_mb",
            "safe_candidates",
            "review_files",
            "protected_files",
            "locked_files",
            "unknown_files",
            "candidates",
        ):
            assert key in data

        assert data["total_files"] >= 1

    def test_failure_results_carry_both_fields(self):
        broken = CleanupTool()
        broken.user_temp = None

        result = broken.scan()

        assert result["success"] is False
        assert "error" in result
        assert "message" in result
