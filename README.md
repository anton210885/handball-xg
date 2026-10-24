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
Eine Strategie besteht aus Regeln auf Merkmale, alle mit UND verknüpft. Beispiel: „Erwartete Tore − Over-Linie ≥ 2“. Die Merkmale kommen immer nur aus den Spielen **vor** dem jeweiligen Spiel. Der Backtest rechnet mit den eingetragenen Linien und Quoten, ohne Quote mit 1,80.

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

- **`start.vbs`** (Doppelklick): startet den Server unsichtbar im Hintergrund, **ohne Konsolenfenster**, und öffnet http://localhost:8010. Läuft er schon, wird nur der Browser geöffnet.
- **`stop.vbs`** (Doppelklick): beendet den Server wieder.
- Meldungen des Servers stehen in `backend/data/server.log`.

Der Server liefert die fertig gebaute Oberfläche aus `frontend/dist` mit aus. Nach Änderungen an der Oberfläche einmal neu bauen:

```bash
cd frontend
npm run build
```

Zum Entwickeln mit Live-Neuladen gibt es `start_entwicklung.bat`. Sie öffnet zwei Fenster (Backend und Vite) und startet die Oberfläche auf http://localhost:5173.

### Vorsaison
Jeder Wettbewerb kann auf seine Vorsaison verweisen (Seite „Daten-Import“, Spalte „Vorsaison-ID“). Die Team-Werte werden dann zur Vorsaison hin gezogen: `(Summe aktuelle Spiele + k · Ø Vorsaison) / (Anzahl aktuelle Spiele + k)` mit k = 3 (`PRIOR_WEIGHT_GAMES`). Aufsteiger haben keine Vorsaison, für sie zählt nur die laufende Saison. Die Auswertung dazu: `.venv\Scripts\python scripts\evaluate_prior.py`.

Importiert sind die Männer-Saisons 24/25 (`6597`), 25/26 (`7284`) und 26/27 (`8070`).

### Übernahme aus der alten Access-Datenbank
- `scripts/import_access_lines.py` übernimmt 1X2-Quoten, Over-Linie und Handicap aus `RusHandbal.accdb`. Die Datei wird nur gelesen; von Hand eingetragene Linien bleiben unangetastet. Zugeordnet wird über die Teams und das Datum (bis 4 Tage später, weil Access oft den Eingabetag enthält). Ein vorhandenes Ergebnis muss übereinstimmen.
- `scripts/seed_old_strategies.py` legt die meistgenutzten Strategien aus `handball.ipynb` als „Alt: …“ an. Die alten Kennzahlen (`homeExpGoal_with_GK_power`, `difference_expGoals_with_GK_power`, `last5_Games_…` usw.) gibt es als Merkmale unter denselben Namen in Klammern.

Tests: `cd backend && .venv\Scripts\python -m pytest`
