#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demi-God Gamer Gauntlet"""

import io
import json
import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, messagebox

try:
    from PIL import Image, ImageOps, ImageTk
except ImportError:
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror("Missing dependency", "Pillow is required.\n\nRun:  pip install Pillow")
    _r.destroy(); raise SystemExit(1)

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# ── Paths ─────────────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR      = os.path.join(SCRIPT_DIR, "dggg-data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
STATS_FILE    = os.path.join(DATA_DIR, "stats.json")

# ── Constants ─────────────────────────────────────────────────────────────────

# Portrait dimensions matching IGDB cover ratios (w × h)
IMAGE_SIZES: dict[str, tuple[int, int]] = {
    "Small":  (66, 94),
    "Medium": (99, 140),
    "Large":  (132, 187),
}

DEFAULT_KEYBINDS: dict[str, str] = {
    "start_next":      "<space>",
    "reset":           "<r>",
    "pause":           "<p>",
    "reset_all_stats": "<Shift-Return>",
    "previous":        "<Left>",
    "next":            "<Right>",
}

KEYBIND_LABELS: dict[str, str] = {
    "start_next":      "Start / Next",
    "reset":           "Reset",
    "pause":           "Pause / Resume",
    "reset_all_stats": "Reset All Stats",
    "previous":        "Previous Game",
    "next":            "Next Game",
}

_DEFAULT_GAME_NAMES = [f"Game {i + 1}" for i in range(15)]
_DEFAULT_IMAGE_IDS  = [""] * 15

DEFAULT_SETTINGS: dict = {
    "image_size":             "Medium",
    "num_games":              5,
    "timer_on":               True,
    "timer_font_size":        13,
    "timer_font_color":       "#48dbfb",
    "timer_keep_on_reset":    False,
    "reset_count_on":         True,
    "resets_font_size":       12,
    "resets_font_color":      "#ff9f43",
    "bg_color":               "#1a1a2e",
    "game_names":             _DEFAULT_GAME_NAMES.copy(),
    "game_title_font_size":   9,
    "game_title_font_color":  "#7777bb",
    "igdb_client_id":         "",
    "igdb_client_secret":     "",
    "game_image_ids":         _DEFAULT_IMAGE_IDS.copy(),
    "keybinds":               DEFAULT_KEYBINDS.copy(),
}

DEFAULT_STATS: dict = {
    "timer_seconds": 0.0,
    "reset_count":   0,
    "current_game":  -1,
    "game_state":    "idle",
}

