"""Zentrale Einstellungen. Werte kommen aus backend/.env oder Umgebungsvariablen."""
import os
from datetime import datetime
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

# OddsPapi (kostenlos: 250 Abfragen/Monat). Etwas Puffer lassen.
ODDSPAPI_KEY = os.getenv("ODDSPAPI_KEY", "")
ODDSPAPI_MONTHLY_BUDGET = int(os.getenv("ODDSPAPI_MONTHLY_BUDGET", "240"))
# Buchmacher für historische Quoten (max. 3). Kostenloser Tarif: alle, z. B. superbet,vave,marathonbet.
# Bezahlte Tarife geben nur die gebuchten frei (sonst HTTP 403 „Restricted bookmaker“), z. B. 22bet.
ODDSPAPI_BOOKMAKERS = os.getenv("ODDSPAPI_BOOKMAKERS", "superbet,vave,marathonbet").split("#")[0].strip()
# Automatischer Abgleich: alle x Stunden; Vorab-Quoten für Spiele der nächsten x Tage
ODDSPAPI_SYNC_HOURS = float(os.getenv("ODDSPAPI_SYNC_HOURS", "6"))
# Laufende Saisons (Russland, Korea) automatisch nachladen: alle x Stunden, 0 = aus
AUTO_IMPORT_HOURS = float(os.getenv("AUTO_IMPORT_HOURS", "6"))
ODDSPAPI_PREMATCH_DAYS = float(os.getenv("ODDSPAPI_PREMATCH_DAYS", "2"))
# Vorab-Quoten eines Spiels frühestens nach x Stunden erneut holen
ODDSPAPI_PREMATCH_REFRESH_HOURS = float(os.getenv("ODDSPAPI_PREMATCH_REFRESH_HOURS", "12"))
# Laut OddsPapi-Dokumentation beginnt das historische Archiv im Januar 2026.
ODDSPAPI_HISTORY_SINCE = datetime.fromisoformat(os.getenv("ODDSPAPI_HISTORY_SINCE", "2026-01-01"))
# (Land, Liga, Geschlecht) -> OddsPapi-Turnier
ODDSPAPI_TOURNAMENTS = {
    ("Russia", "Superliga", "men"): 1143,
    ("Russia", "Superliga", "women"): 1394,
    ("Korea", "H League", "men"): 36187,
    ("Korea", "H League", "women"): 38953,
    ("Germany", "Bundesliga", "men"): 149,
    ("Germany", "Bundesliga", "women"): 245,
    ("Germany", "2. Bundesliga", "men"): 921,
    ("Germany", "2. Bundesliga", "women"): 33055,
    ("Croatia", "Premijer liga", "men"): 576,
    ("Croatia", "HRL", "women"): 577,
    ("Romania", "Liga nationala", "men"): 1396,
    ("Romania", "Liga nationala", "women"): 1398,
    ("International", "EHF Champions League", "men"): 30,
    ("International", "EHF Champions League", "women"): 288,
    ("International", "EHF European League", "men"): 59,
    ("International", "EHF European League", "women"): 60,
}
# Hauptlinie: Over- und Under-Quote liegen beide in diesem Bereich
MAIN_LINE_MIN_ODDS, MAIN_LINE_MAX_ODDS = 1.70, 2.00

# Pause zwischen zwei Abrufen bei rushandball.ru, um die Seite nicht zu belasten
RUSHANDBALL_DELAY_SEC = float(os.getenv("RUSHANDBALL_DELAY_SEC", "0.7"))

# Bekannte Wettbewerbe (rushandball.ru CompId). Weitere lassen sich in der Oberfläche anlegen.
KNOWN_COMPETITIONS = [
    {"id": 6597, "name": "Суперлига Männer – komplett (Vorrunde + Playoffs)", "season": "24/25", "gender": "men"},
    {"id": 7284, "name": "Суперлига Männer – komplett (Vorrunde + Playoffs)", "season": "25/26", "gender": "men",
     "previous_competition_id": 6597},
    {"id": 8070, "name": "Суперлига Männer – Vorrunde", "season": "26/27", "gender": "men",
     "previous_competition_id": 7284},
    {"id": 6604, "name": "Суперлига Frauen – komplett (Vorrunde + Playoffs)", "season": "24/25", "gender": "women"},
    {"id": 7286, "name": "Суперлига Frauen – komplett (Vorrunde + Playoffs)", "season": "25/26", "gender": "women",
     "previous_competition_id": 6604},
    {"id": 8078, "name": "Суперлига Frauen – Vorrunde", "season": "26/27", "gender": "women",
     "previous_competition_id": 7286},
]

# Gewicht der Vorsaison in „Spielen“: Ein Team-Merkmal ist
#   (Summe aktuelle Spiele + k · Ø Vorsaison) / (Anzahl aktuelle Spiele + k)
# k = 0 (Standard) schaltet die Vorsaison ab: Team-Werte kommen nur aus der laufenden Saison.
# k = 3 war in scripts/evaluate_prior.py nahe am Besten, hilft aber nur an Spieltag 1–2.
# Das xG-Modell pro Wurf lernt unabhängig davon weiter aus allen früheren Spielen der Liga.
PRIOR_WEIGHT_GAMES = float(os.getenv("PRIOR_WEIGHT_GAMES", "0"))

# Standardquote, wenn für eine Wette keine Quote hinterlegt ist (für Backtests)
DEFAULT_ODDS = 1.80  # wie in der alten Auswertung (Gewinn +0,8 je Treffer)
