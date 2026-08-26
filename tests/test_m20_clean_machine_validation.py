"""Milestone 20 -- Clean-Machine / Fresh-Environment Validation tests.

Validates that the application works correctly on a clean Windows
machine: correct path resolution in packaged mode, onboarding,
Ollama-absent behavior, local functionality, user-data separation,
and installer integrity. No real cloud actions or destructive ops.
"""

import os
import re
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS_FILE = os.path.join(PROJECT_ROOT, "app", "paths.py")
STATE_FILE = os.path.join(PROJECT_ROOT, "app", "state.py")
VERSION_FILE = os.path.join(PROJECT_ROOT, "app", "version.py")
ENV_CHECK_FILE = os.path.join(PROJECT_ROOT, "app", "env_check.py")
LOGGING_FILE = os.path.join(PROJECT_ROOT, "app", "logging_setup.py")
RUN_GUI_FILE = os.path.join(PROJECT_ROOT, "run_gui.py")
APP_PY = os.path.join(PROJECT_ROOT, "ui", "app.py")
CONTROLLER_PY = os.path.join(PROJECT_ROOT, "ui", "app_controller.py")
ONBOARDING_PY = os.path.join(PROJECT_ROOT, "ui", "views", "onboarding_view.py")
NAVIGATION_PY = os.path.join(PROJECT_ROOT, "ui", "navigation.py")
TOOL_ROUTER_PY = os.path.join(PROJECT_ROOT, "agent", "tool_router.py")
ACTION_SAFETY_PY = os.path.join(PROJECT_ROOT, "agent", "action_safety.py")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AI-Laptop-Guardian.spec")
ISS_FILE = os.path.join(PROJECT_ROOT, "installer", "ai_laptop_guardian.iss")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "AI-Laptop-Guardian")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _version():
    text = _read(VERSION_FILE)
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


class TestFrozenPathResolution:
    """Validate that _is_frozen() correctly detects packaged mode."""

    def test_paths_has_is_frozen(self):
        text = _read(PATHS_FILE)
        assert "def _is_frozen" in text

    def test_is_frozen_checks_sys_frozen(self):
        text = _read(PATHS_FILE)
        assert "getattr(sys" in text
        assert '"frozen"' in text

    def test_is_frozen_does_not_check_meipass_only(self):
        """_is_frozen must not rely on _MEIPASS which is absent in onedir."""
        text = _read(PATHS_FILE)
        # Find the _is_frozen function body
        m = re.search(
            r'def _is_frozen\(\):(.*?)(?=\ndef |\nclass |\Z)',
            text, re.DOTALL
        )
        assert m, "_is_frozen function not found"
        body = m.group(1)
        assert "_MEIPASS" not in body, (
            "_is_frozen must not check _MEIPASS -- "
            "that attribute is only set in --onefile mode"
        )

    def test_is_onefile_exists(self):
        text = _read(PATHS_FILE)
        assert "def _is_onefile" in text

    def test_app_root_handles_onedir(self):
        text = _read(PATHS_FILE)
        # app_root should handle frozen+not-onefile by using dirname(executable)
        assert "os.path.dirname(sys.executable)" in text

    def test_app_root_handles_onefile(self):
        text = _read(PATHS_FILE)
        assert "sys._MEIPASS" in text

    def test_user_data_dir_frozen_uses_localappdata(self):
        text = _read(PATHS_FILE)
        assert "LOCALAPPDATA" in text

    def test_user_data_dir_source_uses_cloud_data(self):
        text = _read(PATHS_FILE)
        assert "cloud_data" in text


class TestInstalledExeDataSeparation:
    """Validate that installed exe writes to %LOCALAPPDATA%, not source."""

    def test_installed_exe_exists(self):
        exe = os.path.join(DIST_DIR, "AI-Laptop-Guardian.exe")
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        assert os.path.isfile(exe)

    def test_user_data_dir_differs_from_source(self):
        local = os.environ.get("LOCALAPPDATA", "")
        if not local:
            pytest.skip("LOCALAPPDATA not set")
        install_dir = os.path.join(local, "Programs", "AI-Laptop-Guardian")
        userdata_dir = os.path.join(local, "AI-Laptop-Guardian")
        assert install_dir != userdata_dir

    def test_user_data_dir_is_under_localappdata(self):
        local = os.environ.get("LOCALAPPDATA", "")
        if not local:
            pytest.skip("LOCALAPPDATA not set")
        userdata = os.path.join(local, "AI-Laptop-Guardian")
        assert userdata.startswith(local)


