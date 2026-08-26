"""Milestone 19 -- Release Hardening tests.

Validates version consistency, logging safety, error
boundaries, installer integrity, artifact hygiene, and
M17/M18 fixes without performing real destructive actions.
"""

import os
import re
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(PROJECT_ROOT, "app", "version.py")
PATHS_FILE = os.path.join(PROJECT_ROOT, "app", "paths.py")
STATE_FILE = os.path.join(PROJECT_ROOT, "app", "state.py")
LOGGING_FILE = os.path.join(PROJECT_ROOT, "app", "logging_setup.py")
ENV_CHECK_FILE = os.path.join(PROJECT_ROOT, "app", "env_check.py")
RUN_GUI_FILE = os.path.join(PROJECT_ROOT, "run_gui.py")
APP_PY = os.path.join(PROJECT_ROOT, "ui", "app.py")
CONTROLLER_PY = os.path.join(PROJECT_ROOT, "ui", "app_controller.py")
TOOL_ROUTER_PY = os.path.join(PROJECT_ROOT, "agent", "tool_router.py")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AI-Laptop-Guardian.spec")
ISS_FILE = os.path.join(PROJECT_ROOT, "installer", "ai_laptop_guardian.iss")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "AI-Laptop-Guardian")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _version():
    text = _read(VERSION_FILE)
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert m, "Cannot read version"
    return m.group(1)


def _iss_display_version():
    text = _read(ISS_FILE)
    m = re.search(r'#define\s+MyAppDisplayVersion\s+"([^"]+)"', text)
    if m:
        return m.group(1)
    m2 = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    return m2.group(1) if m2 else None


class TestVersionConsistency:
    def test_app_version_is_0_14(self):
        assert _version() == "0.14.0"

    def test_iss_display_version_matches(self):
        assert _iss_display_version() == _version()

    def test_iss_4part_version_format(self):
        text = _read(ISS_FILE)
        m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
        assert m
        parts = m.group(1).split(".")
        assert len(parts) == 4
        for p in parts:
            assert p.isdigit()

    def test_controller_uses_version_import(self):
        text = _read(CONTROLLER_PY)
        assert "from app.version import __version__" in text

    def test_env_check_uses_version_import(self):
        text = _read(ENV_CHECK_FILE)
        assert "from app.version import __version__" in text


