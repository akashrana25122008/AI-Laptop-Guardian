import customtkinter as ctk

from ui.components import safe_text, safe_ollama_message


class SettingsView(ctk.CTkFrame):
    """
    Settings with Application, AI, Cloud, and Privacy sections.
    No secrets are exposed.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._body = None

        self._gen_id = 0

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(
            row=0, column=0,
            padx=20, pady=(20, 10), sticky="w",
        )

        self._body = ctk.CTkFrame(
            self, fg_color="transparent"
        )

        self._body.grid(
            row=1, column=0,
            padx=20, pady=(0, 20), sticky="nsew",
        )

        self.grid_rowconfigure(1, weight=1)

    def refresh(self):
        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Loading settings...",
            text_color="gray",
        ).pack(padx=20, pady=30)

        self._gen_id = self.ctrl.next_gen()

        self.ctrl.run_refresh(
            self,
            self._gen_id,
            self.ctrl.get_settings,
            on_done=self._on_loaded,
            on_error=self._on_error,
        )

    def _on_loaded(self, settings):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        if not isinstance(settings, dict):
            settings = {}

        # --- Appearance ---

        ctk.CTkLabel(
            self._body,
            text="Appearance",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(10, 6), anchor="w")

        theme_row = ctk.CTkFrame(
            self._body, fg_color="transparent"
        )

        theme_row.pack(
            padx=20, pady=4, fill="x",
        )

        ctk.CTkLabel(
            theme_row, text="Theme:",
        ).pack(side="left", padx=(0, 8))

        theme_var = ctk.StringVar(
            value=settings.get("theme", "System")
        )

        def on_theme(choice):
            ctk.set_appearance_mode(choice)

        ctk.CTkOptionMenu(
            theme_row,
            values=["System", "Light", "Dark"],
            variable=theme_var,
            command=on_theme,
            width=140,
        ).pack(side="left")

        # --- Application ---

        ctk.CTkLabel(
            self._body,
            text="Application",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(20, 6), anchor="w",
        )

        app_items = [
            ("Version", settings.get("version", "?")),
            ("Onboarding",
             "Completed"
             if settings.get("onboarding_completed")
             else "Not completed"),
        ]

        for label, value in app_items:
            row = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            row.pack(padx=20, pady=3, fill="x")

            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=ctk.CTkFont(
                    size=12, weight="bold"
                ),
                width=140, anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=str(value),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(side="left")

        # --- AI ---

        ctk.CTkLabel(
            self._body,
            text="AI Assistant",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(20, 6), anchor="w",
        )

        ollama_raw = settings.get(
            "ollama_status", "Unknown"
        )

        ollama_items = [
            ("Status", safe_ollama_message(ollama_raw)),
            ("Model", settings.get("model", "Unknown")),
        ]

        for label, value in ollama_items:
            row = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            row.pack(padx=20, pady=3, fill="x")

            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=ctk.CTkFont(
                    size=12, weight="bold"
                ),
                width=140, anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=str(value),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(side="left")

        note = ctk.CTkLabel(
            self._body,
            text=(
                "Ollama is optional. The application "
                "works without it; the AI Assistant "
                "feature will be unavailable."
            ),
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=500,
            anchor="w",
            justify="left",
        )
        note.pack(padx=36, pady=(2, 10), anchor="w")

        # --- Cloud ---

        ctk.CTkLabel(
            self._body,
            text="Cloud",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(10, 6), anchor="w",
        )

        account_count = settings.get("account_count", 0)

        cloud_items = [
            ("Connected Accounts", str(account_count)),
            ("Token Storage", settings.get("token_dir", "?")),
        ]

        for label, value in cloud_items:
            row = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            row.pack(padx=20, pady=3, fill="x")

            ctk.CTkLabel(
                row,
                text=f"{label}:",
                font=ctk.CTkFont(
                    size=12, weight="bold"
                ),
                width=140, anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                row,
                text=str(value),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(side="left")

        # --- Privacy ---

        ctk.CTkLabel(
            self._body,
            text="Privacy",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(20, 6), anchor="w",
        )

        privacy_points = [
            "Local laptop analysis stays on your device.",
            "Google Drive access requires your explicit authorization.",
            "Destructive actions (cleanup, disconnect) require confirmation.",
            "Credentials and tokens are never displayed in the UI.",
        ]

        for point in privacy_points:
            ctk.CTkLabel(
                self._body,
                text=f"  {point}",
                font=ctk.CTkFont(size=12),
                anchor="w",
                wraplength=550,
                justify="left",
            ).pack(padx=36, pady=2, anchor="w")

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Unable to load settings.",
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
