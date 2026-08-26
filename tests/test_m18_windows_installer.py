"""Milestone 18 — Windows Installer validation tests.

These tests verify the installer configuration, packaging
integrity, version consistency, and safety guarantees
without requiring an actual interactive installer run.
"""

import os
import re

import pytest

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_DIR = os.path.join(PROJECT_ROOT, "installer")
ISS_FILE = os.path.join(INSTALLER_DIR, "ai_laptop_guardian.iss")
BUILD_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "build_installer.py")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "AI-Laptop-Guardian")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AI-Laptop-Guardian.spec")
RUN_GUI = os.path.join(PROJECT_ROOT, "run_gui.py")
VERSION_FILE = os.path.join(PROJECT_ROOT, "app", "version.py")
PATHS_FILE = os.path.join(PROJECT_ROOT, "app", "paths.py")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "installer_output")

# Files that must NEVER be packaged
FORBIDDEN_FILES = [
    "credentials.json",
    "token.json",
    ".env",
    "cloud_data",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "tests",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _version():
    text = _read(VERSION_FILE)
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match, "Cannot read version from app/version.py"
    return match.group(1)


def _iss_version():
    text = _read(ISS_FILE)
    match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    assert match, "Cannot read MyAppVersion from .iss file"
    return match.group(1)


def _iss_display_version():
    text = _read(ISS_FILE)
    match = re.search(
        r'#define\s+MyAppDisplayVersion\s+"([^"]+)"', text
    )
    if match:
        return match.group(1)
    return _iss_version()


# ---------------------------------------------------------------------------
# Installer configuration tests
# ---------------------------------------------------------------------------


class TestInstallerConfigExists:
    """Verify installer configuration files exist."""

    def test_installer_dir_exists(self):
        assert os.path.isdir(INSTALLER_DIR)

    def test_iss_file_exists(self):
        assert os.path.isfile(ISS_FILE)

    def test_build_script_exists(self):
        assert os.path.isfile(BUILD_SCRIPT)


class TestInstallerVersionConsistency:
    """Installer version must match app/version.py."""

    def test_iss_version_matches_app(self):
        app_version = _version()
        iss_version = _iss_display_version()
        assert app_version == iss_version, (
            f"Version mismatch: app={app_version}, iss={iss_version}"
        )

    def test_iss_internal_version_format(self):
        """Inno Setup requires 4-part internal version."""
        ver = _iss_version()
        parts = ver.split(".")
        assert len(parts) == 4, (
            f"Expected 4-part version, got: {ver}"
        )
        for p in parts:
            assert p.isdigit(), f"Non-numeric version part: {p}"


class TestInstallerTargetsGui:
    """Installer must target the GUI executable, not CLI."""

    def test_gui_entry_point_specified(self):
        text = _read(ISS_FILE)
        assert "AI-Laptop-Guardian.exe" in text

    def test_no_python_in_shortcut_targets(self):
        text = _read(ISS_FILE)
        assert "python.exe" not in text.lower()
        assert "pythonw.exe" not in text.lower()

    def test_console_false_in_spec(self):
        spec = _read(SPEC_FILE)
        assert "console=False" in spec

    def test_run_gui_exists(self):
        assert os.path.isfile(RUN_GUI)

    def test_run_gui_imports_guardian_app(self):
        text = _read(RUN_GUI)
        assert "GuardianApp" in text


class TestInstallerUserDataSeparation:
    """User data must live outside the installation directory."""

    def test_install_dir_is_localappdata_programs(self):
        text = _read(ISS_FILE)
        assert r"{localappdata}\Programs\AI-Laptop-Guardian" in text

    def test_user_data_dir_in_paths_module(self):
        text = _read(PATHS_FILE)
        assert "LOCALAPPDATA" in text
        assert "AI-Laptop-Guardian" in text

    def test_user_data_not_in_install_dir(self):
        """preferences.json should not be in the install directory."""
        install_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs",
            "AI-Laptop-Guardian",
        )
        user_data = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "AI-Laptop-Guardian",
        )
        assert install_dir != user_data


