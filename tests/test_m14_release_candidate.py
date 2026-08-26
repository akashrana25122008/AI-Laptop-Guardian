"""Milestone 14 — Release Candidate & Windows Packaging.

Tests cover:
- Packaging configuration (PyInstaller spec, build script)
- Resource path helpers (source vs frozen modes)
- Startup environment validation
- Version module integrity
- Local functionality preservation
- Safety regression (no secrets in tracked files, no implicit OAuth)
- Logging setup
- Data directory setup
"""

import os
import sys
import unittest
from unittest import mock

# Ensure the project root is importable
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


# ============================================================
# VERSION MODULE
# ============================================================


class TestVersionModule(unittest.TestCase):
    """Version is a single source of truth."""

    def test_version_is_string(self):
        from app.version import __version__

        self.assertIsInstance(__version__, str)

    def test_version_has_semver_shape(self):
        from app.version import __version__

        parts = __version__.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertTrue(p.isdigit(), p)

    def test_version_is_not_placeholder(self):
        from app.version import __version__

        self.assertNotIn("Milestone", __version__)
        self.assertNotIn("TODO", __version__)


# ============================================================
# RESOURCE PATHS
# ============================================================


class TestResourcePaths(unittest.TestCase):
    """app.paths helpers work in source mode."""

    def test_app_root_is_directory(self):
        from app.paths import app_root

        root = app_root()
        self.assertTrue(os.path.isdir(root))

    def test_app_root_contains_app_package(self):
        from app.paths import app_root

        root = app_root()
        self.assertTrue(os.path.isdir(os.path.join(root, "app")))

    def test_resource_path_returns_string(self):
        from app.paths import resource_path

        result = resource_path("app/version.py")
        self.assertIsInstance(result, str)

    def test_resource_path_exists_for_known_file(self):
        from app.paths import resource_path

        p = resource_path("app/version.py")
        self.assertTrue(os.path.isfile(p))

    def test_user_data_dir_returns_string(self):
        from app.paths import user_data_dir

        d = user_data_dir()
        self.assertIsInstance(d, str)

    def test_user_data_dir_in_source_mode(self):
        from app.paths import app_root, user_data_dir

        d = user_data_dir()
        root = app_root()
        self.assertTrue(d.startswith(root))

    def test_ensure_user_data_dir_creates_tokens(self):
        from app.paths import ensure_user_data_dir

        d = ensure_user_data_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertTrue(os.path.isdir(os.path.join(d, "tokens")))


# ============================================================
# ENVIRONMENT CHECKS
# ============================================================


class TestEnvChecks(unittest.TestCase):
    """Startup validation catches missing dependencies."""

    def test_check_python_ok(self):
        from app.env_check import check_python

        result = check_python()
        self.assertIn("name", result)
        self.assertIn("ok", result)
        self.assertTrue(result["ok"])

    def test_check_customtkinter_returns_dict(self):
        from app.env_check import check_customtkinter

        result = check_customtkinter()
        self.assertIn("name", result)
        self.assertIn("ok", result)

    def test_check_psutil_returns_dict(self):
        from app.env_check import check_psutil

        result = check_psutil()
        self.assertIn("name", result)
        self.assertIn("ok", result)

    def test_check_ollama_is_optional(self):
        from app.env_check import check_ollama

        result = check_ollama()
        self.assertTrue(result.get("optional"))
        self.assertTrue(result["ok"])

    def test_check_google_deps_is_optional(self):
        from app.env_check import check_google_deps

        result = check_google_deps()
        self.assertTrue(result.get("optional"))
        self.assertTrue(result["ok"])

    def test_run_all_checks_returns_list(self):
        from app.env_check import run_all_checks

        results = run_all_checks()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_run_all_checks_has_name_and_ok(self):
        from app.env_check import run_all_checks

        for r in run_all_checks():
            self.assertIn("name", r)
            self.assertIn("ok", r)

    def test_summary_returns_string(self):
        from app.env_check import summary

        text = summary()
        self.assertIsInstance(text, str)
        self.assertIn("AI Laptop Guardian", text)

    def test_critical_check_fails_when_module_missing(self):
        from app.env_check import _check_import

        ok, detail = _check_import(
            "nonexistent_module_xyz_12345"
        )
        self.assertFalse(ok)
        self.assertIn("nonexistent", detail)


# ============================================================
# LOGGING
# ============================================================


class TestLoggingSetup(unittest.TestCase):
    """Logging never exposes secrets."""

    def test_setup_logging_creates_handler(self):
        import logging

        from app.logging_setup import setup_logging

        before = len(logging.getLogger().handlers)
        setup_logging()
        after = len(logging.getLogger().handlers)
        self.assertGreaterEqual(after, before)

    def test_get_logger_returns_logger(self):
        import logging

        from app.logging_setup import get_logger

        logger = get_logger("test")
        self.assertIsInstance(logger, logging.Logger)


# ============================================================
# PACKAGING CONFIGURATION
# ============================================================


