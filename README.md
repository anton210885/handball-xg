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

**Automatisch:** Der Server lädt alle 6 Stunden (`AUTO_IMPORT_HOURS`, 0 = aus) die laufenden Saisons nach – Russland (jeder rushandball-Wettbewerb mit Spielen von vor drei Wochen bis in zwei Wochen), die aktuelle koreanische Saison und die rumänischen Ligen. Neu beendete Spiele bekommen ihre Würfe frühestens 3 Stunden nach Anpfiff, danach werden xG und Team-Werte neu berechnet. Stand und nächster Lauf stehen auf „Daten-Import“.

### xG-Modell (`backend/app/xg.py`)
Die Torquote wird pro **Feldzone × Angriffsart** (Positionsangriff / Umschalten) aus allen Würfen geschätzt. Seltene Kombinationen werden zur Zonenquote hin geglättet: `(Tore + k·Zonenquote) / (Würfe + k)`. Ein 7-m-Wurf hat eine eigene Quote.

### Strategien
Eine Strategie besteht aus Regeln auf Merkmale, alle mit UND verknüpft. Beispiel: „Erwartete Tore − Over-Linie ≥ 2“. Die Merkmale verwenden ausschließlich Spiele früherer Kalendertage; dasselbe gilt für die xG-Lerndaten, getrennt nach Liga und Geschlecht. Der Backtest rechnet mit den eingetragenen Linien und Quoten, ohne Quote mit 1,80.

Im Strategie-Baukasten lassen sich ein Quotenbereich (von/bis) und der feste Einsatz je Wette speichern. Der Filter verwendet die Quote des gewählten Marktes. Der Backtest zeigt Profit, Gesamteinsatz, Durchschnittsquote und Rendite; unter „Alle testen“ werden alle gespeicherten Strategien verglichen. Bestehende Strategien können als neue Vorlage kopiert werden. Gewinn: Einsatz × (Quote − 1), Verlust: −Einsatz, Rückzahlung: 0.

### Quoten
Die HandballAPI (RapidAPI) hat für die russische Superliga **keine Quoten**. Der API-Abruf ist für Ligen mit Quoten eingebaut, zum Beispiel die HBL.

**OddsPapi** (`ODDSPAPI_KEY` in `backend/.env`) liefert Quoten für die russische Superliga (Männer 1143, Frauen 1394) und die koreanische H-Liga (Männer 36187, Frauen 38953). Weitere Zuordnungen bestehen für Bundesliga und 2. Bundesliga (Männer/Frauen), EHF Champions League und European League sowie die vorhandenen kroatischen und rumänischen Ligen. Der kostenlose Tarif zeigt bis zu 22 Buchmacher; der bezahlte Normal-Tarif nur die gebuchten – derzeit **22bet** (`ODDSPAPI_BOOKMAKERS=22bet`, sonst HTTP 403 „Restricted bookmaker“). Das historische Archiv beginnt laut Anbieter im Januar 2026; die tatsächliche Abdeckung hängt von Spiel und Buchmacher ab.
- **Torlinie:** die Linie, bei der Over- und Under-Quote (Median über die Buchmacher) beide zwischen **1,70 und 2,00** liegen. Passen mehrere, gewinnt die mit den meisten Buchmachern, dann die ausgeglichenste. Passt keine, bleibt die Linie leer. Ebenso für das Handicap; dazu 1X2.
- **Beendete Spiele:** Schlusskurse (letzter Preis vor Anpfiff) über die historischen Quoten, max. 3 Buchmacher (`ODDSPAPI_BOOKMAKERS`). Es werden ausschließlich datierte Preise vor Anpfiff verwendet. Fehlt ein solcher Preis, bleibt die Quote leer. Archivbeginn: Januar 2026 (`ODDSPAPI_HISTORY_SINCE`), damit auch ein Teil von 25/26.
- **Kommende Spiele:** Vorab-Quoten für die nächsten 2 Tage, höchstens alle `ODDSPAPI_PREMATCH_REFRESH_HOURS` Stunden neu (Standard 12, im Normal-Tarif 3); nach dem Spiel werden sie durch Schlusskurse ersetzt.
- **Automatisch:** Der Server gleicht alle 6 Stunden ab (`ODDSPAPI_SYNC_HOURS`), nur Saisons mit offenen Spielen. Zusätzlich gibt es den Knopf auf „Linien & Quoten“ und `scripts\sync_oddspapi.py`. Mit `scripts\sync_oddspapi.py --history` werden alle passenden Saisons ab Archivbeginn geprüft, auch vollständig beendete Saisons; kommende Spiele bleiben dabei ausgenommen.
- **Sparsam:** Jede Abfrage wird in der Tabelle `api_usage` gezählt; bei `ODDSPAPI_MONTHLY_BUDGET` ist Schluss (Standard 240 für den kostenlosen Tarif; im Normal-Tarif mit 5.000 Abfragen steht in `backend/.env` 4800, dazu `ODDSPAPI_SYNC_HOURS=3` und `ODDSPAPI_PREMATCH_REFRESH_HOURS=3`). Spiellisten vergangener Zeiträume und historische Quoten werden unter `data/raw/oddspapi/` zwischengespeichert, Spiele ohne Daten bei gleicher Buchmacherauswahl nicht erneut abgefragt. Der historische Cache und der Prüfstatus berücksichtigen die Buchmacherauswahl; ein Wechsel prüft alte Einträge neu. Zwischen API-Abrufen liegen mindestens 5,1 Sekunden.
- Von Hand eingetragene Linien, 1X2-Quoten und Handicaps werden nie überschrieben; der Platzhalter 1,80 ohne Linie schon.

