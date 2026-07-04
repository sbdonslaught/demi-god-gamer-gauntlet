# Demi-God Gamer Gauntlet
Inspiration was taken from the Content Creator Ludwig. Originally is version was the "God Gamer Gauntlet" and featured 10 games. I made this app to support 5 games hence why it's called the Demi-God-Gamer-Gauntlet. Though now I've adapted to support 2-15 games. 
A speedrun-style challenge tracker for multi-game gauntlets. Track your progress across 2–15 games, count your resets, time your runs, and pull cover art automatically from IGDB.
Disclaimer: Claude wrote all of this. I just provided the ideas. Feel free to edit, fork, or make it better.
![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **2–15 game slots** — configurable from settings, default 5
- **Automatic cover art** via IGDB API (Twitch credentials required)
- **Live timer** with pause/resume — optionally keep running through resets
- **Reset counter** — tracks total resets across the run
- **Greyscale → colour** progression as you complete each game
- **Green border** highlights the current active game
- **Confetti animation** on full gauntlet completion
- **Fully rebindable keybinds**
- **Customizable** — background colour, font sizes, font colours, image sizes, game names
- **Persistent state** — timer, reset count, and current game survive app restarts
- **No-console launcher** — runs cleanly via `.pyw` or the built `.exe`

---

## Requirements

- Python 3.10+
- [Pillow](https://pypi.org/project/Pillow/) `>= 10.0.0`
- [requests](https://pypi.org/project/requests/) `>= 2.28.0`

Install dependencies:

```
pip install -r requirements.txt
```

---

## Running

**Double-click launcher (no console window):**
```
DGGG.pyw
```

**Or via the batch file:**
```
launch.bat
```

**Or directly:**
```
python main.py
```

---

## Building the exe

Requires [PyInstaller](https://pyinstaller.org):

```
build_exe.bat
```

Output: `dist\DGGG.exe`

> When distributing, place the `games\` folder next to the exe.

---

## IGDB Cover Art Setup

1. Go to [dev.twitch.tv](https://dev.twitch.tv) → Applications → Register Your Application
2. Copy your **Client ID** and **Client Secret**
3. Open **Settings** inside the app and paste them under **IGDB Credentials**
4. Use the **🔍 IGDB** button next to each game slot to search and assign cover art

---

## Custom Game Images (manual)

Place images in the `games\` folder named `1.png`, `2.png`, … `15.png` (supports png, jpg, jpeg, webp, bmp, gif).

---

## Default Keybinds

| Action | Key |
|---|---|
| Start / Next | `Space` |
| Reset | `R` |
| Pause / Resume | `P` |
| Previous Game | `←` |
| Next Game | `→` |
| Reset All Stats | `Shift + Enter` |

All keybinds are rebindable in Settings.

---

## Settings

| Setting | Description |
|---|---|
| Image Size | Small / Medium / Large |
| Number of Games | 2–15 (default 5) |
| Timer | Show/hide, font size & colour |
| Keep Timer on Reset | Timer keeps running through resets |
| Reset Count | Show/hide, font size & colour |
| Background Colour | Full colour picker |
| Game Names | Custom label per slot |
| Game Title Style | Font size & colour |
| IGDB Credentials | Client ID + Secret for cover art |
| Keybinds | Fully rebindable |

---

## File Structure

```
DGGG App/
├── main.py            # Main application
├── DGGG.pyw           # No-console double-click launcher
├── launch.bat         # Batch launcher (pythonw)
├── build_exe.bat      # PyInstaller build script
├── requirements.txt
├── games/             # Drop custom images here (1.png–15.png)
├── settings.json      # Auto-created on first run
└── stats.json         # Auto-created on first run
```

---

## License

MIT
