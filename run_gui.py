"""Entry point for the packaged desktop GUI.

This module exists solely so PyInstaller can build
the desktop application.  It must not contain any
business logic.
"""

from ui.app import GuardianApp


def main():
    app = GuardianApp()
    app.mainloop()


if __name__ == "__main__":
    main()