Alles Übrige trägst du auf der Seite „Linien & Quoten“ von Hand ein – am schnellsten mit **„Einfügen“**: Auf einer Quotenseite die Tabelle markieren und kopieren (Over/Under, Asian Handicap und/oder 1X2, auch alles zusammen), im Dialog einfügen. Das Tool liest Linien und Dezimalquoten nach Mustern (unabhängig vom Layout), nimmt den Median über die Buchmacher, wählt die Torlinie mit beiden Quoten zwischen 1,70 und 2,00 (ebenso das Handicap) und zeigt eine Vorschau. „Übernehmen“ speichert als Handeintrag (wird vom automatischen Abgleich nicht überschrieben) und öffnet das nächste Spiel ohne Linie. Automatisches Auslesen von oddsportal ist dort laut Nutzungsbedingungen nicht erlaubt; das Einfügen von Hand ist es.

## Prüfung von API-Importen
Der Import prüft die Sportart in den Rohdaten (HandballAPI/Sofascore: Handball-ID 6) und gleicht die tatsächliche Turnier-ID mit der angeforderten Liga ab. Für die 2. Handball-Bundesliga der Männer ist die Turnier-ID **921** korrekt; **150 gehört zum Fußball**. Die drei alten Cache-Einträge mit ID 150 sind deaktiviert. Abgewiesene Rohdaten bleiben in `source_records` erhalten und gelangen nicht als Spiele in die Auswertung. Eine gezielte, vorher gesicherte Bereinigung bestehender Fehlimporte ist über `backend/scripts/repair_foreign_sport.py` möglich.

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

- **`start.vbs`** (Doppelklick): startet den Server unsichtbar im Hintergrund, **ohne Konsolenfenster**, und öffnet http://localhost:8011. Läuft er schon, wird nur der Browser geöffnet.
- **`stop.vbs`** (Doppelklick): beendet den Server wieder.
- Meldungen des Servers stehen in `backend/data/server.log`.

Der Server liefert die fertig gebaute Oberfläche aus `frontend/dist` mit aus. Nach Änderungen an der Oberfläche einmal neu bauen:

```bash
cd frontend
npm run build
```

Zum Entwickeln mit Live-Neuladen gibt es `start_entwicklung.bat`. Sie öffnet zwei Fenster (Backend und Vite) und startet die Oberfläche auf http://localhost:5173.

### Vorsaison
**Standard: aus.** Team-Werte (Ø xG, Ø xG gegen, Abschluss, Torwart …) kommen nur aus Spielen der laufenden Saison; vor dem ersten Spiel eines Teams gibt es deshalb keine Prognose. Das xG-Modell pro Wurf lernt davon unabhängig weiter aus allen früheren Spielen der Liga, auch aus Vorsaisons.

