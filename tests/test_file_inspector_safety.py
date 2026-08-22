"""Sensitive-path policy tests for the file inspector.

All files are created inside pytest's tmp_path sandbox.
No real user files are ever touched.
"""

import json

import pytest

from tools.file_inspector.inspector import FileInspector
from agent.prompt_safety import render_tool_data


@pytest.fixture()
def inspector():
    return FileInspector()


SENSITIVE_NAMES = [
    "credentials.json",
    "token.json",
    ".env",
    ".env.local",
    "client_secret.txt",
    "password_backup.zip",
    "server.pem",
    "private.key",
    "id_rsa",
    "id_ed25519",
    "backup.pfx",
    "keystore.p12",
]


# =========================================================
# INSPECT: BLOCKED PATHS
# =========================================================


class TestInspectBlocksSensitiveFiles:

    @pytest.mark.parametrize(
        "name",
        SENSITIVE_NAMES,
    )
    def test_sensitive_files_are_refused_before_read(
        self,
        inspector,
        tmp_path,
        name,
    ):
        target = tmp_path / name
        target.write_text("TOP SECRET", encoding="utf-8")

        result = inspector.inspect(str(target))

        assert result["success"] is False
        assert result["tool"] == "file_inspector"
        assert (
            result.get("blocked_reason")
            == "sensitive_path"
        )

    def test_blocked_result_never_leaks_the_path(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "credentials.json"
        target.write_text("TOP SECRET", encoding="utf-8")

        result = inspector.inspect(str(target))

        assert str(tmp_path) not in json.dumps(result)
        assert target.name not in result.get(
            "error", ""
        )

    def test_ssh_directory_contents_are_refused(
        self,
        inspector,
        tmp_path,
    ):
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir()

        target = ssh_dir / "my_server_key"
        target.write_text("KEY MATERIAL", encoding="utf-8")

        result = inspector.inspect(str(target))

        assert result["success"] is False
        assert (
            result.get("blocked_reason")
            == "sensitive_path"
        )


# =========================================================
# INSPECT: ALLOWED FILES
# =========================================================


class TestInspectStillWorksForNormalFiles:

    def test_normal_text_file_is_inspectable(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "notes.txt"
        target.write_text("hello world", encoding="utf-8")

        result = inspector.inspect(str(target))

        assert result["success"] is True
        assert result["data"]["type"] == "text"
        assert (
            result["data"]["content"]
            == "hello world"
        )

    def test_missing_file_reports_absence_not_blocking(
        self,
        inspector,
        tmp_path,
    ):
        missing = tmp_path / "ghost.txt"

        result = inspector.inspect(str(missing))

        assert result["success"] is False
        assert "blocked_reason" not in result
        assert "does not exist" in result["error"]

    def test_binary_file_stays_metadata_only(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "program.exe"
        target.write_bytes(b"MZ\x90\x00binary")

        result = inspector.inspect(str(target))

        assert result["success"] is True
        assert result["data"]["type"] == "binary"

    def test_oversized_text_is_not_loaded_completely(
        self,
        inspector,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            inspector,
            "MAX_TEXT_SIZE_MB",
            0.001,
        )

        target = tmp_path / "big.log"
        # size_mb is rounded to 2 decimals; 20 KB rounds to
        # 0.02 MB, which exceeds the patched 0.001 MB limit.
        target.write_text(
            "x" * 20480,
            encoding="utf-8",
        )

        result = inspector.inspect(str(target))

        assert result["success"] is True
        assert result["data"]["type"] == "large_text"


# =========================================================
# PROMPT SAFETY INTEGRATION
# =========================================================


class TestBlockedResultsNeverReachPrompts:

    def test_rendered_failure_contains_no_secret_path(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "token.json"
        target.write_text("TOP SECRET", encoding="utf-8")

        result = inspector.inspect(str(target))

        rendered = render_tool_data(result)

        assert str(tmp_path) not in rendered

    def test_find_file_refuses_existing_sensitive_file(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "credentials.json"
        target.write_text("TOP SECRET", encoding="utf-8")

        result = inspector.find_file(str(target))

        assert result["success"] is False
        assert (
            result.get("blocked_reason")
            == "sensitive_path"
        )

    def test_find_file_still_finds_normal_files(
        self,
        inspector,
        tmp_path,
    ):
        target = tmp_path / "report.txt"
        target.write_text("data", encoding="utf-8")

        result = inspector.find_file(str(target))

        assert result["success"] is True
        assert result["path"] == str(target)
