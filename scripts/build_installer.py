#!/usr/bin/env python3
"""Build the Windows installer for AI Laptop Guardian.

Prerequisites:
    1. PyInstaller build has been run (dist/AI-Laptop-Guardian/ exists).
    2. Inno Setup 6 is installed.

Usage from project root:
    python scripts/build_installer.py
"""

import os
import shutil
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

# Inno Setup 6 default install location (per-user via winget).
INNO_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs",
    "Inno Setup 6",
)
ISCC_EXE = os.path.join(INNO_DIR, "ISCC.exe")

ISS_FILE = os.path.join(
    PROJECT_ROOT, "installer", "ai_laptop_guardian.iss"
)

DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "AI-Laptop-Guardian")

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "installer_output")


def verify_prerequisites():
    """Check that all required files/tools exist."""
    if not os.path.isfile(ISCC_EXE):
        sys.exit(
            f"ERROR: Inno Setup not found at {ISCC_EXE}\n"
            "Install Inno Setup 6 and retry."
        )

    if not os.path.isfile(ISS_FILE):
        sys.exit(f"ERROR: ISS script not found: {ISS_FILE}")

    if not os.path.isdir(DIST_DIR):
        sys.exit(
            f"ERROR: PyInstaller output not found: {DIST_DIR}\n"
            "Run 'python scripts/build_windows.py' first."
        )


def clean():
    """Remove previous installer output."""
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)


def build():
    """Run the Inno Setup compiler."""
    print("Building installer with Inno Setup...")
    result = subprocess.run(
        [ISCC_EXE, ISS_FILE],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        sys.exit(
            f"Inno Setup failed with exit code "
            f"{result.returncode}"
        )


def report():
    """Print installer artifact details."""
    if os.path.isdir(OUTPUT_DIR):
        files = os.listdir(OUTPUT_DIR)
        for f in files:
            path = os.path.join(OUTPUT_DIR, f)
            size = os.path.getsize(path) / (1024 * 1024)
            print(f"  {f}  ({size:.1f} MB)")
    else:
        print("WARNING: No installer output found.")


def main():
    verify_prerequisites()
    clean()
    build()
    print("\nInstaller build complete:")
    report()


if __name__ == "__main__":
    main()