CONFETTI_COLORS = [
    "#ff6b6b", "#feca57", "#48dbfb", "#ff9ff3",
    "#54a0ff", "#5f27cd", "#00d2d3", "#ff9f43", "#a29bfe",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def display_key(key: str) -> str:
    k = key.strip("<>")
    return k.replace("Shift-", "Shift+").replace("Control-", "Ctrl+").replace("Alt-", "Alt+")

def ensure_event(key: str) -> str:
    key = key.strip()
    return key if key.startswith("<") else f"<{key}>"

def dim_color(hex_color: str, factor: float = 0.40) -> str:
    h = hex_color.lstrip("#")
    r = int(int(h[0:2], 16) * factor)
    g = int(int(h[2:4], 16) * factor)
    b = int(int(h[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def _bind_scroll(widget: tk.Widget, canvas: tk.Canvas) -> None:
    """Recursively bind mouse-wheel to every widget so the settings scroll works."""
    def _scroll(e: tk.Event) -> None:
        canvas.yview_scroll(-1 * (e.delta // 120), "units")
    widget.bind("<MouseWheel>", _scroll, add="+")
    for child in widget.winfo_children():
        _bind_scroll(child, canvas)

# ── IGDB client ───────────────────────────────────────────────────────────────

class IgdbClient:
    _TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    _API_URL   = "https://api.igdb.com/v4"
    _IMG_URL   = "https://images.igdb.com/igdb/image/upload"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._cid    = client_id
        self._secret = client_secret
        self._token  = ""
        self._expiry = 0.0

    def _token_headers(self) -> dict[str, str]:
        if time.time() >= self._expiry - 60:
            r = _req.post(self._TOKEN_URL, params={
                "client_id":     self._cid,
                "client_secret": self._secret,
                "grant_type":    "client_credentials",
            }, timeout=10)
            r.raise_for_status()
            d = r.json()
            self._token  = d["access_token"]
            self._expiry = time.time() + d["expires_in"]
        return {"Client-ID": self._cid, "Authorization": f"Bearer {self._token}"}

    def search(self, query: str, limit: int = 15) -> list[dict]:
        r = _req.post(
            f"{self._API_URL}/games",
            headers=self._token_headers(),
            data=f'search "{query}"; fields name,cover.image_id; limit {limit};',
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def cover_url(self, image_id: str, size: str = "t_cover_big") -> str:
        return f"{self._IMG_URL}/{size}/{image_id}.jpg"

    def fetch_image(self, image_id: str, size: str = "t_cover_small") -> Image.Image:
        # (connect_timeout, read_timeout) — avoids a single value doubling the wait
        r = _req.get(self.cover_url(image_id, size), timeout=(5, 15))
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")

# ── Main application ──────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Demi-God Gamer Gauntlet")
        self.root.resizable(True, True)
        self.root.minsize(480, 180)

        self.settings: dict = self._load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        self.stats:    dict = self._load_json(STATS_FILE,    DEFAULT_STATS)

        kb: dict = DEFAULT_KEYBINDS.copy()
        kb.update(self.settings.get("keybinds", {}))
        self.settings["keybinds"] = kb

        # Ensure game_names and game_image_ids are always 15 entries long
        names = self.settings.get("game_names", [])
        while len(names) < 15:
            names.append(f"Game {len(names) + 1}")
        self.settings["game_names"] = names[:15]

        ids = self.settings.get("game_image_ids", [])
        while len(ids) < 15:
            ids.append("")
        self.settings["game_image_ids"] = ids[:15]

        self.num_games = max(2, min(15, int(self.settings.get("num_games", 5))))

        saved_state = self.stats.get("game_state", "idle")
        if saved_state == "running":
            saved_state = "paused"
        self.game_state   = saved_state
        self.current_game = self.stats.get("current_game", -1)

        self._elapsed:      float      = float(self.stats.get("timer_seconds", 0.0))
        self._elapsed_base: float      = 0.0
        self._timer_start:  float|None = None
        self._timer_job:    str|None   = None
        self._bound_keys:   list[str]  = []

        self.pil_images: list[Image.Image|None] = [None] * 15
        self._load_images()
        self._build_ui()
        self._bind_keys()
        self._refresh_images()
        self._refresh_stats()
        self._restore_status()
        # Fetch any IGDB covers that aren't on disk yet (non-blocking)
        self.root.after(200, self._fetch_igdb_images_bg)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_json(self, path: str, default: dict) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {**default, **data}
        except Exception:
            return dict(default)

    def _save_json(self, path: str, data: dict) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_settings(self) -> None:
        self._save_json(SETTINGS_FILE, self.settings)

    def _save_stats(self) -> None:
        self.stats["timer_seconds"] = self._elapsed
        self.stats["current_game"]  = self.current_game
        self.stats["game_state"]    = self.game_state
        self._save_json(STATS_FILE, self.stats)

    # ── Images ────────────────────────────────────────────────────────────────

    def _load_images(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        shades = [
            (50, 40, 120), (40, 70, 140), (60, 30, 110), (30, 60, 130), (55, 45, 115),
            (45, 55, 125), (35, 65, 135), (65, 35, 105), (25, 55, 125), (50, 50, 110),
            (42, 48, 118), (38, 62, 132), (58, 32, 108), (28, 58, 128), (52, 42, 112),
        ]
        for i in range(15):
            self.pil_images[i] = Image.new("RGB", (264, 374), shades[i % len(shades)])

    def _fetch_igdb_images_bg(self) -> None:
        """On startup, fetch all IGDB covers that have a stored image_id."""
        if not REQUESTS_OK:
            return
        cid = self.settings.get("igdb_client_id", "").strip()
        cs  = self.settings.get("igdb_client_secret", "").strip()
        if not cid or not cs:
            return
        image_ids: list[str] = self.settings.get("game_image_ids", [""] * 15)
        while len(image_ids) < 15:
            image_ids.append("")
        client = IgdbClient(cid, cs)
        for slot, image_id in enumerate(image_ids):
            if not image_id:
                continue
            def _fetch(s=slot, iid=image_id):
                try:
                    pil = client.fetch_image(iid, "t_cover_big")
                    self.pil_images[s] = pil
                    self.root.after(0, self._refresh_images)
                except Exception:
                    pass
            threading.Thread(target=_fetch, daemon=True).start()

    def _refresh_images(self) -> None:
        w, h   = IMAGE_SIZES.get(self.settings.get("image_size", "Medium"), (176, 250))
        bg     = self.settings.get("bg_color", "#1a1a2e")
        names  = self.settings.get("game_names", DEFAULT_SETTINGS["game_names"])
        tsize  = self.settings.get("game_title_font_size", 9)
        tcolor = self.settings.get("game_title_font_color", "#7777bb")

        for i, gf in enumerate(self.game_frames):
            if self.game_state == "done" or i < self.current_game:
                state = "done"
            elif i == self.current_game:
                state = "current"
            else:
                state = "pending"

            img = self.pil_images[i] or Image.new("RGB", (264, 374), (60, 60, 100))
            img = img.resize((w, h), Image.LANCZOS)
            if state == "pending":
                img = ImageOps.grayscale(img).convert("RGB")

            photo = ImageTk.PhotoImage(img)
            gf["_photo"] = photo
            gf["label"].configure(image=photo, bg=bg)

            border_color = "#00ff88" if state == "current" else bg
            pad = 4 if state == "current" else 0
            gf["border"].configure(bg=border_color, padx=pad, pady=pad)
            gf["inner"].configure(bg=bg)

            name = names[i] if i < len(names) else f"Game {i + 1}"
            gf["num"].configure(text=name, bg=bg, fg=tcolor,
                                font=("Segoe UI", tsize, "bold"))

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        bg = self.settings.get("bg_color", "#1a1a2e")
        self.root.configure(bg=bg)

        # Top bar
        self._top = tk.Frame(self.root, bg=bg)
        self._top.pack(fill="x", padx=14, pady=(10, 2))

        self._title_lbl = tk.Label(
            self._top, text="Demi-God Gamer Gauntlet",
            font=("Segoe UI", 17, "bold"), fg="#f0c040", bg=bg,
        )
        self._title_lbl.pack(side="left")

        self._right = tk.Frame(self._top, bg=bg)
        self._right.pack(side="right")

        options_btn = tk.Menubutton(
            self._right, text="Options  ▾", relief="flat",
            font=("Segoe UI", 11), fg="white", bg="#2d2d50",
            activeforeground="white", activebackground="#44447a",
            padx=10, pady=5, cursor="hand2",
        )
        omenu = tk.Menu(options_btn, tearoff=0, bg="#2d2d50", fg="white",
                        activebackground="#44447a", activeforeground="white",
                        font=("Segoe UI", 11))
        omenu.add_command(label="Start",          command=self.cmd_start)
        omenu.add_command(label="Next",           command=self.cmd_next)
        omenu.add_command(label="Previous",       command=self.cmd_previous)
        omenu.add_separator()
        omenu.add_command(label="Pause / Resume", command=self.cmd_pause)
        omenu.add_command(label="Reset",          command=self.cmd_reset)
        options_btn.configure(menu=omenu)
        options_btn.pack(side="left", padx=(0, 6))

        tk.Button(
            self._right, text="⚙  Settings", relief="flat",
            font=("Segoe UI", 11), fg="white", bg="#2d2d50",
            activeforeground="white", activebackground="#44447a",
            padx=10, pady=5, cursor="hand2", command=self.open_settings,
        ).pack(side="left")

        # Status bar (full-width)
        self._status_bar = tk.Frame(self.root, bg=bg)
        self._status_bar.pack(fill="x", padx=14, pady=(0, 2))
        self.status_lbl = tk.Label(
            self._status_bar, text="Press Start or Space to begin",
            font=("Segoe UI", 10, "italic"), fg="#888aaa", bg=bg, anchor="e",
        )
        self.status_lbl.pack(side="right")

        # Content frame — shrink-wraps to images so timer left-aligns with Game 1
        self._content = tk.Frame(self.root, bg=bg)
        self._content.pack(padx=14, pady=(2, 14), anchor="w")

        self._stats_bar = tk.Frame(self._content, bg=bg)
        self._stats_bar.pack(fill="x", pady=(0, 6))

        tsize  = self.settings.get("timer_font_size",   13)
        tcolor = self.settings.get("timer_font_color",  "#48dbfb")
        rsize  = self.settings.get("resets_font_size",  12)
        rcolor = self.settings.get("resets_font_color", "#ff9f43")

        self.timer_lbl = tk.Label(
            self._stats_bar, text="⏱  00:00:00",
            font=("Consolas", tsize, "bold"), fg=tcolor, bg=bg,
        )
        self.resets_lbl = tk.Label(
            self._stats_bar, text="↺  Resets: 0",
            font=("Segoe UI", rsize, "bold"), fg=rcolor, bg=bg,
        )
        self.timer_lbl.pack(side="left", padx=(0, 20))
        self.resets_lbl.pack(side="left")

        # Images row
        self._img_row = tk.Frame(self._content, bg=bg)
        self._img_row.pack()

        self.game_frames: list[dict] = []
        self._rebuild_game_frames()

    def _rebuild_game_frames(self) -> None:
        bg = self.settings.get("bg_color", "#1a1a2e")
        for gf in self.game_frames:
            gf["col"].destroy()
        self.game_frames.clear()
        for i in range(self.num_games):
            col    = tk.Frame(self._img_row, bg=bg)
            col.pack(side="left", padx=8)
            border = tk.Frame(col, bg=bg)
            border.pack()
            inner  = tk.Frame(border, bg=bg)
            inner.pack()
            lbl    = tk.Label(inner, bg=bg, bd=0, cursor="arrow")
            lbl.pack()
            num    = tk.Label(col, text=f"Game {i + 1}",
                              font=("Segoe UI", 9, "bold"), fg="#555577", bg=bg)
            num.pack(pady=(3, 0))
            self.game_frames.append({
                "col": col, "border": border, "inner": inner,
                "label": lbl, "num": num, "_photo": None,
            })

    def _theme_widgets(self) -> list:
        return (
            [self.root, self._top, self._title_lbl, self._right,
             self._status_bar, self.status_lbl,
             self._content, self._stats_bar,
             self.timer_lbl, self.resets_lbl, self._img_row]
            + [w for gf in self.game_frames
               for w in (gf["col"], gf["border"], gf["inner"], gf["label"], gf["num"])]
        )

    def _apply_theme(self) -> None:
        bg = self.settings.get("bg_color", "#1a1a2e")
        for w in self._theme_widgets():
            try:
                w.configure(bg=bg)
            except Exception:
                pass
        self.timer_lbl.configure(
            fg=self.settings.get("timer_font_color", "#48dbfb"),
            font=("Consolas", self.settings.get("timer_font_size", 13), "bold"),
        )
        self.resets_lbl.configure(
            fg=self.settings.get("resets_font_color", "#ff9f43"),
            font=("Segoe UI", self.settings.get("resets_font_size", 12), "bold"),
        )

    # ── Stats display ─────────────────────────────────────────────────────────

    def _refresh_stats(self) -> None:
        e = self._elapsed
        h, rem = divmod(int(e), 3600)
        m, s   = divmod(rem, 60)
        self.timer_lbl.configure(text=f"⏱  {h:02d}:{m:02d}:{s:02d}")
        self.resets_lbl.configure(text=f"↺  Resets: {self.stats.get('reset_count', 0)}")

        self.timer_lbl.pack_forget()
        self.resets_lbl.pack_forget()
        if self.settings.get("timer_on", True):
            self.timer_lbl.pack(side="left", padx=(0, 20))
        if self.settings.get("reset_count_on", True):
            self.resets_lbl.pack(side="left")

    def _restore_status(self) -> None:
        gs, cg = self.game_state, self.current_game
        names  = self.settings.get("game_names", DEFAULT_SETTINGS["game_names"])
        if gs == "idle":
            self._set_status("Press Start or Space to begin")
        elif gs == "paused":
            name = names[cg] if 0 <= cg < len(names) else f"Game {cg + 1}"
            self._set_status(f"Paused  —  {name}  (restored from last session)")
        elif gs == "done":
            self._set_status("All 5 games complete! \U0001f389")

    def _set_status(self, text: str) -> None:
        self.status_lbl.configure(text=text)

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _start_timer(self) -> None:
        self._elapsed_base = self._elapsed
        self._timer_start  = time.monotonic()
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
        self._tick()

    def _pause_timer(self) -> None:
        if self._timer_job is not None:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None
        if self._timer_start is not None:
            self._elapsed     = self._elapsed_base + (time.monotonic() - self._timer_start)
            self._timer_start = None
        self._save_stats()

    def _tick(self) -> None:
        if self.game_state != "running":
            return
        self._elapsed = self._elapsed_base + (time.monotonic() - self._timer_start)
        self._refresh_stats()
        self._save_stats()
        self._timer_job = self.root.after(1000, self._tick)

    # ── Keybinds ──────────────────────────────────────────────────────────────

    def _bind_keys(self) -> None:
        for key in self._bound_keys:
            try:
                self.root.unbind(key)
            except Exception:
                pass
        self._bound_keys.clear()

        handlers: dict = {
            "start_next":      lambda e: self.cmd_start_next(),
            "reset":           lambda e: self.cmd_reset(),
            "pause":           lambda e: self.cmd_pause(),
            "reset_all_stats": lambda e: self.cmd_reset_all_stats(),
            "previous":        lambda e: self.cmd_previous(),
            "next":            lambda e: self.cmd_next(),
        }
        for action, handler in handlers.items():
            raw = self.settings["keybinds"].get(action, DEFAULT_KEYBINDS[action])
            key = ensure_event(raw)
            try:
                self.root.bind(key, handler)
                self._bound_keys.append(key)
            except Exception as exc:
                print(f"Could not bind {key!r}: {exc}")

    # ── Commands ──────────────────────────────────────────────────────────────

    def _game_name(self, index: int) -> str:
        names = self.settings.get("game_names", DEFAULT_SETTINGS["game_names"])
        if 0 <= index < len(names) and names[index].strip():
            return names[index]
        return f"Game {index + 1}"

    def cmd_start(self) -> None:
        if self.game_state != "idle":
            return
        self.current_game = 0
        self.game_state   = "running"
        self._start_timer()
        self._refresh_images()
        self._set_status(f"Running  —  {self._game_name(0)}")

    def cmd_start_next(self) -> None:
        if self.game_state == "idle":
            self.cmd_start()
        else:
            self.cmd_next()

    def cmd_next(self) -> None:
        if self.game_state not in ("running", "paused"):
            return
        if self.current_game >= self.num_games - 1:
            self.game_state = "done"
            self._pause_timer()
            self._refresh_images()
            self._set_status("All 5 games complete! \U0001f389")
            self._launch_confetti()
        else:
            self.current_game += 1
            if self.game_state == "paused":
                self.game_state = "running"
                self._start_timer()
            self._refresh_images()
            self._set_status(f"Running  —  {self._game_name(self.current_game)}")

    def cmd_previous(self) -> None:
        if self.game_state not in ("running", "paused"):
            return
        if self.current_game > 0:
            self.current_game -= 1
            self._refresh_images()
            self._set_status(f"Running  —  {self._game_name(self.current_game)}")

    def cmd_pause(self) -> None:
        if self.game_state == "running":
            self.game_state = "paused"
            self._pause_timer()
            self._set_status(f"Paused  —  {self._game_name(self.current_game)}")
        elif self.game_state == "paused":
            self.game_state = "running"
            self._start_timer()
            self._set_status(f"Running  —  {self._game_name(self.current_game)}")

    def cmd_reset(self) -> None:
        keep = self.settings.get("timer_keep_on_reset", False)
        self.stats["reset_count"] = self.stats.get("reset_count", 0) + 1

        if keep:
            self.current_game = 0
            self.game_state   = "running"
            if self._timer_start is None:
                self._start_timer()
            self._refresh_images()
            self._refresh_stats()
            self._set_status(f"Reset  —  Running  {self._game_name(0)}")
        else:
            self._pause_timer()
            self.game_state   = "idle"
            self.current_game = -1
            self._elapsed       = 0.0
            self._elapsed_base  = 0.0
            self._timer_start   = None
            self._refresh_images()
            self._refresh_stats()
            self._set_status("Reset  —  Press Start or Space to begin")

        self._save_stats()

    def cmd_reset_all_stats(self) -> None:
        if not messagebox.askyesno(
            "Reset All Stats",
            "Reset the timer and reset count to 0?\n\nThis cannot be undone.",
            icon="warning", parent=self.root,
        ):
            return
        self._pause_timer()
        self.game_state   = "idle"
        self.current_game = -1
        self._elapsed = self._elapsed_base = 0.0
        self._timer_start = None
        self.stats["reset_count"] = self.stats["timer_seconds"] = 0
        self._save_stats()
        self._refresh_images()
        self._refresh_stats()
        self._set_status("All stats reset  —  Press Start or Space to begin")

    # ── Confetti ──────────────────────────────────────────────────────────────

    def _launch_confetti(self) -> None:
        self.root.update_idletasks()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.geometry(f"{rw}x{rh}+{rx}+{ry}")
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-transparentcolor", "#010203")
        except Exception:
            pass
        overlay.lift()

        canvas = tk.Canvas(overlay, bg="#010203", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        particles = [
            {
                "x": random.uniform(0, rw), "y": random.uniform(-80, 0),
                "vx": random.uniform(-2.0, 2.0), "vy": random.uniform(2.5, 7.0),
                "g": random.uniform(0.06, 0.18), "color": random.choice(CONFETTI_COLORS),
                "w": random.randint(7, 14), "h": random.randint(4, 8),
            }
            for _ in range(180)
        ]
        end_mono = time.monotonic() + 10.0

        def animate() -> None:
            if not overlay.winfo_exists():
                return
            if time.monotonic() > end_mono:
                try: overlay.destroy()
                except Exception: pass
                return
            canvas.delete("all")
            alive = []
            for p in particles:
                p["x"] += p["vx"]; p["y"] += p["vy"]; p["vy"] += p["g"]
                if p["y"] < rh + 20:
                    alive.append(p)
                    canvas.create_rectangle(
                        p["x"] - p["w"] // 2, p["y"] - p["h"] // 2,
                        p["x"] + p["w"] // 2, p["y"] + p["h"] // 2,
                        fill=p["color"], outline="",
                    )
            particles[:] = alive
            if alive: overlay.after(25, animate)
            else:
                try: overlay.destroy()
                except Exception: pass

        animate()

    # ── IGDB Search dialog ────────────────────────────────────────────────────

    def open_search_dialog(self, slot: int, name_var: tk.StringVar,
                           parent: tk.Toplevel) -> None:
        if not REQUESTS_OK:
            messagebox.showerror("Missing library",
                                 "The 'requests' library is required for IGDB search.\n\n"
                                 "Run:  pip install requests", parent=parent)
            return

        cid = self.settings.get("igdb_client_id", "").strip()
        cs  = self.settings.get("igdb_client_secret", "").strip()
        if not cid or not cs:
            messagebox.showerror("No credentials",
                                 "Enter your Twitch Client ID and Secret in Settings → IGDB first.",
                                 parent=parent)
            return

        client = IgdbClient(cid, cs)

        B  = "#16162a"
        FG = "#dde0f5"
        AC = "#2a2a4a"
        HL = "#3c3c6a"
        CELL_BG   = "#1e1e38"
        CELL_HOV  = "#2a2a52"
        THUMB_W, THUMB_H = 90, 128
        COLS = 4

        dlg = tk.Toplevel(parent)
        dlg.title(f"Search IGDB  —  Game {slot + 1}")
        dlg.configure(bg=B)
        dlg.geometry("500x580")
        dlg.resizable(True, True)
        dlg.grab_set()
        dlg.transient(parent)

        # ── Search bar ────────────────────────────────────────────
        top_f = tk.Frame(dlg, bg=B)
        top_f.pack(fill="x", padx=12, pady=(12, 4))

        query_var = tk.StringVar(value=name_var.get())
        entry = tk.Entry(top_f, textvariable=query_var,
                         font=("Segoe UI", 11), bg=AC, fg=FG,
                         insertbackground=FG, relief="flat")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=4)
        entry.focus_set()
        entry.select_range(0, "end")

        status_var = tk.StringVar(value="Type a game name and press Search")
        status_lbl = tk.Label(dlg, textvariable=status_var,
                              font=("Segoe UI", 9, "italic"), fg="#888aaa",
                              bg=B, anchor="w")
        status_lbl.pack(fill="x", padx=14, pady=(0, 4))

        # ── Results canvas + scrollbar ────────────────────────────
        res_outer = tk.Frame(dlg, bg=B)
        res_outer.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        res_canvas = tk.Canvas(res_outer, bg=B, highlightthickness=0)
        res_sb     = tk.Scrollbar(res_outer, orient="vertical", command=res_canvas.yview)
        res_canvas.configure(yscrollcommand=res_sb.set)
        res_sb.pack(side="right", fill="y")
        res_canvas.pack(side="left", fill="both", expand=True)

        res_frame = tk.Frame(res_canvas, bg=B)
        res_win   = res_canvas.create_window((0, 0), window=res_frame, anchor="nw")

        def _on_res_cfg(e: tk.Event) -> None:
            res_canvas.configure(scrollregion=res_canvas.bbox("all"))
        def _on_res_canvas_cfg(e: tk.Event) -> None:
            res_canvas.itemconfig(res_win, width=e.width)

        res_frame.bind("<Configure>", _on_res_cfg)
        res_canvas.bind("<Configure>", _on_res_canvas_cfg)
        res_canvas.bind("<MouseWheel>",
                        lambda e: res_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Placeholder thumbnail
        _placeholder = Image.new("RGB", (THUMB_W, THUMB_H), (35, 35, 65))
        placeholder_photo = ImageTk.PhotoImage(_placeholder)

        # Keep photo references alive
        _photo_refs: list = []

        def clear_results() -> None:
            for w in res_frame.winfo_children():
                w.destroy()
            _photo_refs.clear()
            _photo_refs.append(placeholder_photo)  # keep base placeholder alive

        def show_results(results: list[dict]) -> None:
            clear_results()
            if not results:
                status_var.set("No results found.")
                tk.Label(res_frame, text="No results found.",
                         fg="#888aaa", bg=B,
                         font=("Segoe UI", 11, "italic")).pack(pady=30)
                return

            status_var.set(f"{len(results)} result(s) — click a cover to assign")

            for idx, game in enumerate(results):
                r, c = divmod(idx, COLS)
                cell = tk.Frame(res_frame, bg=CELL_BG, cursor="hand2")
                cell.grid(row=r, column=c, padx=5, pady=5, sticky="n")

                img_lbl = tk.Label(cell, image=placeholder_photo,
                                   bg=CELL_BG, cursor="hand2")
                img_lbl.pack(padx=4, pady=(4, 2))

                gname = game.get("name", "Unknown")
                short = (gname[:16] + "…") if len(gname) > 16 else gname
                tk.Label(cell, text=short, fg=FG, bg=CELL_BG,
                         font=("Segoe UI", 8), wraplength=THUMB_W,
                         justify="center").pack(padx=4, pady=(0, 4))

                def _enter(e, f=cell):
                    f.configure(bg=CELL_HOV)
                    for w in f.winfo_children(): w.configure(bg=CELL_HOV)
                def _leave(e, f=cell):
                    f.configure(bg=CELL_BG)
                    for w in f.winfo_children(): w.configure(bg=CELL_BG)

                cell.bind("<Enter>", _enter)
                cell.bind("<Leave>", _leave)

                def _select(e=None, g=game):
                    assign_game(g)

                cell.bind("<Button-1>", _select)
                for child in cell.winfo_children():
                    child.bind("<Button-1>", _select)
                    child.bind("<Enter>", _enter)
                    child.bind("<Leave>", _leave)

                # Load thumbnail in background
                image_id = (game.get("cover") or {}).get("image_id")
                if image_id:
                    ref_idx = len(_photo_refs)
                    _photo_refs.append(None)

                    def _load_thumb(iid=image_id, ri=ref_idx, lbl=img_lbl):
                        try:
                            pil   = client.fetch_image(iid, "t_cover_small")
                            pil   = pil.resize((THUMB_W, THUMB_H), Image.LANCZOS)
                            photo = ImageTk.PhotoImage(pil)
                            _photo_refs[ri] = photo
                            dlg.after(0, lambda p=photo, l=lbl: l.configure(image=p))
                        except Exception:
                            pass

                    threading.Thread(target=_load_thumb, daemon=True).start()

        def assign_game(game: dict) -> None:
            name_var.set(game.get("name", name_var.get()))

            image_id = (game.get("cover") or {}).get("image_id")
            if not image_id:
                dlg.destroy()
                return

            status_var.set("Loading cover…")

            def _fetch():
                try:
                    pil = client.fetch_image(image_id, "t_cover_big")
                    # Store image in memory
                    self.pil_images[slot] = pil
                    # Persist the image_id so it re-fetches on next launch
                    ids: list[str] = list(self.settings.get("game_image_ids", [""] * 15))
                    while len(ids) < 15:
                        ids.append("")
                    ids[slot] = image_id
                    self.settings["game_image_ids"] = ids
                    self._save_settings()
                    dlg.after(0, lambda: (self._refresh_images(), dlg.destroy()))
                except Exception as exc:
                    dlg.after(0, lambda e=exc: status_var.set(f"Failed: {e}"))

            threading.Thread(target=_fetch, daemon=True).start()

        def do_search() -> None:
            query = query_var.get().strip()
            if not query:
                return
            status_var.set("Searching…")
            clear_results()

            def _run():
                try:
                    results = client.search(query)
                    dlg.after(0, lambda: show_results(results))
                except Exception as exc:
                    dlg.after(0, lambda: status_var.set(f"Error: {exc}"))

            threading.Thread(target=_run, daemon=True).start()

        search_btn = tk.Button(top_f, text="Search", command=do_search,
                               fg="white", bg="#2d2d50",
                               activeforeground="white", activebackground="#44447a",
                               relief="flat", padx=12, pady=4,
                               font=("Segoe UI", 11), cursor="hand2")
        search_btn.pack(side="left")

        entry.bind("<Return>", lambda e: do_search())

        # Kick off a search immediately if there's a pre-filled name
        if query_var.get().strip():
            dlg.after(100, do_search)

    # ── Settings window ───────────────────────────────────────────────────────

    def open_settings(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.configure(bg="#16162a")
        win.resizable(True, True)
        win.minsize(520, 300)
        win.grab_set()
        win.transient(self.root)

        B  = "#16162a"
        FG = "#dde0f5"
        AC = "#2a2a4a"
        HL = "#3c3c6a"

        # Scrollable container
        outer    = tk.Frame(win, bg=B)
        outer.pack(fill="both", expand=True)
        canvas_s = tk.Canvas(outer, bg=B, highlightthickness=0)
        sb       = tk.Scrollbar(outer, orient="vertical", command=canvas_s.yview)
        canvas_s.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas_s.pack(side="left", fill="both", expand=True)
        inner_frame = tk.Frame(canvas_s, bg=B)
        cwin = canvas_s.create_window((0, 0), window=inner_frame, anchor="nw")

        inner_frame.bind("<Configure>",
                         lambda e: canvas_s.configure(scrollregion=canvas_s.bbox("all")))
        canvas_s.bind("<Configure>",
                      lambda e: canvas_s.itemconfig(cwin, width=e.width))

        # ── Widget helpers ─────────────────────────────────────────
        def section_hdr(text: str) -> None:
            f = tk.Frame(inner_frame, bg=B)
            f.pack(fill="x", padx=0, pady=(12, 0))
            tk.Frame(f, bg=AC, height=1).pack(fill="x")
            tk.Label(f, text=f"  {text}", fg="#7070aa", bg=B,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

        def colour_picker(parent: tk.Widget, label_text: str, initial: str) -> list:
            stored = [initial]
            row = tk.Frame(parent, bg=B)
            row.pack(side="left")
            tk.Label(row, text=label_text, fg=FG, bg=B,
                     font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
            prev = tk.Label(row, width=3, height=1, bg=initial,
                            relief="solid", bd=1)
            prev.pack(side="left", padx=(0, 4))
            def pick(s=stored, p=prev):
                c = colorchooser.askcolor(color=s[0], parent=win, title="Pick Colour")
                if c[1]: s[0] = c[1]; p.configure(bg=c[1])
            tk.Button(row, text="Pick", command=pick,
                      fg=FG, bg=AC, activeforeground=FG, activebackground=HL,
                      relief="flat", padx=8, pady=2,
                      font=("Segoe UI", 9), cursor="hand2").pack(side="left")
            return stored

        def size_spin(parent: tk.Widget, initial: int) -> tk.IntVar:
            var = tk.IntVar(value=initial)
            tk.Label(parent, text="Size:", fg=FG, bg=B,
                     font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
            tk.Spinbox(parent, from_=6, to=72, textvariable=var, width=4,
                       font=("Segoe UI", 10), bg=AC, fg=FG,
                       buttonbackground=HL, relief="flat").pack(side="left", padx=(0, 16))
            return var

        def checkbox(parent: tk.Widget, text: str, initial: bool) -> tk.BooleanVar:
            var = tk.BooleanVar(value=initial)
            tk.Checkbutton(parent, text=text, variable=var,
                           fg=FG, bg=B, selectcolor=AC,
                           activeforeground=FG, activebackground=B,
                           font=("Segoe UI", 11)).pack(side="left", padx=(0, 16))
            return var

        # ── IMAGE SIZE ─────────────────────────────────────────────
        section_hdr("IMAGE SIZE")
        sz_f = tk.Frame(inner_frame, bg=B)
        sz_f.pack(fill="x", padx=16, pady=6)
        size_var = tk.StringVar(value=self.settings.get("image_size", "Medium"))
        for s in ("Small", "Medium", "Large"):
            tk.Radiobutton(sz_f, text=s, variable=size_var, value=s,
                           fg=FG, bg=B, selectcolor=AC,
                           activeforeground=FG, activebackground=B,
                           font=("Segoe UI", 11)).pack(side="left", padx=(0, 16))

        # ── NUMBER OF GAMES ────────────────────────────────────────
        section_hdr("NUMBER OF GAMES")
        ng_f = tk.Frame(inner_frame, bg=B)
        ng_f.pack(fill="x", padx=16, pady=6)
        num_games_var = tk.IntVar(value=self.settings.get("num_games", 5))
        tk.Label(ng_f, text="Games in challenge:", fg=FG, bg=B,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        tk.Spinbox(ng_f, from_=2, to=15, textvariable=num_games_var, width=4,
                   font=("Segoe UI", 10), bg=AC, fg=FG,
                   buttonbackground=HL, relief="flat").pack(side="left")

        # ── TIMER ─────────────────────────────────────────────────
        section_hdr("TIMER")
        t_f = tk.Frame(inner_frame, bg=B)
        t_f.pack(fill="x", padx=16, pady=4)
        timer_on_var   = checkbox(t_f, "Show Timer", self.settings.get("timer_on", True))
        timer_size_var = size_spin(t_f, self.settings.get("timer_font_size", 13))
        timer_color    = colour_picker(t_f, "Colour:", self.settings.get("timer_font_color", "#48dbfb"))

        t_f2 = tk.Frame(inner_frame, bg=B)
        t_f2.pack(fill="x", padx=16, pady=(0, 4))
        timer_keep_var = checkbox(t_f2, "Keep timer running through resets",
                                  self.settings.get("timer_keep_on_reset", False))
        tk.Label(t_f2, text="(resets jump straight back to Game 1, timer keeps going)",
                 fg="#666688", bg=B, font=("Segoe UI", 8, "italic")).pack(side="left")

        # ── RESET COUNT ────────────────────────────────────────────
        section_hdr("RESET COUNT")
        r_f = tk.Frame(inner_frame, bg=B)
        r_f.pack(fill="x", padx=16, pady=6)
        rc_on_var       = checkbox(r_f, "Show Resets", self.settings.get("reset_count_on", True))
        resets_size_var = size_spin(r_f, self.settings.get("resets_font_size", 12))
        resets_color    = colour_picker(r_f, "Colour:", self.settings.get("resets_font_color", "#ff9f43"))

        # ── BACKGROUND COLOUR ──────────────────────────────────────
        section_hdr("BACKGROUND COLOUR")
        col_f    = tk.Frame(inner_frame, bg=B)
        col_f.pack(fill="x", padx=16, pady=6)
        bg_color = [self.settings.get("bg_color", "#1a1a2e")]
        bg_prev  = tk.Label(col_f, width=3, height=1, bg=bg_color[0],
                             relief="solid", bd=1)
        bg_prev.pack(side="left", padx=(0, 10))
        def pick_bg():
            c = colorchooser.askcolor(color=bg_color[0], parent=win,
                                      title="Background Colour")
            if c[1]: bg_color[0] = c[1]; bg_prev.configure(bg=c[1])
        tk.Button(col_f, text="Pick Colour", command=pick_bg,
                  fg=FG, bg=AC, activeforeground=FG, activebackground=HL,
                  relief="flat", padx=10, pady=4,
                  font=("Segoe UI", 10), cursor="hand2").pack(side="left")

        # ── GAME NAMES + IGDB SEARCH ───────────────────────────────
        section_hdr("GAME NAMES")
        tk.Label(inner_frame,
                 text="  Names are customisable. Use 🔍 to pull a cover image from IGDB.",
                 fg="#666688", bg=B, font=("Segoe UI", 8, "italic"),
                 anchor="w").pack(fill="x", padx=16)
        tk.Label(inner_frame,
                 text="  Greyed-out rows are outside the current game count.",
                 fg="#666688", bg=B, font=("Segoe UI", 8, "italic"),
                 anchor="w").pack(fill="x", padx=16)

        names_f = tk.Frame(inner_frame, bg=B)
        names_f.pack(fill="x", padx=16, pady=6)
        current_names = self.settings.get("game_names", _DEFAULT_GAME_NAMES)
        name_vars: list[tk.StringVar] = []
        name_rows: list[tuple] = []  # (entry_widget, igdb_btn)

        for i in range(15):
            row = tk.Frame(names_f, bg=B)
            row.pack(fill="x", pady=2)
            lbl_fg = FG if i < num_games_var.get() else "#555577"
            tk.Label(row, text=f"Game {i + 1}:", fg=lbl_fg, bg=B,
                     font=("Segoe UI", 10), width=8, anchor="w").pack(side="left")
            nv = tk.StringVar(
                value=current_names[i] if i < len(current_names) else f"Game {i + 1}"
            )
            name_vars.append(nv)
            entry_fg  = FG     if i < num_games_var.get() else "#555577"
            entry_bg  = AC     if i < num_games_var.get() else B
            ent = tk.Entry(row, textvariable=nv, font=("Segoe UI", 10),
                           bg=entry_bg, fg=entry_fg, insertbackground=FG,
                           relief="flat", width=26,
                           state="normal" if i < num_games_var.get() else "disabled")
            ent.pack(side="left", padx=(4, 8))

            igdb_enabled = REQUESTS_OK and i < num_games_var.get()
            igdb_btn = tk.Button(row, text="🔍 IGDB",
                      command=lambda slot=i, v=nv: self.open_search_dialog(slot, v, win),
                      fg="white", bg="#1a3a5c" if igdb_enabled else "#333355",
                      activeforeground="white", activebackground="#1e5080",
                      relief="flat", padx=8, pady=2,
                      font=("Segoe UI", 9), cursor="hand2",
                      state="normal" if igdb_enabled else "disabled")
            igdb_btn.pack(side="left")
            name_rows.append((ent, igdb_btn, row))

        def _update_name_rows(*_):
            n = num_games_var.get()
            for idx, (ent, igdb_btn, row) in enumerate(name_rows):
                active = idx < n
                ent.configure(
                    state="normal" if active else "disabled",
                    bg=AC if active else B,
                    fg=FG if active else "#555577",
                )
                igdb_enabled = REQUESTS_OK and active
                igdb_btn.configure(
                    state="normal" if igdb_enabled else "disabled",
                    bg="#1a3a5c" if igdb_enabled else "#333355",
                )
                # Update the label colour in the same row
                for child in row.winfo_children():
                    if isinstance(child, tk.Label):
                        child.configure(fg=FG if active else "#555577")

        num_games_var.trace_add("write", _update_name_rows)

        # ── GAME TITLE STYLE ───────────────────────────────────────
        section_hdr("GAME TITLE STYLE")
        gt_f = tk.Frame(inner_frame, bg=B)
        gt_f.pack(fill="x", padx=16, pady=6)
        gt_size_var = size_spin(gt_f, self.settings.get("game_title_font_size", 9))
        gt_color    = colour_picker(gt_f, "Colour:",
                                    self.settings.get("game_title_font_color", "#7777bb"))

        # ── IGDB CREDENTIALS ───────────────────────────────────────
        section_hdr("IGDB CREDENTIALS")
        tk.Label(inner_frame,
                 text="  Get these from dev.twitch.tv → Applications → Register Your Application.",
                 fg="#666688", bg=B, font=("Segoe UI", 8, "italic"),
                 anchor="w").pack(fill="x", padx=16)

        cred_f = tk.Frame(inner_frame, bg=B)
        cred_f.pack(fill="x", padx=16, pady=6)

        cid_var = tk.StringVar(value=self.settings.get("igdb_client_id", ""))
        cs_var  = tk.StringVar(value=self.settings.get("igdb_client_secret", ""))

        for label_text, var, show_char in (
            ("Client ID:",     cid_var, ""),
            ("Client Secret:", cs_var,  "●"),
        ):
            row = tk.Frame(cred_f, bg=B)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label_text, fg=FG, bg=B,
                     font=("Segoe UI", 10), width=14, anchor="w").pack(side="left")
            e = tk.Entry(row, textvariable=var, show=show_char,
                         font=("Segoe UI", 10), bg=AC, fg=FG,
                         insertbackground=FG, relief="flat", width=34)
            e.pack(side="left", padx=(4, 8))
            # Toggle visibility for secret
            if show_char:
                vis = [False]
                def _toggle(entry=e, v=vis):
                    v[0] = not v[0]
                    entry.configure(show="" if v[0] else "●")
                tk.Button(row, text="Show", command=_toggle,
                          fg=FG, bg=AC, activeforeground=FG, activebackground=HL,
                          relief="flat", padx=6, pady=1,
                          font=("Segoe UI", 8), cursor="hand2").pack(side="left")

        # ── KEYBINDS ───────────────────────────────────────────────
        section_hdr("KEYBINDS")
        kb_f = tk.Frame(inner_frame, bg=B)
        kb_f.pack(fill="x", padx=16, pady=(6, 2))

        keybind_data: dict[str, tuple[list, tk.StringVar]] = {}
        listening_for: list[str|None] = [None]
        btn_vars: dict[str, tk.StringVar] = {}

        def stop_listening() -> None:
            if listening_for[0] is not None:
                bv = btn_vars.get(listening_for[0])
                if bv: bv.set("Rebind")
                listening_for[0] = None
            try: win.unbind("<KeyPress>")
            except Exception: pass

        for action, label in KEYBIND_LABELS.items():
            current = self.settings["keybinds"].get(action, DEFAULT_KEYBINDS[action])
            stored: list[str] = [ensure_event(current)]
            dv = tk.StringVar(value=display_key(stored[0]))
            keybind_data[action] = (stored, dv)

            row = tk.Frame(kb_f, bg=B)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, fg=FG, bg=B,
                     font=("Segoe UI", 10), width=18, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=dv, width=16, state="readonly",
                     font=("Consolas", 10), readonlybackground=AC,
                     fg=FG, relief="flat").pack(side="left", padx=(4, 6))

            bv = tk.StringVar(value="Rebind")
            btn_vars[action] = bv

            def make_rebind(act=action, s=stored, v=dv):
                def do():
                    stop_listening()
                    listening_for[0] = act
                    btn_vars[act].set("Press a key…")
                    win.focus_set()
                    def on_key(event: tk.Event) -> str:
                        sym = event.keysym
                        if sym in ("Shift_L", "Shift_R", "Control_L", "Control_R",
                                   "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
                            return "break"
                        mods = ""
                        if event.state & 0x0001: mods += "Shift-"
                        if event.state & 0x0004: mods += "Control-"
                        if event.state & 0x0008: mods += "Alt-"
                        full = f"<{mods}{sym}>"
                        s[0] = full; v.set(display_key(full))
                        stop_listening(); return "break"
                    win.bind("<KeyPress>", on_key)
                return do

            tk.Button(row, textvariable=bv, command=make_rebind(),
                      fg=FG, bg=AC, activeforeground=FG, activebackground=HL,
                      relief="flat", padx=8, pady=2,
                      font=("Segoe UI", 9), cursor="hand2").pack(side="left")

        # ── DANGER ZONE ────────────────────────────────────────────
        section_hdr("DANGER ZONE")
        dz_f = tk.Frame(inner_frame, bg=B)
        dz_f.pack(fill="x", padx=16, pady=6)
        def reset_from_settings():
            win.destroy(); self.cmd_reset_all_stats()
        tk.Button(dz_f, text="Reset All Stats", command=reset_from_settings,
                  fg="white", bg="#8b0000",
                  activeforeground="white", activebackground="#b00000",
                  relief="flat", padx=12, pady=6,
                  font=("Segoe UI", 10, "bold"), cursor="hand2").pack(anchor="w")

        tk.Frame(inner_frame, bg=B, height=12).pack()

        # ── Save / Cancel ──────────────────────────────────────────
        btn_row = tk.Frame(win, bg=B)
        btn_row.pack(fill="x", padx=16, pady=(6, 12))

        def save() -> None:
            new_num_games = max(2, min(15, num_games_var.get()))
            games_changed = new_num_games != self.num_games

            self.settings["image_size"]            = size_var.get()
            self.settings["num_games"]             = new_num_games
            self.settings["timer_on"]              = timer_on_var.get()
            self.settings["timer_font_size"]       = timer_size_var.get()
            self.settings["timer_font_color"]      = timer_color[0]
            self.settings["timer_keep_on_reset"]   = timer_keep_var.get()
            self.settings["reset_count_on"]        = rc_on_var.get()
            self.settings["resets_font_size"]      = resets_size_var.get()
            self.settings["resets_font_color"]     = resets_color[0]
            self.settings["bg_color"]              = bg_color[0]
            self.settings["game_names"]            = [v.get() for v in name_vars]
            self.settings["game_title_font_size"]  = gt_size_var.get()
            self.settings["game_title_font_color"] = gt_color[0]
            self.settings["igdb_client_id"]        = cid_var.get().strip()
            self.settings["igdb_client_secret"]    = cs_var.get().strip()
            # game_image_ids are written directly by assign_game / not exposed here
            self.settings["keybinds"] = {a: s[0] for a, (s, _) in keybind_data.items()}
            self._save_settings()

            if games_changed:
                self.num_games = new_num_games
                # Clamp current_game into range
                if self.current_game >= self.num_games:
                    self.current_game = self.num_games - 1
                    self.stats["current_game"] = self.current_game
                self._rebuild_game_frames()

            self._apply_theme()
            self._bind_keys()
            self._refresh_images()
            self._refresh_stats()
            win.destroy()

        tk.Button(btn_row, text="Save", command=save,
                  fg="white", bg="#1e6b3c",
                  activeforeground="white", activebackground="#27ae60",
                  relief="flat", padx=18, pady=6,
                  font=("Segoe UI", 11, "bold"), cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Cancel", command=win.destroy,
                  fg=FG, bg=AC, activeforeground=FG, activebackground=HL,
                  relief="flat", padx=18, pady=6,
                  font=("Segoe UI", 11), cursor="hand2").pack(side="left")

        win.update_idletasks()
        _bind_scroll(inner_frame, canvas_s)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(SCRIPT_DIR, "icon.ico"))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
