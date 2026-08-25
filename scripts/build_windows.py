#!/usr/bin/env python3
"""Minimal Windows build script for AI Laptop Guardian.

Builds a folder-based distribution using PyInstaller.

Usage from the project root:

    python scripts/build_windows.py
"""

import os
import shutil
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AI-Laptop-Guardian.spec")
RELEASE_DIR = os.path.join(DIST_DIR, "AI-Laptop-Guardian")


def clean():
    """Remove build artifacts."""
    for d in (BUILD_DIR, DIST_DIR):
        if os.path.exists(d):
            shutil.rmtree(d)


def verify_spec():
    """Ensure the spec file exists."""
    if not os.path.isfile(SPEC_FILE):
        sys.exit(
            f"ERROR: Spec file not found: {SPEC_FILE}\n"
            "Run this script from the project root."
        )


def build():
    """Run PyInstaller."""
    print("Building with PyInstaller...")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            SPEC_FILE,
            "--clean",
            "--noconfirm",
        ],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed with exit code {result.returncode}")


def print_artifacts():
    """Print the release directory and size."""
    if os.path.isdir(RELEASE_DIR):
        total = sum(
            os.path.getsize(os.path.join(d, f))
            for d, _, files in os.walk(RELEASE_DIR)
            for f in files
        )
        print(
            f"\nRelease build ready:\n"
            f"  {RELEASE_DIR}\n"
            f"  Size: {total / (1024 * 1024):.1f} MB"
        )
    else:
        print(
            f"\nWARNING: Expected build output not found at {RELEASE_DIR}"
        )


def main():
    verify_spec()
    clean()
    build()
    print_artifacts()


if __name__ == "__main__":
    main()
