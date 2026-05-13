"""Tkinter UI for MP3 Insight Player."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import api_client, exporter, source_manager, storage
from .config import AVAILABLE_ASR_MODELS, AVAILABLE_CHAT_MODELS, AVAILABLE_LANGUAGES, WINDOW_GEOMETRY, ensure_dirs
from .player_engine import Mp3Player, PlayerError
from .time_utils import format_ms


PAD = 8


THEME_OPTIONS = [("淺色 Light", "light"), ("暗色 Dark", "dark")]
THEME_LABEL_BY_NAME = {name: label for label, name in THEME_OPTIONS}
THEME_NAME_BY_LABEL = {label: name for label, name in THEME_OPTIONS}

PALETTES = {
    "light": {
        "app_bg": "#f3f6fb",
        "surface_bg": "#eef3f9",
        "input_bg": "#ffffff",
        "text_fg": "#142033",
        "muted_fg": "#32506d",
        "accent": "#0f6cbd",
        "accent_fg": "#ffffff",
        "tree_bg": "#ffffff",
        "tree_selected_bg": "#b7d7f4",
    },
    "dark": {
        "app_bg": "#10161f",
        "surface_bg": "#18212d",
        "input_bg": "#223041",
        "text_fg": "#e6edf6",
        "muted_fg": "#8fc3ff",
        "accent": "#5aa9ff",
        "accent_fg": "#08111f",
        "tree_bg": "#18212d",
        "tree_selected_bg": "#36516f",
    },
}


def _fmt_ts(timestamp: int | None) -> str:
    if not timestamp:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))


class Mp3InsightApp:
    def __init__(self, root: tk.Tk) -> None:
        ensure_dirs()
        self.root = root
        self.root.title("MP3 Insight Player")
        self.root.geometry(WINDOW_GEOMETRY)
        self.settings = storage.load_settings()
        self.current_source: dict[str, Any] | None = None
        self.current_transcript: dict[str, Any] | None = None
        self.current_analysis: dict[str, Any] | None = None
        self.palette = PALETTES.get(str(self.settings.get("theme", "light")), PALETTES["light"])
        self._seeking = False
        self._last_saved_second = 0
        self._player_error = ""
        self._analyzing_id: str | None = None
        try:
            self.player = Mp3Player()
        except PlayerError as exc:
            self.player = None
            self._player_error = str(exc)

        self._apply_style()
        self._scan_workspace_audio()
        self._build_ui()
        self._apply_widget_colors()
        self._refresh_library()
        self._update_player_tick()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_style(self) -> None:
        self.palette = PALETTES.get(str(self.settings.get("theme", "light")), PALETTES["light"])
        palette = self.palette
        style = ttk.Style(self.root)
        style.theme_use("clam")
        self.root.configure(bg=palette["app_bg"])
        style.configure(".", background=palette["app_bg"], foreground=palette["text_fg"], fieldbackground=palette["input_bg"])
        style.configure("TFrame", background=palette["app_bg"])
        style.configure("TLabelframe", background=palette["app_bg"], foreground=palette["text_fg"])
        style.configure("TLabelframe.Label", background=palette["app_bg"], foreground=palette["text_fg"])
        style.configure("TLabel", background=palette["app_bg"], foreground=palette["text_fg"])
        style.configure("TButton", padding=(10, 6), background=palette["surface_bg"], foreground=palette["text_fg"])
        style.map("TButton", background=[("active", palette["input_bg"])], foreground=[("active", palette["text_fg"])])
        style.configure("Accent.TButton", padding=(10, 6), background=palette["accent"], foreground=palette["accent_fg"])
        style.map("Accent.TButton", background=[("active", palette["accent"])], foreground=[("active", palette["accent_fg"])])
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), background=palette["app_bg"], foreground=palette["text_fg"])
        style.configure("Status.TLabel", background=palette["app_bg"], foreground=palette["muted_fg"])
        style.configure("TEntry", fieldbackground=palette["input_bg"], foreground=palette["text_fg"], insertcolor=palette["text_fg"])
        style.configure("TCombobox", fieldbackground=palette["input_bg"], foreground=palette["text_fg"], background=palette["surface_bg"])
        style.map("TCombobox", fieldbackground=[("readonly", palette["input_bg"])], foreground=[("readonly", palette["text_fg"])])
        style.configure("TCheckbutton", background=palette["app_bg"], foreground=palette["text_fg"])
        style.map("TCheckbutton", background=[("active", palette["app_bg"])], foreground=[("active", palette["text_fg"])])
        style.configure("TNotebook", background=palette["app_bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=palette["surface_bg"], foreground=palette["text_fg"], padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", palette["input_bg"])], foreground=[("selected", palette["text_fg"])])
        style.configure("Treeview", background=palette["tree_bg"], fieldbackground=palette["tree_bg"], foreground=palette["text_fg"])
        style.map("Treeview", background=[("selected", palette["tree_selected_bg"])], foreground=[("selected", palette["text_fg"])])
        style.configure("Treeview.Heading", background=palette["surface_bg"], foreground=palette["text_fg"])

    def _apply_widget_colors(self) -> None:
        palette = self.palette
        if getattr(self, "summary_text", None) is not None:
            self.summary_text.configure(
                bg=palette["input_bg"],
                fg=palette["text_fg"],
                insertbackground=palette["text_fg"],
                selectbackground=palette["tree_selected_bg"],
                selectforeground=palette["text_fg"],
            )
        if getattr(self, "transcript_list", None) is not None:
            self.transcript_list.configure(
                bg=palette["input_bg"],
                fg=palette["text_fg"],
                selectbackground=palette["tree_selected_bg"],
                selectforeground=palette["text_fg"],
            )

    def _build_ui(self) -> None:
        # Status bar — packed first so it anchors to the very bottom
        self.status_var = tk.StringVar(value=self._player_error or "請載入 MP3 網址或本地檔。")
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel").pack(
            side="bottom", fill="x", padx=PAD, pady=(0, 4))

        # Playback panel — always visible, sits above the status bar
        self._build_playback_panel()

        # Notebook takes all remaining space
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.player_tab = ttk.Frame(self.notebook)
        self.transcript_tab = ttk.Frame(self.notebook)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.player_tab, text="播放器")
        self.notebook.add(self.transcript_tab, text="逐字稿")
        self.notebook.add(self.analysis_tab, text="重點")
        self.notebook.add(self.settings_tab, text="設定")

        self._build_player_tab()
        self._build_transcript_tab()
        self._build_analysis_tab()
        self._build_settings_tab()

        # Global keyboard shortcuts
        self.root.bind("<space>", lambda _e: self._toggle_play())
        self.root.bind("<Left>", lambda _e: self._jump_relative(-5000))
        self.root.bind("<Right>", lambda _e: self._jump_relative(5000))
        self.root.bind("<Control-f>", lambda _e: self._focus_search())

    def _build_playback_panel(self) -> None:
        """Always-visible playback controls below the notebook."""
        panel = ttk.LabelFrame(self.root, text="播放控制")
        panel.pack(side="bottom", fill="x", padx=PAD, pady=(0, PAD))

        # Now-playing title
        title_row = ttk.Frame(panel)
        title_row.pack(fill="x", padx=PAD, pady=(4, 0))
        self.now_playing_var = tk.StringVar(value="尚未載入音訊")
        self.lbl_now_playing = ttk.Label(title_row, textvariable=self.now_playing_var, style="Header.TLabel")
        self.lbl_now_playing.pack(side="left")
        self.lbl_now_playing.bind("<Button-3>", lambda _e: self._rename_current_title())

        # Progress row
        prog_row = ttk.Frame(panel)
        prog_row.pack(fill="x", padx=PAD, pady=(2, 0))
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        ttk.Label(prog_row, textvariable=self.time_var, width=18).pack(side="left")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_scale = ttk.Scale(prog_row, from_=0, to=1000, variable=self.progress_var)
        self.progress_scale.pack(side="left", fill="x", expand=True, padx=PAD)
        self.progress_scale.bind("<ButtonPress-1>", lambda _e: self._begin_seek())
        self.progress_scale.bind("<ButtonRelease-1>", lambda _e: self._end_seek())
        ttk.Button(prog_row, text="匯出 MD", command=lambda: self._export("md")).pack(side="left", padx=(0, 4))
        ttk.Button(prog_row, text="匯出 JSON", command=lambda: self._export("json")).pack(side="left", padx=(0, PAD))

        # Buttons row
        ctrl_row = ttk.Frame(panel)
        ctrl_row.pack(fill="x", padx=PAD, pady=(2, PAD))
        ttk.Button(ctrl_row, text="▶ 播放", command=self._play).pack(side="left", padx=(0, 4))
        ttk.Button(ctrl_row, text="⏸ 暫停", command=self._pause).pack(side="left", padx=(0, 4))
        ttk.Button(ctrl_row, text="⏹ 停止", command=self._stop).pack(side="left", padx=(0, 4))
        ttk.Separator(ctrl_row, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(ctrl_row, text="◀◀ -15s", command=lambda: self._jump_relative(-15000)).pack(side="left", padx=(0, 4))
        ttk.Button(ctrl_row, text="+15s ▶▶", command=lambda: self._jump_relative(15000)).pack(side="left", padx=(0, 4))
        ttk.Separator(ctrl_row, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(ctrl_row, text="音量").pack(side="left", padx=(0, 4))
        self.volume_var = tk.IntVar(value=int(self.settings.get("volume", 80)))
        ttk.Scale(ctrl_row, from_=0, to=100, variable=self.volume_var,
                  command=self._set_volume, length=100).pack(side="left", padx=(0, PAD))

    def _build_player_tab(self) -> None:
        source_frame = ttk.LabelFrame(self.player_tab, text="音訊來源")
        source_frame.pack(fill="x", padx=PAD, pady=PAD)
        self.url_var = tk.StringVar(value="https://filesb.soundon.fm/file/filesb/abf48784-54b4-47b4-a376-b3a344156345.mp3")
        ttk.Entry(source_frame, textvariable=self.url_var).grid(row=0, column=0, sticky="ew", padx=PAD, pady=PAD)
        ttk.Button(source_frame, text="載入網址", command=self._load_url).grid(row=0, column=1, padx=(0, PAD))
        ttk.Button(source_frame, text="開啟檔案", command=self._open_file).grid(row=0, column=2, padx=(0, PAD))
        ttk.Button(source_frame, text="分析音訊", command=self._analyze_current, style="Accent.TButton").grid(row=0, column=3, padx=(0, PAD))
        source_frame.columnconfigure(0, weight=1)

        library_frame = ttk.LabelFrame(self.player_tab, text="播放清單與最近播放")
        library_frame.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        columns = ("title", "duration", "status", "last_played")
        self.library_tree = ttk.Treeview(library_frame, columns=columns, show="headings", height=9)
        self.library_tree.heading("title", text="標題")
        self.library_tree.heading("duration", text="長度")
        self.library_tree.heading("status", text="分析狀態")
        self.library_tree.heading("last_played", text="最後播放")
        self.library_tree.column("title", width=420)
        self.library_tree.column("duration", width=90, anchor="center")
        self.library_tree.column("status", width=110, anchor="center")
        self.library_tree.column("last_played", width=150, anchor="center")
        self.library_tree.pack(side="left", fill="both", expand=True)
        library_scroll = ttk.Scrollbar(library_frame, orient="vertical", command=self.library_tree.yview)
        self.library_tree.configure(yscrollcommand=library_scroll.set)
        library_scroll.pack(side="right", fill="y")
        self.library_tree.bind("<Double-1>", lambda _event: self._load_selected_library_item())
        self.library_tree.bind("<Button-3>", self._show_library_menu)
        self.library_menu = tk.Menu(self.root, tearoff=0)
        self.library_menu.add_command(label="載入", command=self._load_selected_library_item)
        self.library_menu.add_command(label="重新命名", command=self._rename_selected_library_item)
        self.library_menu.add_command(label="重新分析", command=self._analyze_selected_library_item)
        self.library_menu.add_command(label="刪除檔案與分析資料", command=self._delete_selected_library_item)

    def _build_transcript_tab(self) -> None:
        top = ttk.Frame(self.transcript_tab)
        top.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Label(top, text="搜尋逐字稿：").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, PAD))
        search_entry.bind("<KeyRelease>", lambda _event: self._render_transcript())
        ttk.Button(top, text="清除", command=lambda: [self.search_var.set(""), self._render_transcript()]).pack(side="left")
        ttk.Label(top, text="  點擊段落即可跳播", style="Status.TLabel").pack(side="left", padx=(PAD, 0))

        self.transcript_list = tk.Listbox(self.transcript_tab, font=("Segoe UI", 10))
        self.transcript_list.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        # Single-click seeks to that segment
        self.transcript_list.bind("<ButtonRelease-1>", lambda _event: self._seek_selected_transcript())

    def _build_analysis_tab(self) -> None:
        summary_frame = ttk.LabelFrame(self.analysis_tab, text="摘要")
        summary_frame.pack(fill="x", padx=PAD, pady=PAD)
        self.summary_text = tk.Text(summary_frame, height=4, wrap="word")
        self.summary_text.pack(fill="x", padx=PAD, pady=PAD)

        panes = ttk.PanedWindow(self.analysis_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        keyword_frame = ttk.LabelFrame(panes, text="關鍵詞")
        highlight_frame = ttk.LabelFrame(panes, text="重點句")
        panes.add(keyword_frame, weight=1)
        panes.add(highlight_frame, weight=1)

        self.keyword_tree = ttk.Treeview(keyword_frame, columns=("category", "score", "time"), show="tree headings")
        self.keyword_tree.heading("#0", text="詞")
        self.keyword_tree.heading("category", text="分類")
        self.keyword_tree.heading("score", text="分數")
        self.keyword_tree.heading("time", text="時間  （點擊跳播）")
        self.keyword_tree.pack(fill="both", expand=True)
        self.keyword_tree.bind("<ButtonRelease-1>", lambda _event: self._seek_selected_keyword())

        self.highlight_tree = ttk.Treeview(highlight_frame, columns=("time", "reason"), show="tree headings")
        self.highlight_tree.heading("#0", text="重點句")
        self.highlight_tree.heading("time", text="時間  （點擊跳播）")
        self.highlight_tree.heading("reason", text="原因")
        self.highlight_tree.pack(fill="both", expand=True)
        self.highlight_tree.bind("<ButtonRelease-1>", lambda _event: self._seek_selected_highlight())

    def _build_settings_tab(self) -> None:
        form = ttk.Frame(self.settings_tab)
        form.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Label(form, text="ASR 模型（本機）：").grid(row=0, column=0, sticky="w", pady=PAD)
        self.asr_model_var = tk.StringVar(value=str(self.settings.get("asr_model", "tiny")))
        ttk.Combobox(form, textvariable=self.asr_model_var, values=AVAILABLE_ASR_MODELS, state="readonly").grid(row=0, column=1, sticky="ew", pady=PAD)
        lang_label_by_code = {code: label for label, code in AVAILABLE_LANGUAGES}
        lang_labels = [label for label, _code in AVAILABLE_LANGUAGES]
        saved_lang = str(self.settings.get("language", "auto"))
        ttk.Label(form, text="轉錄語言：").grid(row=1, column=0, sticky="w", pady=PAD)
        self.language_var = tk.StringVar(value=lang_label_by_code.get(saved_lang, "自動偵測"))
        ttk.Combobox(form, textvariable=self.language_var, values=lang_labels, state="readonly").grid(row=1, column=1, sticky="ew", pady=PAD)
        ttk.Label(form, text="Hugging Face Token（僅重點分析需要）：").grid(row=2, column=0, sticky="w", pady=PAD)
        self.token_var = tk.StringVar(value=str(self.settings.get("hf_token", "")))
        ttk.Entry(form, textvariable=self.token_var, show="*", width=54).grid(row=2, column=1, sticky="ew", pady=PAD)
        ttk.Label(form, text="分析模型：").grid(row=3, column=0, sticky="w", pady=PAD)
        self.chat_model_var = tk.StringVar(value=str(self.settings.get("chat_model", "")))
        ttk.Combobox(form, textvariable=self.chat_model_var, values=AVAILABLE_CHAT_MODELS).grid(row=3, column=1, sticky="ew", pady=PAD)
        ttk.Label(form, text="主題：").grid(row=4, column=0, sticky="w", pady=PAD)
        theme_label = THEME_LABEL_BY_NAME.get(str(self.settings.get("theme", "light")), "淺色 Light")
        self.theme_var = tk.StringVar(value=theme_label)
        ttk.Combobox(form, textvariable=self.theme_var, values=[label for label, _name in THEME_OPTIONS], state="readonly").grid(row=4, column=1, sticky="ew", pady=PAD)
        self.auto_resume_var = tk.BooleanVar(value=bool(self.settings.get("auto_resume", True)))
        ttk.Checkbutton(form, text="載入音訊時自動從上次位置續播", variable=self.auto_resume_var).grid(row=5, column=1, sticky="w", pady=PAD)
        self.privacy_var = tk.BooleanVar(value=bool(self.settings.get("privacy_acknowledged", False)))
        ttk.Checkbutton(form, text="我了解重點分析會將逐字稿送到雲端 HF API（轉錄在本機執行）", variable=self.privacy_var).grid(row=6, column=1, sticky="w", pady=PAD)
        ttk.Button(form, text="儲存設定", command=self._save_settings, style="Accent.TButton").grid(row=7, column=1, sticky="e", pady=PAD)
        form.columnconfigure(1, weight=1)

        note = (
            "語音轉錄使用本機 faster-whisper（首次使用某模型會自動下載）。"
            "重點分析需 HF Token；若無 Token 則自動使用本地 TF-IDF 分析。"
        )
        ttk.Label(self.settings_tab, text=note, wraplength=900, style="Status.TLabel").pack(fill="x", padx=PAD)

    def _scan_workspace_audio(self) -> None:
        library = storage.load_library()
        for path in Path.cwd().glob("*.mp3"):
            try:
                source = source_manager.register_local_file(str(path))
                if str(source["id"]) not in library:
                    storage.upsert_audio_source(source)
            except Exception:
                continue

    def _refresh_library(self) -> None:
        for item in self.library_tree.get_children():
            self.library_tree.delete(item)
        entries = sorted(storage.load_library().values(), key=lambda entry: entry.get("last_played_ts", entry.get("created_ts", 0)), reverse=True)
        for entry in entries:
            status = str(entry.get("analysis_status", "not_started"))
            if status == "failed" and entry.get("last_error"):
                status = f"failed: {str(entry.get('last_error'))[:48]}"
            elif status == "failed":
                status = "failed: 請右鍵重新分析"
            self.library_tree.insert("", "end", iid=str(entry["id"]), values=(
                entry.get("title", ""),
                format_ms(entry.get("duration_ms", 0)),
                status,
                _fmt_ts(entry.get("last_played_ts")),
            ))

    def _rename_selected_library_item(self) -> None:
        from tkinter import simpledialog
        selected = self.library_tree.selection()
        if not selected:
            return
        audio_id = selected[0]
        source = storage.load_library().get(audio_id)
        if not source:
            return
        current = str(source.get("title", ""))
        new_name = simpledialog.askstring("重新命名", "請輸入新標題：", initialvalue=current, parent=self.root)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        source["title"] = new_name
        storage.upsert_audio_source(source)
        if self.current_source and str(self.current_source.get("id")) == audio_id:
            self.current_source["title"] = new_name
            self.now_playing_var.set(new_name)
        self._refresh_library()
        self.status_var.set(f"已重新命名：{new_name}")

    def _rename_current_title(self) -> None:
        if not self.current_source:
            return
        from tkinter import simpledialog
        current = str(self.current_source.get("title", ""))
        new_name = simpledialog.askstring("改檔名", "請輸入新標題：", initialvalue=current, parent=self.root)
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        self.current_source["title"] = new_name
        storage.upsert_audio_source(self.current_source)
        self.now_playing_var.set(new_name)
        self._refresh_library()
        self.status_var.set(f"已重新命名：{new_name}")

    def _show_library_menu(self, event) -> None:
        item_id = self.library_tree.identify_row(event.y)
        if item_id:
            self.library_tree.selection_set(item_id)
            self.library_tree.focus(item_id)
            self.library_menu.tk_popup(event.x_root, event.y_root)

    def _load_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("提示", "請輸入 MP3 網址。")
            return
        self._run_background("載入網址", lambda: source_manager.download_url(url, self._thread_status), self._on_source_loaded)

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("MP3 音訊", "*.mp3"), ("所有檔案", "*.*")])
        if path:
            self._run_background("開啟檔案", lambda: source_manager.register_local_file(path), self._on_source_loaded)

    def _run_background(self, label: str, work, on_success) -> None:
        self.status_var.set(f"{label}中...")

        def worker() -> None:
            try:
                result = work()
                self.root.after(0, on_success, result)
            except Exception as exc:
                self.root.after(0, self.status_var.set, f"錯誤：{exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _thread_status(self, message: str) -> None:
        self.root.after(0, self.status_var.set, message)

    def _on_source_loaded(self, source: dict[str, Any]) -> None:
        stored = storage.upsert_audio_source(source)
        self._load_source(stored)
        self._refresh_library()

    def _load_selected_library_item(self) -> None:
        selected = self.library_tree.selection()
        if not selected:
            return
        source = storage.load_library().get(selected[0])
        if source:
            self._load_source(source)

    def _load_source(self, source: dict[str, Any]) -> None:
        self.current_source = source
        self.current_transcript = storage.get_transcript(str(source["id"]))
        self.current_analysis = storage.get_analysis(str(source["id"]))
        if not self.player:
            self.status_var.set(self._player_error)
            return
        try:
            self.player.load(str(source.get("local_path") or source.get("source_url")))
            self.player.set_volume(self.volume_var.get())
            resume_ms = int(source.get("last_position_ms", 0) or 0)
            duration_ms = int(source.get("duration_ms", 0) or 0)
            if duration_ms and resume_ms >= duration_ms - 1000:
                resume_ms = 0
            if self.settings.get("auto_resume") and resume_ms > 0:
                self.player.seek(resume_ms)
            title = str(source.get('title', ''))
            self.status_var.set(f"已載入：{title}")
            self.now_playing_var.set(title or "（無標題）")
            self._render_transcript()
            self._render_analysis()
        except Exception as exc:
            self.status_var.set(f"播放載入失敗：{exc}")

    def _play(self) -> None:
        if not self.player:
            self.status_var.set(self._player_error)
            return
        try:
            self.player.play()
            backend = self.player.backend_name() if hasattr(self.player, "backend_name") else "player"
            self.status_var.set(f"播放中（{backend}）")
        except Exception as exc:
            self.status_var.set(f"播放失敗：{exc}")

    def _pause(self) -> None:
        if self.player:
            self.player.pause()
            self.status_var.set("已暫停")

    def _stop(self) -> None:
        if self.player:
            self.player.stop()
            self.status_var.set("已停止")

    def _toggle_play(self) -> None:
        if self.player and self.player.is_playing():
            self._pause()
        else:
            self._play()

    def _jump_relative(self, delta_ms: int) -> None:
        if not self.player:
            return
        self.player.seek(self.player.get_position_ms() + delta_ms)

    def _begin_seek(self) -> None:
        self._seeking = True

    def _end_seek(self) -> None:
        if not self.player:
            return
        duration = self.player.get_duration_ms()
        target = int((self.progress_var.get() / 1000) * duration) if duration else 0
        self.player.seek(target)
        self._seeking = False

    def _set_volume(self, _value=None) -> None:
        if self.player:
            self.player.set_volume(self.volume_var.get())

    def _update_player_tick(self) -> None:
        if self.player:
            try:
                position = self.player.get_position_ms()
                duration = self.player.get_duration_ms()
                self.time_var.set(f"{format_ms(position)} / {format_ms(duration)}")
                if duration > 0 and not self._seeking:
                    self.progress_var.set((position / duration) * 1000)
                if self.current_source and int(time.time()) != self._last_saved_second:
                    self._last_saved_second = int(time.time())
                    storage.update_playback_state(str(self.current_source["id"]), position, duration)
            except Exception:
                pass
        storage.flush_library()
        self.root.after(500, self._update_player_tick)

    def _analyze_current(self) -> None:
        if not self.current_source:
            messagebox.showinfo("提示", "請先載入音訊。")
            return
        audio_id = str(self.current_source["id"])
        if self._analyzing_id == audio_id:
            self.status_var.set("此音訊正在分析中，請稍候。")
            return
        self._save_settings(show_message=False)
        if not str(self.settings.get("asr_model", "")).strip():
            messagebox.showwarning("缺少 ASR 模型", "請先到設定選擇 ASR 模型大小。")
            self.notebook.select(self.settings_tab)
            return
        local_path = Path(str(self.current_source.get("local_path", "")))
        if not local_path.exists():
            messagebox.showwarning("找不到音訊快取", "請重新載入網址或本地檔後再分析。")
            return
        source = dict(self.current_source)
        self._analyzing_id = audio_id

        def worker() -> None:
            aid = str(source["id"])
            try:
                storage.update_analysis_status(aid, "transcribing")
                model_size = self.settings.get("asr_model", "tiny")
                language = self.settings.get("language", "auto")
                self._thread_status(f"準備 Whisper {model_size} 模型...")
                transcript = api_client.transcribe_audio(
                    hf_token=self.settings.get("hf_token", ""),
                    asr_model=model_size,
                    audio_path=str(source.get("local_path", "")),
                    duration_ms=int(source.get("duration_ms", 0) or 0),
                    status_callback=self._thread_status,
                    language=language,
                )
                storage.save_transcript(aid, transcript)
                used_model = str(transcript.get("asr_model", self.settings.get("asr_model", "")))
                storage.update_analysis_status(aid, "analyzing")
                self._thread_status(f"轉錄完成（ASR: {used_model}），擷取關鍵詞與重點句...")
                analysis = api_client.analyze_transcript(
                    hf_token=self.settings.get("hf_token", ""),
                    chat_model=self.settings.get("chat_model", ""),
                    chunks=transcript.get("chunks", []),
                )
                storage.save_analysis(aid, analysis)
                self.root.after(0, self._analysis_completed, transcript, analysis)
            except Exception as exc:
                message = str(exc)
                storage.update_analysis_status(aid, "failed", message)
                self.root.after(0, self.status_var.set, f"分析失敗：{message}")
                self.root.after(0, messagebox.showerror, "分析失敗", message)
                self.root.after(0, self._refresh_library)
            finally:
                self._analyzing_id = None

        threading.Thread(target=worker, daemon=True).start()

    def _analyze_selected_library_item(self) -> None:
        selected = self.library_tree.selection()
        if not selected:
            return
        source = storage.load_library().get(str(selected[0]))
        if not source:
            return
        # Only reload player if this is a different audio from what's currently loaded
        current_id = str(self.current_source["id"]) if self.current_source else ""
        if str(source.get("id", "")) != current_id:
            self._load_source(source)
        else:
            # Same audio: refresh current_source metadata from storage without disturbing playback
            self.current_source = source
        self._analyze_current()

    def _analysis_completed(self, transcript: dict[str, Any], analysis: dict[str, Any]) -> None:
        self.current_transcript = transcript
        self.current_analysis = analysis
        used_model = str(transcript.get("asr_model", ""))
        self.status_var.set(f"分析完成。ASR：{used_model}" if used_model else "分析完成。")
        self._render_transcript()
        self._render_analysis()
        self._refresh_library()
        self.notebook.select(self.analysis_tab)

    def _render_transcript(self) -> None:
        self.transcript_list.delete(0, "end")
        transcript = self.current_transcript or {}
        query = self.search_var.get().strip().lower()
        for chunk in transcript.get("chunks", []) or []:
            text = str(chunk.get("text", ""))
            if query and query not in text.lower():
                continue
            label = f"[{format_ms(chunk.get('start_ms', 0))}] {text}"
            self.transcript_list.insert("end", label)
            self.transcript_list.itemconfig("end", foreground=self.palette["text_fg"])

    def _delete_selected_library_item(self) -> None:
        selected = self.library_tree.selection()
        if not selected:
            return
        audio_id = str(selected[0])
        source = storage.load_library().get(audio_id)
        if not source:
            return
        title = str(source.get("title", audio_id))
        confirmed = messagebox.askyesno("刪除檔案", f"要刪除『{title}』的播放清單項目、快取檔、逐字稿與分析資料嗎？")
        if not confirmed:
            return
        if self.current_source and str(self.current_source.get("id")) == audio_id:
            if self.player:
                self.player.stop()
            self.current_source = None
            self.current_transcript = None
            self.current_analysis = None
            self.time_var.set("00:00 / 00:00")
            self.progress_var.set(0)
            self._render_transcript()
            self._render_analysis()
        removed = storage.delete_audio_source(audio_id, delete_cached_file=True)
        self._refresh_library()
        self.status_var.set("已刪除檔案與相關資料。" if removed else "找不到要刪除的項目。")

    def _render_analysis(self) -> None:
        self.summary_text.delete("1.0", "end")
        for item in self.keyword_tree.get_children():
            self.keyword_tree.delete(item)
        for item in self.highlight_tree.get_children():
            self.highlight_tree.delete(item)
        analysis = self.current_analysis or {}
        self.summary_text.insert("end", str(analysis.get("summary", "")))
        for index, keyword in enumerate(analysis.get("keywords", []) or []):
            if not isinstance(keyword, dict):
                continue
            timestamps = keyword.get("timestamps", []) or []
            first_ms = timestamps[0].get("start_ms", 0) if timestamps else 0
            self.keyword_tree.insert("", "end", iid=f"kw-{index}", text=keyword.get("term", ""), values=(
                keyword.get("category", "其他"),
                f"{float(keyword.get('score', 0) or 0):.2f}",
                format_ms(first_ms),
            ))
        for index, highlight in enumerate(analysis.get("highlights", []) or []):
            if not isinstance(highlight, dict):
                continue
            text = str(highlight.get("text", ""))
            self.highlight_tree.insert("", "end", iid=f"hl-{index}", text=text[:80], values=(
                format_ms(highlight.get("start_ms", 0)),
                str(highlight.get("reason", ""))[:80],
            ))

    def _seek_selected_transcript(self) -> None:
        selection = self.transcript_list.curselection()
        if not selection or not self.current_transcript:
            return
        visible_text = self.transcript_list.get(selection[0])
        for chunk in self.current_transcript.get("chunks", []) or []:
            if str(chunk.get("text", "")) in visible_text:
                self._seek_to(int(chunk.get("start_ms", 0) or 0))
                return

    def _seek_selected_keyword(self) -> None:
        selected = self.keyword_tree.selection()
        if not selected or not self.current_analysis:
            return
        index = int(selected[0].split("-", 1)[1])
        keyword = self.current_analysis.get("keywords", [])[index]
        timestamps = keyword.get("timestamps", []) or []
        if timestamps:
            self._seek_to(int(timestamps[0].get("start_ms", 0) or 0))

    def _seek_selected_highlight(self) -> None:
        selected = self.highlight_tree.selection()
        if not selected or not self.current_analysis:
            return
        index = int(selected[0].split("-", 1)[1])
        highlight = self.current_analysis.get("highlights", [])[index]
        self._seek_to(int(highlight.get("start_ms", 0) or 0))

    def _seek_to(self, position_ms: int) -> None:
        if self.player:
            self.player.seek(position_ms)
            if not self.player.is_playing():
                self.player.play()
            self.status_var.set(f"已跳到 {format_ms(position_ms)} 並播放")

    def _focus_search(self) -> None:
        self.notebook.select(self.transcript_tab)

    def _export(self, export_type: str) -> None:
        if not self.current_source:
            messagebox.showinfo("提示", "請先載入音訊。")
            return
        title = str(self.current_source.get("title") or self.current_source.get("id") or "audio")
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:80]
        if export_type == "md":
            save_path = filedialog.asksaveasfilename(
                title="匯出 Markdown",
                initialfile=f"{safe_title}.md",
                defaultextension=".md",
                filetypes=[("Markdown 檔案", "*.md"), ("所有檔案", "*.*")],
            )
            if not save_path:
                return
            path = exporter.export_markdown(self.current_source, self.current_transcript, self.current_analysis, save_path=Path(save_path))
        else:
            save_path = filedialog.asksaveasfilename(
                title="匯出 JSON",
                initialfile=f"{safe_title}.json",
                defaultextension=".json",
                filetypes=[("JSON 檔案", "*.json"), ("所有檔案", "*.*")],
            )
            if not save_path:
                return
            path = exporter.export_json(self.current_source, self.current_transcript, self.current_analysis, save_path=Path(save_path))
        self.status_var.set(f"已匯出：{path}")

    def _save_settings(self, show_message: bool = True) -> None:
        lang_code_by_label = {label: code for label, code in AVAILABLE_LANGUAGES}
        self.settings.update({
            "hf_token": self.token_var.get().strip(),
            "asr_model": self.asr_model_var.get().strip(),
            "chat_model": self.chat_model_var.get().strip(),
            "theme": THEME_NAME_BY_LABEL.get(self.theme_var.get(), "light"),
            "auto_resume": bool(self.auto_resume_var.get()),
            "privacy_acknowledged": bool(self.privacy_var.get()),
            "volume": int(self.volume_var.get()),
            "language": lang_code_by_label.get(self.language_var.get(), "auto"),
        })
        storage.save_settings(self.settings)
        self._apply_style()
        self._apply_widget_colors()
        if show_message:
            self.status_var.set("設定已儲存。")

    def _on_close(self) -> None:
        self._save_settings(show_message=False)
        storage.flush_library()
        if self.player:
            self.player.release()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Drag-and-drop support (requires tkinterdnd2; gracefully skipped
    # when the package is unavailable)
    # ------------------------------------------------------------------
    def _init_dnd(self) -> None:
        """Register the window as a file-drop target if tkinterdnd2 is available."""
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore[import-untyped]
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # tkinterdnd2 not installed or Tk not built with DnD — degrade silently

    def _on_drop(self, event) -> None:
        """Handle files dropped onto the window."""
        raw: str = event.data or ""
        # Windows wraps paths with spaces in {}, and may deliver multiple files.
        paths: list[str] = []
        for token in raw.replace("{", "").replace("}", "").split():
            token = token.strip()
            if token:
                paths.append(token)
        audio_paths = [p for p in paths if Path(p).suffix.lower() in {".mp3", ".wav", ".flac", ".m4a", ".ogg"}]
        if not audio_paths:
            self.status_var.set("請拖放支援的音訊檔案（.mp3 .wav .flac .m4a .ogg）。")
            return
        # Load the first valid audio file
        first = audio_paths[0]
        self._run_background("載入拖放檔案", lambda: source_manager.register_local_file(first), self._on_source_loaded)


def run() -> None:
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore[import-untyped]
        root = TkinterDnD.Tk()
    except Exception:
        root = tk.Tk()
    app = Mp3InsightApp(root)
    app._init_dnd()
    root.mainloop()