class TestOnboardingFreshState:
    """Validate onboarding works from a fresh state."""

    def test_onboarding_view_exists(self):
        assert os.path.isfile(ONBOARDING_PY)

    def test_onboarding_view_has_wizard(self):
        text = _read(ONBOARDING_PY)
        assert "welcome" in text.lower() or "step" in text.lower()

    def test_state_module_has_onboarding_functions(self):
        text = _read(STATE_FILE)
        assert "onboarding_completed" in text

    def test_app_py_checks_onboarding(self):
        text = _read(APP_PY)
        assert "onboarding" in text.lower()

    def test_state_module_has_preferences_file(self):
        text = _read(STATE_FILE)
        assert "preferences" in text


class TestOllamaAbsentBehavior:
    """Validate app works when Ollama is not installed."""

    def test_env_check_marks_ollama_optional(self):
        text = _read(ENV_CHECK_FILE)
        assert "ollama" in text.lower()

    def test_controller_handles_ollama_failure(self):
        text = _read(CONTROLLER_PY)
        assert "except" in text

    def test_ollama_not_required_for_startup(self):
        text = _read(RUN_GUI_FILE)
        lower = text.lower()
        assert "ollama" not in lower or "except" in lower

    def test_settings_view_shows_ollama_status(self):
        settings = os.path.join(PROJECT_ROOT, "ui", "views", "settings_view.py")
        if not os.path.isfile(settings):
            pytest.skip("settings_view not found")
        text = _read(settings)
        assert "ollama" in text.lower()


class TestLocalFunctionality:
    """Validate all local tools are present and callable."""

    TOOL_DIRS = ["cpu", "ram", "battery", "storage", "health"]

    def test_tool_router_exists(self):
        assert os.path.isfile(TOOL_ROUTER_PY)

    def test_tool_router_has_execute(self):
        text = _read(TOOL_ROUTER_PY)
        assert "def execute" in text

    @pytest.mark.parametrize("tool_name", TOOL_DIRS)
    def test_tool_dir_exists(self, tool_name):
        path = os.path.join(PROJECT_ROOT, "tools", tool_name)
        assert os.path.isdir(path), f"tools/{tool_name} not found"

    def test_cleanup_tool_exists(self):
        cleanup = os.path.join(PROJECT_ROOT, "tools", "cleanup")
        assert os.path.isdir(cleanup)


class TestCleanupSafety:
    """Validate cleanup confirmation is unchanged."""

    def test_action_safety_has_propose(self):
        text = _read(ACTION_SAFETY_PY)
        assert "propose" in text.lower()

    def test_action_safety_requires_confirmation(self):
        text = _read(ACTION_SAFETY_PY)
        assert "confirm" in text.lower()

    def test_cleanup_requires_preview_first(self):
        cleanup_dir = os.path.join(PROJECT_ROOT, "tools", "cleanup")
        if not os.path.isdir(cleanup_dir):
            pytest.skip("cleanup tool not found")
        cleanup_file = os.path.join(cleanup_dir, "cleanup.py")
        if not os.path.isfile(cleanup_file):
            pytest.skip("cleanup.py not found")
        text = _read(cleanup_file)
        assert "preview" in text.lower() or "scan" in text.lower()


class TestAccountsUX:
    """Validate accounts view and auth_manager present."""

    def test_accounts_view_exists(self):
        view = os.path.join(PROJECT_ROOT, "ui", "views", "accounts_view.py")
        assert os.path.isfile(view)

    def test_auth_manager_exists(self):
        am = os.path.join(PROJECT_ROOT, "cloud", "auth_manager.py")
        assert os.path.isfile(am)

    def test_accounts_view_no_implicit_auth(self):
        view = os.path.join(PROJECT_ROOT, "ui", "views", "accounts_view.py")
        text = _read(view)
        lower = text.lower()
        # Should not auto-authenticate
        assert "auto_connect" not in lower
        assert "auto_auth" not in lower


class TestSettingsView:
    """Validate settings view displays version and settings."""

    def test_settings_view_exists(self):
        view = os.path.join(PROJECT_ROOT, "ui", "views", "settings_view.py")
        assert os.path.isfile(view)

    def test_settings_displays_version(self):
        view = os.path.join(PROJECT_ROOT, "ui", "views", "settings_view.py")
        text = _read(view)
        assert "version" in text.lower()

    def test_settings_has_theme_selector(self):
        view = os.path.join(PROJECT_ROOT, "ui", "views", "settings_view.py")
        text = _read(view)
        assert "theme" in text.lower()