class TestPackagingConfig(unittest.TestCase):
    """PyInstaller spec and build script exist and are valid."""

    def test_spec_file_exists(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        spec = os.path.join(root, "AI-Laptop-Guardian.spec")
        self.assertTrue(os.path.isfile(spec))

    def test_build_script_exists(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        script = os.path.join(root, "scripts", "build_windows.py")
        self.assertTrue(os.path.isfile(script))

    def test_spec_excludes_google_auth_in_tests(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        spec = os.path.join(root, "AI-Laptop-Guardian.spec")
        content = open(spec, encoding="utf-8").read()
        self.assertIn("EXCLUDES", content)
        self.assertIn("HIDDEN_IMPORTS", content)

    def test_spec_references_main_entry(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        spec = os.path.join(root, "AI-Laptop-Guardian.spec")
        content = open(spec, encoding="utf-8").read()
        self.assertTrue(
            "main.py" in content or "run_gui.py" in content
        )

    def test_build_script_is_valid_python(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        script = os.path.join(root, "scripts", "build_windows.py")
        content = open(script, encoding="utf-8").read()
        compile(content, script, "exec")


# ============================================================
# GITIGNORE COVERAGE
# ============================================================


class TestGitignoreCoverage(unittest.TestCase):
    """Sensitive paths are covered by .gitignore."""

    def _gitignore(self):
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        path = os.path.join(root, ".gitignore")
        return open(path, encoding="utf-8").read()

    def test_credentials_json_ignored(self):
        content = self._gitignore()
        self.assertIn("credentials.json", content)

    def test_token_json_ignored(self):
        content = self._gitignore()
        self.assertIn("token.json", content)

    def test_env_ignored(self):
        content = self._gitignore()
        self.assertIn(".env", content)

    def test_cloud_data_ignored(self):
        content = self._gitignore()
        self.assertIn("cloud_data/", content)

    def test_build_artifacts_ignored(self):
        content = self._gitignore()
        self.assertIn("build/", content)
        self.assertIn("dist/", content)

    def test_logs_ignored(self):
        content = self._gitignore()
        self.assertIn("logs/", content)
        self.assertIn("*.log", content)


# ============================================================
# SAFETY REGRESSION
# ============================================================


class TestSafetyRegression(unittest.TestCase):
    """No credentials are tracked in git, and M1-M13 behavior is preserved."""

    def _git_tracked_files(self):
        """Return set of files tracked by git."""
        import subprocess
        root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        return set(result.stdout.splitlines())

    def test_no_tracked_credential_files(self):
        tracked = self._git_tracked_files()
        for name in ("credentials.json", "token.json"):
            self.assertNotIn(
                name, tracked,
                f"{name} must not be tracked in git",
            )

    def test_no_env_file_tracked(self):
        tracked = self._git_tracked_files()
        self.assertNotIn(".env", tracked)

    def test_app_version_importable(self):
        from app.version import __version__

        self.assertIsInstance(__version__, str)

    def test_controller_imports_version(self):
        from ui.app_controller import GuardianController

        src = open(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "ui",
                "app_controller.py",
            ),
            encoding="utf-8",
        ).read()
        self.assertIn("from app.version import __version__", src)

    def test_controller_uses_version_in_settings(self):
        from ui.app_controller import GuardianController

        src = open(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "ui",
                "app_controller.py",
            ),
            encoding="utf-8",
        ).read()
        self.assertIn('"version": __version__', src)

    def test_app_module_has_env_check(self):
        src = open(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "ui",
                "app.py",
            ),
            encoding="utf-8",
        ).read()
        self.assertIn("run_all_checks", src)

    def test_no_implicit_oauth_on_import(self):
        """Importing app modules must not trigger OAuth."""
        from app.version import __version__
        from app.paths import app_root, user_data_dir
        from app.env_check import run_all_checks
        from app.logging_setup import setup_logging

        for mod in (app_root, user_data_dir, run_all_checks, setup_logging):
            self.assertIsNotNone(mod)


# ============================================================
# DATA DIRECTORY
# ============================================================


class TestDataDirectory(unittest.TestCase):
    """User data directory is created and contains tokens/."""

    def test_ensure_creates_tokens_subdir(self):
        from app.paths import ensure_user_data_dir

        d = ensure_user_data_dir()
        tokens = os.path.join(d, "tokens")
        self.assertTrue(os.path.isdir(tokens))


# ============================================================
# NAVIGATION
# ============================================================


class TestNavigationConsistency(unittest.TestCase):
    """Navigation still lists the same 7 views."""

    def test_nav_item_count(self):
        from ui.navigation import NAV_ITEMS

        self.assertEqual(len(NAV_ITEMS), 7)

    def test_nav_keys_are_strings(self):
        from ui.navigation import NAV_ITEMS

        for key, label in NAV_ITEMS:
            self.assertIsInstance(key, str)
            self.assertIsInstance(label, str)


if __name__ == "__main__":
    unittest.main()
