"""Entry point for the packaged desktop GUI.

This module exists solely so PyInstaller can build
the desktop application.  It must not contain any
business logic.

M19: Wraps application startup in an error boundary so
that unexpected exceptions are logged and shown as a
safe user-facing message instead of silently crashing.
"""

import sys
import logging


def main():
    try:
        from app.logging_setup import setup_logging
        setup_logging()
    except Exception:
        pass

    try:
        from ui.app import GuardianApp
        app = GuardianApp()
        app.mainloop()
    except SystemExit:
        raise
    except Exception as exc:
        logger = logging.getLogger("ai_laptop_guardian.startup")
        logger.exception("Fatal startup error")
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror(
                "AI Laptop Guardian",
                f"Application failed to start:\n{type(exc).__name__}",
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