Einschalten lässt sich die Vorsaison mit `PRIOR_WEIGHT_GAMES=3` in `backend/.env`. Jeder Wettbewerb kann auf seine Vorsaison verweisen (Seite „Daten-Import“, Spalte „Vorsaison-ID“); die Team-Werte werden dann zur Vorsaison hin gezogen: `(Summe aktuelle Spiele + k · Ø Vorsaison) / (Anzahl aktuelle Spiele + k)`. Laut Auswertung hilft das nur an Spieltag 1–2. Die Auswertung dazu: `.venv\Scripts\python scripts\evaluate_prior.py`.

Importiert sind die Männer-Saisons 24/25 (`6597`), 25/26 (`7284`) und 26/27 (`8070`).

### Übernahme aus der alten Access-Datenbank
- `scripts/import_access_lines.py` übernimmt 1X2-Quoten, Over-Linie und Handicap aus `RusHandbal.accdb`. Die Datei wird nur gelesen; von Hand eingetragene Linien bleiben unangetastet. Zugeordnet wird über die Teams und das Datum (bis 4 Tage später, weil Access oft den Eingabetag enthält). Ein vorhandenes Ergebnis muss übereinstimmen.
- `scripts/import_notebook_strategies.py` übernimmt **alle 308 selbst gebauten Strategien** aus `handball.ipynb` (`futuregamesstrategy_…`) als „NB: …“. Jede Bedingung wird wörtlich als Formel übernommen, z. B. `(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) -3 > over`. Die Grenzwerte `overOddsW`, `underOddsW`, `overTB25` und `underTB25` werden so eingesetzt, wie sie im Notebook direkt davor gesetzt waren. Die alten Spaltennamen berechnet `app/legacy.py` aus den neuen Werten. Formeln erlauben nur Namen, Zahlen, Rechenzeichen und Vergleiche, keinen beliebigen Code.

Tests: `cd backend && .venv\Scripts\python -m pytest`

### Metriken & Profit
Die Analyse bietet Home, Draw, Away, Over und Under, Quotenfilter Min/Max sowie feste Bookmaker-Torlinienbereiche: 40,5–44,5; 45,5–49,5; 50,5–54,5; 55,5–59,5; 60,5–65,5; 66,5–99. Grenzen zählen einschließlich. Leere Quotenfelder begrenzen nicht. Gerechnet wird mit der gespeicherten Quote des Marktes (Over/Under ohne Quote: Standard 1,80). Der Torlinienbereich filtert in allen Märkten die gespeicherte Bookmaker-Torlinie. Keine zusätzliche +1-Regel. Einsatz und Saisons sind wählbar.

Pearson-Korrelationen zeigen den Zusammenhang zwischen jeder verfügbaren numerischen Metrik und Nettoertrag je Wette. Sortiert wird numerisch nach dem Korrelationswert absteigend (positiv bis negativ); konstante Metriken bleiben ohne Korrelation. Ältere ca. 70 % der Spieldaten bestimmen bis zu fünf Wertebereiche je Metrik; neuere Daten prüfen dieselben Grenzen. Gleiche Tage werden nicht getrennt, fehlende Werte ausgewiesen. Grafiken und Tabellen zeigen Profit, ROI und Anzahl Wetten je Bereich und Zeitraum. Korrelation belegt keine Ursache; die xG-Merkmale werden für jedes historische Spiel mit früheren Lerndaten berechnet.

Zusätzlich sind Home-Quote Min/Max und Away-Quote Min/Max unabhängig vom gewählten Wettmarkt optional einstellbar. Jede Grenze kann einzeln gesetzt werden. Weitere Metrikbedingungen (Merkmal, Vergleich, Wert) und Formeln lassen sich wie im Strategie-Baukasten ergänzen und entfernen. Alle gesetzten Filter werden mit UND vor Profitberechnung, zeitlicher Aufteilung und Korrelationsanalyse angewendet. Fehlende Quoten/Metriken schließen ein Spiel nur dann aus, wenn die jeweilige zusätzliche Bedingung sie benötigt.