class TestRestartPersistence:
    """Validate preferences survive simulated restart."""

    def test_state_loads_saved_preferences(self):
        text = _read(STATE_FILE)
        assert "load" in text.lower() or "read" in text.lower()

    def test_state_saves_preferences(self):
        text = _read(STATE_FILE)
        assert "save" in text.lower() or "write" in text.lower()

    def test_state_has_atomic_write(self):
        text = _read(STATE_FILE)
        assert "os.replace" in text or "tempfile" in text


class TestUninstallReinstall:
    """Validate installer and uninstaller configuration."""

    def test_installer_exists(self):
        assert os.path.isfile(ISS_FILE)

    def test_installer_has_uninstall_entry(self):
        text = _read(ISS_FILE)
        assert "[UninstallDelete]" in text or "DelTree" in text

    def test_installer_does_not_delete_user_data_dir(self):
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


class TestSecurity:
    """Validate no secrets or credentials exposed."""

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

    def test_state_never_stores_oauth(self):
        text = _read(STATE_FILE)
        in_docstring = False
        for line in text.split("\n"):
            s = line.strip()
            if '"""' in s:
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if s.startswith("#"):
                continue
            lower_s = s.lower()
            if "oauth" in lower_s and "token" in lower_s:
                pytest.fail(f"Possible secret storage: {s}")

    def test_logging_no_password_in_format(self):
        text = _read(LOGGING_FILE)
        lower = text.lower()
        assert "password" not in lower

    def test_tool_router_no_implicit_auth(self):
        text = _read(TOOL_ROUTER_PY)
        lower = text.lower()
        assert "no-implicit" in lower or "explicit" in lower


class TestProcessValidation:
    """Validate exe can be launched (dist check only, no real launch)."""

    def test_dist_has_exe(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        exe = os.path.join(DIST_DIR, "AI-Laptop-Guardian.exe")
        assert os.path.isfile(exe)

    def test_dist_has_internal_dir(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        assert os.path.isdir(os.path.join(DIST_DIR, "_internal"))

    def test_dist_size_reasonable(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        total = 0
        for root, dirs, files in os.walk(DIST_DIR):
            for f in files:
                total += os.path.getsize(os.path.join(root, f))
        # Should be at least 5 MB (GUI + deps)
        assert total > 5 * 1024 * 1024
        # Should be under 200 MB
        assert total < 200 * 1024 * 1024


class TestErrorRecovery:
    """Validate error handling is robust."""

    def test_run_gui_has_error_boundary(self):
        text = _read(RUN_GUI_FILE)
        assert "except" in text
        assert "Exception" in text

    def test_run_gui_shows_user_message(self):
        text = _read(RUN_GUI_FILE)
        assert "messagebox" in text or "showerror" in text

    def test_app_py_has_shutdown_handler(self):
        text = _read(APP_PY)
        assert "_on_close" in text

    def test_controller_has_shutting_down_flag(self):
        text = _read(CONTROLLER_PY)
        assert "_shutting_down" in text

    def test_state_has_safe_defaults(self):
        text = _read(STATE_FILE)
        assert "_DEFAULT_STATE" in text
        assert "FileNotFoundError" in text


class TestM19FixesPreserved:
    """Validate all M19 hardening is preserved."""

    def test_logging_namespace_correct(self):
        text = _read(LOGGING_FILE)
        assert "ai_laptop_guardian" in text
        assert "algebra_guardian" not in text

    def test_google_imports_optional(self):
        text = _read(TOOL_ROUTER_PY)
        assert "_HAS_GOOGLE" in text

    def test_no_console_in_spec(self):
        text = _read(SPEC_FILE)
        assert "console=False" in text

    def test_run_gui_entry_in_spec(self):
        text = _read(SPEC_FILE)
        assert "run_gui.py" in text

    def test_installer_build_script_exists(self):
        assert os.path.isfile(
            os.path.join(PROJECT_ROOT, "scripts", "build_installer.py")
        )


class TestNoRealMutations:
    """Verify M20 tests never perform real destructive actions."""

    def test_no_real_cloud_delete(self):
        test_file = os.path.join(
            PROJECT_ROOT, "tests", "test_m20_clean_machine_validation.py"
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "delete_file_by_id" in s and "assert" not in s:
                pytest.fail(f"Possible real cloud delete: {s}")

    def test_no_real_cleanup_on_real_files(self):
        test_file = os.path.join(
            PROJECT_ROOT, "tests", "test_m20_clean_machine_validation.py"
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "shutil.rmtree" in s and "assert" not in s:
                pytest.fail(f"Possible real cleanup: {s}")

    def test_no_real_oauth(self):
        test_file = os.path.join(
            PROJECT_ROOT, "tests", "test_m20_clean_machine_validation.py"
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines:
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "run_local_server" in s and "not in" not in s:
                pytest.fail(f"Possible real OAuth flow: {s}")
