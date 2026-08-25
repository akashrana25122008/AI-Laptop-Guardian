import customtkinter as ctk

from ui.components import safe_text


class HealthView(ctk.CTkFrame):
    """Full deterministic health report."""

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
            text="Laptop Health",
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
            self._body, text="Checking health...",
            text_color="gray",
        ).pack(padx=20, pady=30)

        self._gen_id = self.ctrl.next_gen()

        self.ctrl.run_refresh(
            self,
            self._gen_id,
            self._load,
            on_done=self._on_loaded,
            on_error=self._on_error,
        )

    def _load(self):
        result = self.ctrl.get_health_report()
        recs = self.ctrl.get_health_recommendations(
            result
        )

        return result, recs

    def _on_loaded(self, pair):
        result, recs = pair

        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        if not (
            result.get("success")
            if isinstance(result, dict)
            else False
        ):
            ctk.CTkLabel(
                self._body,
                text=safe_text(
                    result.get("error")
                    if isinstance(result, dict)
                    else None,
                    "Health data unavailable.",
                ),
                text_color="#c0392b",
            ).pack(padx=20, pady=30)
            return

        data = result.get("data") or {}
        overall = data.get("overall") or {}

        score = overall.get("score")
        status = overall.get("status", "Unknown")

        header_text = (
            f"Score: {score}  |  Status: {status}"
            if score is not None
            else f"Status: {status}"
        )

        ctk.CTkLabel(
            self._body, text=header_text,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=(
                "#2fa572" if score and score >= 70
                else "#c0392b"
            ),
        ).pack(padx=20, pady=(10, 20), anchor="w")

        scores = data.get("component_scores") or {}

        for label, key in [
            ("CPU", "cpu"),
            ("RAM", "ram"),
            ("Battery", "battery"),
            ("Storage", "storage"),
        ]:
            sc = scores.get(key)

            if sc is None:
                continue

            color = (
                "#2fa572" if sc >= 70
                else "#c0392b"
            )

            ctk.CTkLabel(
                self._body,
                text=f"{label}: {sc}/100",
                font=ctk.CTkFont(size=13),
                text_color=color,
            ).pack(
                padx=20, pady=2, anchor="w",
            )

        if recs:
            ctk.CTkLabel(
                self._body,
                text="Recommendations",
                font=ctk.CTkFont(
                    size=14, weight="bold"
                ),
            ).pack(
                padx=20, pady=(20, 6), anchor="w",
            )

            for rec in recs:
                ctk.CTkLabel(
                    self._body,
                    text=f"• {rec}",
                    font=ctk.CTkFont(size=12),
                    wraplength=500,
                    justify="left",
                ).pack(
                    padx=30, pady=2, anchor="w",
                )

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Unable to check health right now.\nPlease try again.",
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