### Rumänien (Liga Zimbrilor, Liga Florilor, frhlive2.com)
`scripts\import_romania.py` lädt die laufende Saison von frhlive2.com, der Live-Statistik des rumänischen Verbands (Daten von sportinfocentar2.com): Spielplan, Ergebnis, Halbzeit und aus jedem beendeten Spiel den **Spielverlauf mit jedem Wurf** – Zone (Außen und Rückraum mit Seite, Kreis, 7 m, Gegenstoß, Durchbruch, leeres Tor), Ergebnis, Torzone, Werfer, Torwart und Vorlage.

- Wettbewerbe und Teams wie im Access-Bestand („Romania · Liga nationala“, frhlive-Namen → Access-Namen in `TEAM_NAMES`), damit Vorsaison und Teamwerte durchgehen. Unbekannte Teams stehen im Bericht.
- Würfe nur, wenn die Tore im Spielverlauf genau zum Ergebnis passen und die Wurfzahl höchstens um 2 von der Spielertabelle abweicht.
- Ältere Saisons bietet die Quelle nicht an. Abrufe mit 1,5 s Pause, Spieldateien unter `data/raw/frhlive/` zwischengespeichert.

### Korea (H-Liga, koreahandball.com)
`scripts\import_korea.py` (optional mit Saison, z. B. `2026` = 26/27) lädt ab 24/25 Männer und Frauen von koreahandball.com: Spielplan (Hauptrunde und Playoffs) und aus jedem Spielbericht den **Spielverlauf mit jedem Wurf** – Zone (6 m, Außen, 9 m, 7 m, Gegenstoß, Durchbruch, leeres Tor), Ergebnis (Tor, gehalten, vorbei, Pfosten, Block), Werfer, Torwart und Vorlage. Der Werfer wird über den Kader dem Team zugeordnet (geblockte Würfe stehen im Verlauf teils beim Gegner).
- **Prüfung:** Würfe werden übernommen, wenn sie die offiziellen Zonensummen exakt treffen oder – weil auch die offizielle Zonenaufteilung nicht immer vollständig ist – die Tore je Team genau und die Würfe höchstens 2 abweichen (markiert). 24/25 und 25/26: 283 exakt, 42 mit kleiner Abweichung, 7 ohne Würfe (im Verlauf fehlt ein Tor).
- **Zusammenführung** mit den Access-Daten („Korea · H League“): gleiche Wettbewerbe und Teams (koreanische Namen → englische Namen, `TEAM_NAMES`), doppelt angelegte Teams zusammengelegt. Ein vorhandenes Spiel (gleiche Teams, ±2 Tage) bekommt offizielles Ergebnis, Anstoßzeit und Würfe; seine Linien bleiben. Ein Spiel wird nie zwei koreanischen Spielen zugeordnet (wichtig bei Playoff-Serien).
- **Kommende Spiele** (noch ohne Spielbericht) werden über Datum und Teams angelegt und später ergänzt; Playoff-Platzhalter („정규 1위“) erst, wenn die Teams feststehen.
- Abrufe mit 1 s Pause, Seiten unter `data/raw/koreahandball/` zwischengespeichert. `robots.txt` erlaubt den Zugriff.

### Frauen-Superliga
Angelegt sind 24/25 (6604, gesamte Saison), 25/26 (7286, gesamte Saison) und 26/27 (8078, Vorrunde), jeweils mit Vorsaison-Verknüpfung. `scripts/import_women_access_lines.py` liest die alte Access-Datei ausschließlich lesend und ergänzt verfügbare Frauen-Quoten und Torlinien. Die Zuordnung erfordert beide Teams, ein Datum im bestehenden Importfenster und Übereinstimmung mit dem Endergebnis. Einträge ohne Ergebnis werden ausgelassen. Mehrdeutige Treffer werden ausgelassen; vorhandene Werte werden nicht überschrieben.

Die Korrelationsseite wählt statt einzelner Saisons die Gruppe (Männer, Frauen, Alle) und die Liga (Standard: Alle). Alle importierten Saisons der Auswahl fließen ein. Nicht berechenbare Korrelationen stehen am Tabellenende.

### Vor-Spiel-Metriken und Beschreibungen
In „Strategien“ und „Metriken & Profit“ erklärt die aufklappbare Metrikhilfe Bedeutung, Formel, Datenquelle und Zeitpunkt aller Merkmale und alten Formelnamen. Bei der ausgewählten Korrelationsmetrik erscheint zusätzlich ihre vollständige Beschreibung.

