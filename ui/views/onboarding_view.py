"""First-run onboarding for AI Laptop Guardian.

This view is shown when the user has not yet completed
onboarding.  It walks through:

1. Welcome — what Guardian does
2. Privacy — what data stays local, what needs consent
3. Setup status — Ollama, Google Drive, local tools
4. Finish — Get Started button

No OAuth, network calls, or credential access occurs
during onboarding.
"""

import customtkinter as ctk


class OnboardingView(ctk.CTkFrame):
    """First-run wizard displayed before the main dashboard."""

    def __init__(self, parent, controller, on_finish=None):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller
        self._on_finish = on_finish
        self._step = 0
        self._steps = [
            self._build_welcome,
            self._build_privacy,
            self._build_setup,
            self._build_finish,
        ]
        self._body = None

        self._build()

        self._show_step(0)

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._header = ctk.CTkLabel(
            self,
            text="Welcome to AI Laptop Guardian",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self._header.grid(
            row=0, column=0,
            padx=20, pady=(20, 10), sticky="w",
        )

        self._body = ctk.CTkFrame(
            self, fg_color="transparent"
        )
        self._body.grid(
            row=1, column=0,
            padx=20, pady=(0, 10), sticky="nsew",
        )

        nav = ctk.CTkFrame(
            self, fg_color="transparent"
        )
        nav.grid(
            row=2, column=0,
            padx=20, pady=(0, 20), sticky="ew",
        )

        self._back_btn = ctk.CTkButton(
            nav, text="Back", width=100,
            command=self._go_back,
        )
        self._back_btn.pack(side="left")

        self._next_btn = ctk.CTkButton(
            nav, text="Next", width=100,
            command=self._go_next,
        )
        self._next_btn.pack(side="right")

    def _show_step(self, idx):
        self._step = idx

        for w in self._body.winfo_children():
            w.destroy()

        self._steps[idx]()

        self._back_btn.configure(
            state="normal" if idx > 0 else "disabled"
        )

        if idx == len(self._steps) - 1:
            self._next_btn.configure(
                text="Get Started",
                command=self._finish,
            )
        else:
            self._next_btn.configure(
                text="Next",
                command=self._go_next,
            )

    def _go_back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _go_next(self):
        if self._step < len(self._steps) - 1:
            self._show_step(self._step + 1)

    def _finish(self):
        """Complete onboarding and transition to main UI."""
        import app.state as state_mod

        state_mod.mark_onboarding_completed()

        if self._on_finish:
            self._on_finish()

    # =====================================================
    # STEP 1: Welcome
    # =====================================================

    def _build_welcome(self):
        self._header.configure(
            text="Welcome to AI Laptop Guardian"
        )

        ctk.CTkLabel(
            self._body,
            text=(
                "AI Laptop Guardian helps you understand "
                "and maintain your Windows laptop."
            ),
            font=ctk.CTkFont(size=14),
            wraplength=600,
            justify="left",
        ).pack(padx=20, pady=(20, 10), anchor="w")

        features = [
            ("Health Monitoring",
             "Check your laptop's health and get recommendations"),
            ("Storage Analysis",
             "See what is using your disk space"),
            ("Safe Cleanup",
             "Remove temporary and unnecessary files safely"),
            ("Cloud Integration",
             "Optionally connect Google Drive to manage cloud storage"),
            ("AI Assistant",
             "Ask questions about your laptop in plain English"),
        ]

        for title, desc in features:
            f = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            f.pack(padx=40, pady=3, fill="x")

            ctk.CTkLabel(
                f, text=title,
                font=ctk.CTkFont(
                    size=13, weight="bold"
                ),
                width=180, anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                f, text=desc,
                font=ctk.CTkFont(size=12),
                wraplength=400, anchor="w",
            ).pack(side="left", padx=(10, 0))

    # =====================================================
    # STEP 2: Privacy
    # =====================================================

    def _build_privacy(self):
        self._header.configure(text="Your Privacy")

        ctk.CTkLabel(
            self._body,
            text=(
                "AI Laptop Guardian is designed with your "
                "privacy in mind."
            ),
            font=ctk.CTkFont(size=14),
            wraplength=600,
            justify="left",
        ).pack(padx=20, pady=(20, 10), anchor="w")

        points = [
            ("Local analysis stays local",
             "Your laptop data is analyzed on your device. "
             "Nothing is sent anywhere unless you choose to "
             "connect a cloud account."),
            ("Google Drive requires your permission",
             "Connecting Google Drive uses Google's official "
             "authorization. Guardian never accesses your "
             "Google account without you explicitly choosing "
             "to connect."),
            ("Cleanup requires your confirmation",
             "Before any file is deleted, you will see a "
             "preview and must give explicit approval. "
             "Nothing is removed automatically."),
            ("Credentials are protected",
             "Authentication tokens and secrets are stored "
             "securely and never displayed in the application."),
        ]

        for title, desc in points:
            f = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            f.pack(padx=40, pady=4, fill="x")

            ctk.CTkLabel(
                f, text=f"  {title}",
                font=ctk.CTkFont(
                    size=13, weight="bold"
                ),
                anchor="w",
            ).pack(padx=(20, 0), fill="x")

            ctk.CTkLabel(
                f, text=desc,
                font=ctk.CTkFont(size=12),
                wraplength=550, justify="left",
                anchor="w",
            ).pack(padx=(40, 20), fill="x")

    # =====================================================
    # STEP 3: Setup Status
    # =====================================================

    def _build_setup(self):
        self._header.configure(text="Setup Status")

        ctk.CTkLabel(
            self._body,
            text=(
                "Here is what is currently available on "
                "your system."
            ),
            font=ctk.CTkFont(size=14),
            wraplength=600,
        ).pack(padx=20, pady=(20, 10), anchor="w")

        status = self.ctrl.get_onboarding_status()

        items = [
            ("Local Storage",
             status.get("local_storage", "Available"),
             True),
            ("Ollama (AI Assistant)",
             status.get("ollama_status", "Unknown"),
             status.get("ollama_available", False)),
            ("Google Drive",
             status.get("google_status", "Not connected"),
             True),
            ("Application Version",
             status.get("version", "Unknown"),
             True),
        ]

        for label, value, ok in items:
            f = ctk.CTkFrame(
                self._body, fg_color="transparent"
            )
            f.pack(padx=40, pady=3, fill="x")

            color = "#2fa572" if ok else "#c0392b"

            ctk.CTkLabel(
                f, text=label,
                font=ctk.CTkFont(
                    size=13, weight="bold"
                ),
                width=180, anchor="w",
            ).pack(side="left")

            ctk.CTkLabel(
                f, text=value,
                font=ctk.CTkFont(size=12),
                text_color=color,
                anchor="w",
            ).pack(side="left", padx=(10, 0))

        note = ctk.CTkLabel(
            self._body,
            text=(
                "Ollama and Google Drive are optional. "
                "You can connect them later from Settings "
                "or the Accounts tab."
            ),
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=550,
            justify="left",
        )
        note.pack(
            padx=40, pady=(20, 10), anchor="w",
        )

    # =====================================================
    # STEP 4: Finish
    # =====================================================

    def _build_finish(self):
        self._header.configure(text="You're All Set")

        ctk.CTkLabel(
            self._body,
            text=(
                "You're ready to use AI Laptop Guardian.\n\n"
                "You can return to Settings at any time to "
                "change your preferences or reconnect "
                "Google Drive."
            ),
            font=ctk.CTkFont(size=14),
            wraplength=600,
            justify="left",
        ).pack(padx=20, pady=(20, 10), anchor="w")

        ctk.CTkLabel(
            self._body,
            text=(
                "Tip: Try the Dashboard to see your "
                "laptop's status at a glance, or ask the "
                "AI Assistant a question."
            ),
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=550,
            justify="left",
        ).pack(padx=40, pady=(10, 0), anchor="w")
