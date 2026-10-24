# Handball xG

Spielstatistiken sammeln, xG berechnen, Strategien bauen und testen. Erster Wettbewerb ist die russische Superliga, Quelle rushandball.ru.

## Aufbau

| Teil | Technik | Aufgabe |
|---|---|---|
| `backend/` | Python, FastAPI, SQLite | Daten laden, Würfe auslesen, xG, Merkmale, Strategien, REST-API |
| `frontend/` | React, Vite, TypeScript | Oberfläche |

### Datenquelle rushandball.ru
Die Webseite holt ihre Daten aus einer JSON-Schnittstelle:

- `ias.rushandball.ru/Api/Online/GetCompGames/{compId}` liefert den Spielplan (Männer 26/27: `8070`, Frauen: `8078`).
- `ias.rushandball.ru/Api/Online/{gameId}` liefert den Spielverlauf. Daraus wird **jeder einzelne Wurf** mit Feldzone, Torzone, Angriffsart, Werfer, Torwart und Vorlage rekonstruiert.
- `ias.rushandball.ru/Api/Online/GetGame/{gameId}` liefert die offizielle Statistik. Gegen sie wird der Parser geprüft: Bei allen 54 Spielen (108 Team-Spielen) stimmen Würfe, Tore und jede Zone überein.

Die Rohdaten werden unter `backend/data/raw/` zwischengespeichert. Ein erneuter Import lädt sie also nicht noch einmal.

### xG-Modell (`backend/app/xg.py`)
Die Torquote wird pro **Feldzone × Angriffsart** (Positionsangriff / Umschalten) aus allen Würfen geschätzt. Seltene Kombinationen werden zur Zonenquote hin geglättet: `(Tore + k·Zonenquote) / (Würfe + k)`. Ein 7-m-Wurf hat eine eigene Quote.

### Strategien
Eine Strategie besteht aus Regeln auf Merkmale, alle mit UND verknüpft. Beispiel: „Erwartete Tore − Over-Linie ≥ 2“. Die Merkmale kommen immer nur aus den Spielen **vor** dem jeweiligen Spiel. Der Backtest rechnet mit den eingetragenen Linien und Quoten, ohne Quote mit 1,85.

### Quoten
Die HandballAPI (RapidAPI) hat für die russische Superliga **keine Quoten**. Linien und Quoten trägst du auf der Seite „Linien & Quoten“ von Hand ein. Der API-Abruf ist für Ligen mit Quoten eingebaut, zum Beispiel die HBL.

## Einrichten (einmalig)

```bash
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # RAPIDAPI_KEY eintragen
cd ..\frontend
npm install
```

## Starten

Doppelklick auf `start.bat`. Das startet das Backend auf Port 8010 und die Oberfläche auf Port 5173 und öffnet dann http://localhost:5173.

### Vorsaison
Jeder Wettbewerb kann auf seine Vorsaison verweisen (Seite „Daten-Import“, Spalte „Vorsaison-ID“). Die Team-Werte werden dann zur Vorsaison hin gezogen: `(Summe aktuelle Spiele + k · Ø Vorsaison) / (Anzahl aktuelle Spiele + k)` mit k = 3 (`PRIOR_WEIGHT_GAMES`). Aufsteiger haben keine Vorsaison, für sie zählt nur die laufende Saison. Die Auswertung dazu: `.venv\Scripts\python scripts\evaluate_prior.py`.

Importiert sind die Männer-Saisons 24/25 (`6597`), 25/26 (`7284`) und 26/27 (`8070`).

Tests: `cd backend && .venv\Scripts\python -m pytest`