Die Analyse übernimmt keine gespeicherten globalen `Shot.xg`. Stattdessen wird die Wurfbewertung chronologisch rekonstruiert: pro Liga und Geschlecht nur Würfe beendeter, importierter Spiele früherer Kalendertage, Glättung 30; ohne Lerndaten neutrale Wurfchance 0,5. Das Modell wird für einen Spieltag eingefroren und erst danach um dessen Würfe erweitert. Auch Teamhistorie und Vorsaison werden auf frühere Tage begrenzt; eine Vorsaison anderer Liga/Geschlechtsgruppe wird ignoriert. Am ersten Spiel ohne Historie fehlen Teamprognosen. Ergebnis, Halbzeitstand und tatsächliche Würfe des Zielspiels sind keine erlaubten Filter-/Formelnamen; Ergebnisse dienen nur der Wettabrechnung.

Die xG-Modellübersicht und Spielstatistik bleiben deskriptive Ansichten aus dem aktuellen Datenbestand; ihre xG können von den historischen Vor-Spiel-Metriken abweichen. Quoten und Torlinien werden als manuell/importierte Pre-Match-Werte behandelt; historische Erfassungszeitpunkte/Revisionen sind nicht versioniert und können nicht nachträglich bewiesen werden. Künftige Daten dürfen frühere Strategie-Metriken nicht verändern; Regressionstests prüfen dies auch für Ergebnisänderungen, gleichzeitige Spiele, globale xG-Neuberechnung und Vorsaison-Verknüpfungen.

### Einheitlicher Bestandsimport weiterer Ligen
`scripts/import_unified_history.py` importiert die vorhandenen Access-Sportdaten und bereits gespeicherte HandballAPI-Antworten. Das Skript ruft keine API auf und erstellt vor Änderungen eine SQLite-Sicherung. Externe Spiele, Teams und Wettbewerbe erhalten deterministische, getrennte IDs innerhalb der JavaScript-Zahlengenauigkeit. Die Quelldateien werden nur lesend geöffnet; alte berechnete Wett-Ergebnisse werden neu berechnet und nicht als Rohdaten übernommen.

`aggregate_stats` speichert Team-Summen und kategorisierte Roh-/Spielerwerte, `source_records` sichert übernommene Sportfelder und ungeklärte Datensätze. Einzelwürfe werden nicht erfunden. Fehlende xG bleiben leer. Spiele mit reinen Ergebnisdaten liefern weiterhin zeitlich korrekte Tor-Durchschnitte und die Metrik „Erwartete Tore aus bisherigen Toren − Bookmaker-Linie“. Bei aggregierten Wurfzahlen ohne verlässliche Kategorie-Tore verwendet xG ein getrenntes gröberes Modell: Gesamtwürfe × geglättete Torquote ausschließlich früherer Tage derselben Liga/Geschlechtsgruppe. Abgeleitete Positions-Wurfsummen sind gekennzeichnet; Angriffsarten werden nicht zusätzlich doppelt gezählt.

Fehlende Außenwürfe können bei Außenpositionen als Rest geschätzt werden: Gesamtwürfe minus 7-m-, 9-m-, Gegenstoß-, Kreis- und Durchbruchwürfe. Die Quelle kann 6-m-Zähler mit Untertypen überlappend führen; deshalb bleiben die ursprünglichen Zähler separat. Schätzungen werden als solche angezeigt. Ein negativer Rest oder weniger Versuche als Außentore ergibt keinen Wert statt einer stillen Korrektur auf 0. Alte gespeicherte Außenwerte werden als Altbestand mit nicht verifizierter Berechnung markiert.

Der API-Teamspiel-Endpunkt liefert nur einen begrenzten Saisonausschnitt je Team. Die importierten deutschen und EHF-Saisons sind daher keine garantierten vollständigen Saisonarchive. Weitere Einzelstatistiken und Datumsauflösungen benötigen wieder verfügbares API-Kontingent. Noch undatierte Access-Analyse-/Quotenzeilen sowie Datum-/Geschlechtskonflikte bleiben im Quelldatenspeicher und fließen nicht als erfundene historische Spiele ein. Die Quellimport-Knöpfe für rushandball werden für fremde Bestandsimporte gesperrt; erneuter lokaler Import erfolgt mit obigem Skript.
