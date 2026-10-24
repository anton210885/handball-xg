"""Zentrale Einstellungen. Werte kommen aus backend/.env oder Umgebungsvariablen."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
RAW_CACHE_DIR = DATA_DIR / "raw"
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "handball.db"))
if not DB_PATH.is_absolute():
    DB_PATH = BACKEND_DIR / DB_PATH

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")

# Pause zwischen zwei Abrufen bei rushandball.ru, um die Seite nicht zu belasten
RUSHANDBALL_DELAY_SEC = float(os.getenv("RUSHANDBALL_DELAY_SEC", "0.7"))

# Bekannte Wettbewerbe (rushandball.ru CompId). Weitere lassen sich in der Oberfläche anlegen.
KNOWN_COMPETITIONS = [
    {"id": 6597, "name": "Суперлига Männer – komplett (Vorrunde + Playoffs)", "season": "24/25", "gender": "men"},
    {"id": 7284, "name": "Суперлига Männer – komplett (Vorrunde + Playoffs)", "season": "25/26", "gender": "men",
     "previous_competition_id": 6597},
    {"id": 8070, "name": "Суперлига Männer – Vorrunde", "season": "26/27", "gender": "men",
     "previous_competition_id": 7284},
    {"id": 8078, "name": "Суперлига Frauen – Vorrunde", "season": "26/27", "gender": "women"},
]

# Gewicht der Vorsaison in „Spielen“: Ein Team-Merkmal ist
#   (Summe aktuelle Spiele + k · Ø Vorsaison) / (Anzahl aktuelle Spiele + k)
# k = 0 schaltet die Vorsaison ab. k = 3 war in scripts/evaluate_prior.py auf 25/26 und
# 26/27 nahe am Besten (Spieltag 1–2 deutlich genauer, später praktisch kein Unterschied).
PRIOR_WEIGHT_GAMES = float(os.getenv("PRIOR_WEIGHT_GAMES", "3"))

# Standardquote, wenn für eine Wette keine Quote hinterlegt ist (für Backtests)
DEFAULT_ODDS = 1.85
