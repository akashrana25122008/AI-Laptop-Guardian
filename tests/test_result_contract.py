"""Tests for the shared result contract helpers."""

import pytest

from agent.result_contract import (
    MAX_ERROR_LENGTH,
    ensure_result,
    is_successful_result,
    sanitize_error,
)


# =========================================================
# sanitize_error
# =========================================================


class TestSanitizeError:

    def test_plain_string_passes_through(self):
        assert sanitize_error("disk full") == "disk full"

    def test_exception_becomes_type_and_message(self):
        error = ValueError("bad input")

        result = sanitize_error(error)

        assert result == "ValueError: bad input"

    def test_newlines_are_collapsed(self):
        result = sanitize_error("line one\nline two\r\nline three")

        assert result == "line one line two line three"

    def test_long_errors_are_truncated(self):
        result = sanitize_error("x" * 1000)

        assert len(result) <= MAX_ERROR_LENGTH
        assert result.endswith("...")

    def test_empty_error_gets_placeholder(self):
        assert sanitize_error("") == "Unknown error."
        assert sanitize_error("   \n ") == "Unknown error."


# =========================================================
# is_successful_result
# =========================================================


class TestIsSuccessfulResult:

    def test_true_only_for_explicit_success(self):
        assert is_successful_result({"success": True}) is True

    @pytest.mark.parametrize(
        "result",
        [
            None,
            42,
            "ok",
            {"success": False},
            {"success": "yes"},
            {},
            {"data": {"success": True}},
        ],
    )
    def test_everything_else_is_not_success(self, result):
        assert is_successful_result(result) is False


# =========================================================
# ensure_result
# =========================================================


class TestEnsureResult:

    def test_valid_result_is_returned_unchanged(self):
        original = {
            "success": True,
            "tool": "cpu",
            "data": {"usage_percent": 10},
        }

        assert ensure_result(original, "cpu") is original

    def test_failure_result_is_returned_unchanged(self):
        original = {
            "success": False,
            "tool": "ram",
            "error": "boom",
        }

        assert ensure_result(original, "ram") is original

    def test_dict_without_success_becomes_failure(self):
        raw = {"drives": ["C:\\"]}

        result = ensure_result(raw, "storage")

        assert result["success"] is False
        assert result["tool"] == "storage"
        assert "error" in result
        # Original payload preserved for debugging.
        assert result["data"] is raw

    def test_non_dict_becomes_failure(self):
        for raw in (None, 42, "done", [1, 2]):

            result = ensure_result(raw, "cleanup")

            assert result["success"] is False
            assert result["tool"] == "cleanup"
            assert isinstance(result["error"], str)

    def test_wrapped_never_fakes_success(self):
        assert ensure_result("all good", "cpu")[
            "success"
        ] is False
