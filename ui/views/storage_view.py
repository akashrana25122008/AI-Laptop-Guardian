import customtkinter as ctk

from ui.components import safe_text


class StorageView(ctk.CTkFrame):
    """Local drives + large files + duplicate candidates."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._body = None

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Local Storage",
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
            self._body, text="Scanning storage...",
            text_color="gray",
        ).pack(padx=20, pady=30)

        self.ctrl.run_in_background(
            self._load,
            on_done=self._on_loaded,
            on_error=self._on_error,
        )

    def _load(self):
        drives = self.ctrl.get_local_drives()
        large = self.ctrl.get_large_files()
        dup = self.ctrl.get_local_duplicates()

        return drives, large, dup

    def _on_loaded(self, triple):
        drives, large, dup = triple

        for w in self._body.winfo_children():
            w.destroy()

        self._render_drives(drives)

        self._render_large_files(large)

        self._render_duplicates(dup)

    def _render_drives(self, result):
        ctk.CTkLabel(
            self._body,
            text="Drives",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(10, 6), anchor="w")

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
                    "Drive data unavailable.",
                ),
                text_color="#c0392b",
            ).pack(padx=30, pady=4, anchor="w")
            return

        drives = (
            (result.get("data") or {})
            .get("drives") or []
        )

        if not drives:
            ctk.CTkLabel(
                self._body,
                text="No local drives found.",
            ).pack(padx=30, pady=4, anchor="w")
            return

        for d in drives:
            if not isinstance(d, dict):
                continue

            name = d.get("drive", "?")
            total = d.get("total_gb", "?")
            free = d.get("free_gb", "?")
            pct = d.get("percent_used", "?")
            status = d.get("status", "")

            ctk.CTkLabel(
                self._body,
                text=(
                    f"{name}  —  {pct}% used  |  "
                    f"{free} GB free of {total} GB  |  "
                    f"{status}"
                ),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(padx=30, pady=2, anchor="w")

    def _render_large_files(self, result):
        ctk.CTkLabel(
            self._body,
            text="Large local files",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(16, 6), anchor="w",
        )

        if not (
            result.get("success")
            if isinstance(result, dict)
            else False
        ):
            ctk.CTkLabel(
                self._body,
                text="Large-file data unavailable.",
                text_color="gray",
            ).pack(padx=30, pady=4, anchor="w")
            return

        files = (
            (result.get("data") or {})
            .get("files") or []
        )[:10]

        if not files:
            ctk.CTkLabel(
                self._body,
                text="No large files found.",
            ).pack(padx=30, pady=4, anchor="w")
            return

        for f in files:
            if not isinstance(f, dict):
                continue

            ctk.CTkLabel(
                self._body,
                text=(
                    f"  {f.get('name', '?')}  —  "
                    f"{f.get('size_gb', '?')} GB"
                ),
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(padx=30, pady=1, anchor="w")

    def _render_duplicates(self, result):
        ctk.CTkLabel(
            self._body,
            text="Duplicate candidates",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(
            padx=20, pady=(16, 6), anchor="w",
        )

        if not (
            result.get("success")
            if isinstance(result, dict)
            else False
        ):
            ctk.CTkLabel(
                self._body,
                text="Duplicate data unavailable.",
                text_color="gray",
            ).pack(padx=30, pady=4, anchor="w")
            return

        groups = (
            (result.get("data") or {})
            .get("groups") or []
        )[:10]

        if not groups:
            ctk.CTkLabel(
                self._body,
                text="No duplicate candidates found.",
            ).pack(padx=30, pady=4, anchor="w")
            return

        for g in groups:
            if not isinstance(g, dict):
                continue

            copies = g.get("copies", "?")
            size = g.get("size_mb", "?")

            ctk.CTkLabel(
                self._body,
                text=(
                    f"  {copies} copies  —  "
                    f"{size} MB each"
                ),
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(padx=30, pady=1, anchor="w")

    def _on_error(self, _exc):
        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Unable to scan storage right now.\nPlease try again.",
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