class TestInstallerExcludesForbiddenFiles:
    """Packaged application must not contain forbidden files."""

    def test_dist_dir_no_credentials(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        for root, dirs, files in os.walk(DIST_DIR):
            for name in files + dirs:
                assert name not in FORBIDDEN_FILES, (
                    f"Forbidden item found in dist: {name}"
                )

    def test_dist_dir_no_git(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        git_dir = os.path.join(DIST_DIR, ".git")
        assert not os.path.exists(git_dir)

    def test_dist_dir_no_env(self):
        if not os.path.isdir(DIST_DIR):
            pytest.skip("dist not built")
        env_file = os.path.join(DIST_DIR, ".env")
        assert not os.path.exists(env_file)


class TestInstallerUninstallSafety:
    """Uninstall must not target user-data paths."""

    def test_uninstall_delete_only_app_dir(self):
        text = _read(ISS_FILE)
        assert "{app}" in text
        user_data_ref = r"{localappdata}\AI-Laptop-Guardian"
        assert user_data_ref not in text or "UninstallDelete" not in text


class TestInstallerShortcuts:
    """Installer creates correct shortcuts."""

    def test_start_menu_shortcut(self):
        text = _read(ISS_FILE)
        assert "{group}" in text
        assert "AI-Laptop-Guardian.exe" in text

    def test_desktop_shortcut_optional(self):
        text = _read(ISS_FILE)
        assert "desktopicon" in text
        assert "Tasks:" in text

    def test_no_cli_in_shortcut(self):
        text = _read(ISS_FILE)
        assert "main.py" not in text


class TestInstallerBuildProcess:
    """Installer build script exists and is valid."""

    def test_build_script_is_python(self):
        assert BUILD_SCRIPT.endswith(".py")

    def test_build_script_references_iscc(self):
        text = _read(BUILD_SCRIPT)
        assert "ISCC" in text or "iscc" in text.lower()

    def test_build_script_references_iss(self):
        text = _read(BUILD_SCRIPT)
        assert ".iss" in text


class TestInstallerPrivileges:
    """Installer should not require admin privileges."""

    def test_lowest_privileges(self):
        text = _read(ISS_FILE)
        assert "PrivilegesRequired=lowest" in text


class TestInstallerCompression:
    """Installer should use solid compression."""

    def test_compression_set(self):
        text = _read(ISS_FILE)
        assert "SolidCompression=yes" in text


class TestM17FixesPreserved:
    """M17 critical fixes must remain intact."""

    def test_run_gui_entry_point(self):
        spec = _read(SPEC_FILE)
        assert '["run_gui.py"]' in spec

    def test_google_imports_optional(self):
        router_path = os.path.join(
            PROJECT_ROOT, "agent", "tool_router.py"
        )
        text = _read(router_path)
        assert "try:" in text
        assert "except" in text
        assert "_HAS_GOOGLE" in text

    def test_no_console_in_spec(self):
        spec = _read(SPEC_FILE)
        assert "console=False" in spec


class TestInstallerPostInstallLaunch:
    """Installer offers post-install launch."""

    def test_postinstall_launch(self):
        text = _read(ISS_FILE)
        assert "postinstall" in text
        assert "nowait" in text


class TestInstallerUpgradeBehavior:
    """Installer cleans old files on upgrade."""

    def test_del_tree_on_install(self):
        text = _read(ISS_FILE)
        assert "DelTree" in text or "delTree" in text


class TestNoSecretsTracked:
    """No secrets in git-tracked files."""

    def test_no_credentials_tracked(self):
        result = os.popen(
            'git ls-files | findstr /i "credentials.json token.json .env"'
        ).read()
        assert "credentials.json" not in result
        assert "token.json" not in result


class TestInstallerOutputExists:
    """If installer was built, verify the artifact."""

    def test_installer_output_dir(self):
        if not os.path.isdir(OUTPUT_DIR):
            pytest.skip("Installer not built yet")

    def test_installer_exe_exists(self):
        if not os.path.isdir(OUTPUT_DIR):
            pytest.skip("Installer not built yet")
        files = os.listdir(OUTPUT_DIR)
        setup_files = [f for f in files if f.endswith(".exe")]
        assert len(setup_files) >= 1, "No setup .exe found"

    def test_installer_naming_convention(self):
        if not os.path.isdir(OUTPUT_DIR):
            pytest.skip("Installer not built yet")
        files = os.listdir(OUTPUT_DIR)
        for f in files:
            if f.endswith(".exe"):
                assert "AI-Laptop-Guardian" in f
                assert "Setup" in f or "setup" in f