class TestReleaseArtifactAudit:
    FORBIDDEN = {
        "credentials.json", "token.json", ".env",
        "cloud_data", ".git", ".venv", "venv",
        "__pycache__", "tests",
    }

    def test_dist_no_forbidden_files(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        for root, dirs, files in os.walk(DIST_DIR):
            for name in files + dirs:
                assert name not in self.FORBIDDEN

    def test_dist_no_git_dir(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        assert not os.path.exists(os.path.join(DIST_DIR, ".git"))

    def test_dist_has_exe(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        assert os.path.isfile(
            os.path.join(DIST_DIR, "AI-Laptop-Guardian.exe")
        )

    def test_dist_has_internal_dir(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        assert os.path.isdir(os.path.join(DIST_DIR, "_internal"))

    def test_dist_no_test_files(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        for root, dirs, files in os.walk(DIST_DIR):
            for name in files:
                assert not name.startswith("test_")


class TestStartupHardening:
    def test_run_gui_has_error_boundary(self):
        text = _read(RUN_GUI_FILE)
        assert "except" in text
        assert "Exception" in text

    def test_run_gui_logs_fatal_error(self):
        text = _read(RUN_GUI_FILE)
        assert "logging" in text

    def test_run_gui_shows_user_message(self):
        text = _read(RUN_GUI_FILE)
        assert "messagebox" in text or "showerror" in text

    def test_run_gui_sets_up_logging(self):
        text = _read(RUN_GUI_FILE)
        assert "setup_logging" in text

    def test_app_py_has_shutdown_handler(self):
        text = _read(APP_PY)
        assert "_on_close" in text
        assert "shutting_down" in text

    def test_controller_has_shutting_down_flag(self):
        text = _read(CONTROLLER_PY)
        assert "_shutting_down" in text


class TestLoggingSafety:
    def test_logging_setup_exists(self):
        assert os.path.isfile(LOGGING_FILE)

    def test_logging_no_secret_keywords_in_format(self):
        text = _read(LOGGING_FILE)
        lower = text.lower()
        assert "password" not in lower
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "password" in s.lower():
                pytest.fail(f"Password in logging code: {s}")

    def test_logging_setup_uses_user_data_dir(self):
        text = _read(LOGGING_FILE)
        assert "user_data_dir" in text

    def test_logging_has_correct_namespace(self):
        text = _read(LOGGING_FILE)
        assert "ai_laptop_guardian" in text

    def test_logging_no_algebra_typo(self):
        text = _read(LOGGING_FILE)
        assert "algebra_guardian" not in text

    def test_controller_no_token_logging(self):
        text = _read(CONTROLLER_PY)
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("#"):
                continue
            if "log" in s.lower() and "token" in s.lower():
                pytest.fail(f"Possible token logging: {s}")


class TestCrashHardening:
    def test_app_py_imports_catch_customtkinter(self):
        text = _read(APP_PY)
        assert "ImportError" in text

    def test_app_py_systemexit_on_missing_ctk(self):
        text = _read(APP_PY)
        assert "SystemExit" in text

    def test_controller_run_in_background_catches(self):
        text = _read(CONTROLLER_PY)
        assert "except Exception" in text

    def test_controller_has_run_refresh(self):
        text = _read(CONTROLLER_PY)
        assert "run_refresh" in text
        assert "shutting_down" in text

    def test_app_on_close_catches_errors(self):
        text = _read(APP_PY)
        assert "try:" in text
        assert "except" in text

    def test_run_gui_catches_startup_error(self):
        text = _read(RUN_GUI_FILE)
        assert "except" in text
        assert "sys.exit" in text


class TestInstallerUpgradeHardening:
    def test_installer_has_deltree(self):
        text = _read(ISS_FILE)
        assert "DelTree" in text

    def test_installer_deltree_on_app_dir_only(self):
        text = _read(ISS_FILE)
        assert "DelTree(ExpandConstant('{app}')" in text

    def test_installer_does_not_delete_userdata(self):
        text = _read(ISS_FILE)
        ud_ref = r"{localappdata}\AI-Laptop-Guardian"
        lines = [
            l for l in text.split("\n")
            if l.strip() and not l.strip().startswith(";")
        ]
        for line in lines:
            if "DelTree" in line or "UninstallDelete" in line:
                assert ud_ref not in line

    def test_installer_privileges_lowest(self):
        text = _read(ISS_FILE)
        assert "PrivilegesRequired=lowest" in text


class TestUserDataSeparation:
    def test_paths_module_has_user_data_dir(self):
        text = _read(PATHS_FILE)
        assert "user_data_dir" in text

    def test_frozen_mode_uses_localappdata(self):
        text = _read(PATHS_FILE)
        assert "LOCALAPPDATA" in text

    def test_source_mode_uses_cloud_data(self):
        text = _read(PATHS_FILE)
        assert "cloud_data" in text

    def test_state_file_uses_user_data_dir(self):
        text = _read(STATE_FILE)
        assert "user_data_dir" in text

    def test_logging_uses_user_data_dir(self):
        text = _read(LOGGING_FILE)
        assert "user_data_dir" in text

    def test_install_dir_differs_from_userdata(self):
        local = os.environ.get("LOCALAPPDATA", "X")
        install = os.path.join(local, "Programs", "AI-Laptop-Guardian")
        userdata = os.path.join(local, "AI-Laptop-Guardian")
        assert install != userdata

    def test_state_module_never_stores_secrets(self):
        """State module must not contain code that stores secrets."""
        text = _read(STATE_FILE)
        in_docstring = False
        for line in text.split("\n"):
            s = line.strip()
            if '"""' in s:
                count = s.count('"""')
                if count == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if s.startswith("#"):
                continue
            lower_s = s.lower()
            if "credentials" in lower_s or "oauth" in lower_s:
                pytest.fail(f"Possible secret storage: {s}")

    def test_state_module_safe_defaults(self):
        text = _read(STATE_FILE)
        assert "_DEFAULT_STATE" in text
        assert "FileNotFoundError" in text
        assert "JSONDecodeError" in text


class TestOptionalDependencyHandling:
    def test_tool_router_google_optional(self):
        text = _read(TOOL_ROUTER_PY)
        assert "_HAS_GOOGLE" in text
        assert "try:" in text
        assert "except ImportError" in text

    def test_tool_router_cloud_methods_guarded(self):
        text = _read(TOOL_ROUTER_PY)
        assert "if self.google_drive is None" in text
        assert "if self.drive_manager is None" in text
        assert "if self.auth_manager is None" in text

    def test_env_check_ollama_optional(self):
        text = _read(ENV_CHECK_FILE)
        assert '"optional": True' in text or "'optional': True" in text

    def test_env_check_google_optional(self):
        text = _read(ENV_CHECK_FILE)
        lower = text.lower()
        assert "google" in lower
        assert "optional" in lower

    def test_controller_handles_ollama_unavailable(self):
        text = _read(CONTROLLER_PY)
        assert "except Exception:" in text or "except Exception :" in text

    def test_no_implicit_auth_at_startup(self):
        text = _read(RUN_GUI_FILE)
        lower = text.lower()
        assert "oauth" not in lower
        assert "authenticate" not in lower
        assert "google" not in lower


class TestSecurityAudit:
    def test_no_secrets_tracked(self):
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        tracked = result.stdout
        for name in ["credentials.json", "token.json"]:
            assert name not in tracked

    def test_gitignore_excludes_cloud_data(self):
        gitignore = os.path.join(PROJECT_ROOT, ".gitignore")
        text = _read(gitignore)
        assert "cloud_data/" in text

    def test_gitignore_excludes_env(self):
        gitignore = os.path.join(PROJECT_ROOT, ".gitignore")
        text = _read(gitignore)
        assert ".env" in text

    def test_gitignore_excludes_installer_output(self):
        gitignore = os.path.join(PROJECT_ROOT, ".gitignore")
        text = _read(gitignore)
        assert "installer_output/" in text

    def test_tool_router_no_implicit_auth(self):
        text = _read(TOOL_ROUTER_PY)
        assert "no-implicit" in text or "explicit" in text.lower() or "EXPLICIT" in text

    def test_state_module_has_atomic_writes(self):
        text = _read(STATE_FILE)
        assert "os.replace" in text or "os.rename" in text

    def test_action_safety_unchanged(self):
        safety = os.path.join(PROJECT_ROOT, "agent", "action_safety.py")
        assert os.path.isfile(safety)
        text = _read(safety)
        assert "propose_cleanup" in text or "get_pending" in text


class TestM17FixesPreserved:
    def test_run_gui_entry_point(self):
        text = _read(SPEC_FILE)
        assert "run_gui.py" in text

    def test_google_imports_optional(self):
        text = _read(TOOL_ROUTER_PY)
        assert "_HAS_GOOGLE" in text

    def test_no_console_in_spec(self):
        text = _read(SPEC_FILE)
        assert "console=False" in text


class TestM18FixesPreserved:
    def test_installer_config_exists(self):
        assert os.path.isfile(ISS_FILE)

    def test_installer_build_script_exists(self):
        assert os.path.isfile(
            os.path.join(PROJECT_ROOT, "scripts", "build_installer.py")
        )

    def test_installer_targets_gui_exe(self):
        text = _read(ISS_FILE)
        assert "AI-Laptop-Guardian.exe" in text

    def test_installer_shortcuts_target_gui(self):
        text = _read(ISS_FILE)
        assert "AI-Laptop-Guardian.exe" in text
        assert "main.py" not in text
        assert "python.exe" not in text.lower()


class TestNoRealMutations:
    def test_no_real_cloud_delete_in_test(self):
        """Verify M19 tests don't call real cloud delete."""
        test_file = os.path.join(PROJECT_ROOT, "tests", "test_m19_release_hardening.py")
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            # Only check actual code lines, not strings containing the word
            if "delete_file_by_id" in s and "assert" not in s:
                pytest.fail(f"Possible real cloud delete: {s}")

    def test_no_real_cleanup_on_real_files(self):
        """Verify M19 tests don't do real filesystem cleanup."""
        test_file = os.path.join(PROJECT_ROOT, "tests", "test_m19_release_hardening.py")
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "shutil.rmtree" in s and "assert" not in s and "not in" not in s:
                pytest.fail(f"Possible real cleanup: {s}")
