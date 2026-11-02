# Änderungen

Die Versionsnummer steht in `backend/app/__init__.py` und `frontend/package.json` (ein Test prüft, dass beide gleich sind). Sie wird im Seitenmenü und unter `/api/version` angezeigt.

## 0.11.0 – 2026-11-03
- **Kroatien** (Paket24 Premijer liga, 1. HRL Žene) aus der Statistik des Verbands HRS: 24/25, 25/26 und die laufende Saison 26/27 mit jedem Wurf (1.042 Spiele, 951 mit Würfen). Die Wettbewerbsnummern stammen aus dem HRS-Archiv (https://hrs.hr/povijesna-natjecanja/). Damit ist auch die Rückrunde 25/26 da, die in Access fehlte. 12 doppelte Access-Spiele mit den HRS-Spielen zusammengeführt (Linien bleiben), 12 kampflos gewertete 10:0-Spiele werden übersprungen. Im automatischen Import enthalten; von Hand `scripts\import_croatia.py`.
- Rumänien und Kroatien nutzen denselben Import (`import_schedule`); vorhandene Spiele werden auch mit vertauschtem Heim/Gast erkannt.
- Parser für sportinfocentar-Dateien verträgt einzelne Backslashes; eine unlesbare Spieldatei bricht den Import nicht mehr ab.

## 0.10.2 – 2026-11-02
- **Rumänien: Spielerstatistik für ältere Spiele** aus der HandballAPI (Würfe und Tore je Spieler und Zone, Paraden): die neuesten 33 Spiele der Rückrunde 25/26 sind geladen (24 mit Daten, alle mit passender Torzahl; für 9 hat der Anbieter keine). Der Rest kommt im automatischen Import nach und nach, solange mehr als 5 Abfragen im Monat übrig sind (`backfill_lineups`); der letzte bekannte Stand des Kontingents wird gemerkt.

## 0.10.1 – 2026-11-02
- **Rumänien 25/26 vervollständigt**: Access endete im Dezember 2025; die Ergebnisse von Januar bis Mai 2026 kommen jetzt aus der HandballAPI (Männer 62, Frauen 78 Spiele, mit Halbzeit, ohne Würfe), dazu Halbzeitstände für 111 Access-Spiele. Zwei doppelte Access-Spiele zusammengeführt. `scripts\import_romania_history.py` liest die gespeicherten Antworten unter `data/handballapi/ro_events_*`.

## 0.10.0 – 2026-11-02
- **Rumänien** (Liga Zimbrilor, Liga Florilor) von frhlive2.com, der Live-Statistik des Verbands: laufende Saison 26/27 mit Spielplan, Ergebnis, Halbzeit und jedem Wurf aus dem Spielverlauf (Zone mit Seite, Ergebnis, Torzone, Werfer, Torwart, Vorlage). Teams wie im Access-Bestand, Vorsaison verknüpft. Im automatischen Import enthalten; von Hand `scripts\import_romania.py`. Erster Lauf: 314 Spiele, alle 90 beendeten mit Würfen.
- Spielseite nennt die tatsächliche Quelle (koreahandball.com, frhlive2.com) statt „Access-Bestandsimport“.

## 0.9.0 – 2026-11-01
- **„Spiele“ → „Alle Metriken (beendet)“**: jedes beendete Spiel mit Ergebnis, xG und allen 61 Metriken (Stand vor Anpfiff, wie die Strategien sie sehen); jede Spalte sortierbar, Beschreibung beim Zeigen auf den Spaltennamen.
- **Excel-Export** (`/api/games/export.xlsx`): dieselben Spiele mit Halbzeit, Linie, Handicap, Ausgang Over und Handicap und allen Metriken samt den alten Access-Namen; zweites Blatt mit den Beschreibungen. Neue Abhängigkeit `openpyxl`.

## 0.8.3 – 2026-11-01
- **Spielstatistik** auf jeder Spielseite mit Würfen (Russland und Korea): je Team eine Spielertabelle mit Tore/Würfe, Quote, Zonen (6 m, Außen, 9 m, 7 m, Gegenstoß, Durchbruch, leeres Tor) und xG sowie eine Torhütertabelle mit Paraden je Zone, aufgebaut wie die Statistik von koreahandball.

## 0.8.2 – 2026-11-01
- Korea 24/25: vier falsch eingeordnete Access-Spiele bereinigt. Drei waren doppelt (Geschlecht vertauscht, „Buzau W“ statt Busan W) und wurden mit dem echten Spiel von koreahandball zusammengeführt, dessen Linie und Quoten jetzt übernommen sind. Ein Spiel ohne Gegenstück (Incheon City – Chungnam, 16.03.25) wurde gelöscht, ebenso fünf verwaiste Teams. Die Rohdaten bleiben erhalten.
- `game_admin.merge_duplicate`: doppeltes Spiel in das richtige überführen. Der Access-Import legt gelöschte oder zusammengeführte Spiele nicht wieder an.

## 0.8.1 – 2026-10-31
- **Automatischer Import** der laufenden Saisons (Russland, Korea) alle 6 Stunden (`AUTO_IMPORT_HOURS`): neue Ergebnisse, Würfe (frühestens 3 Stunden nach Anpfiff) und geänderte Anstoßzeiten, danach xG neu. Stand auf „Daten-Import“.

## 0.8.0 – 2026-10-31
- **Spielphase** je Spiel: Hauptrunde, KO-Spiel (Viertel-/Halbfinale, Finale, Spiele um Plätze) oder Platzierungsrunde – aus dem rushandball-Spielplan (Russland), koreahandball (Korea) und der Access-Spalte `tour` (40 = Playoff). Filter und Etikett auf „Spiele“, „Linien & Quoten“ und „Prognosen“; Metriken `is_knockout` / `is_league` für Strategien, der alte Name `tour` ist bei KO-Spielen wie in Access 40. Nachtragen: `scripts/backfill_stages.py`.
- Fehlimport der 2. Bundesliga Männer korrigiert: Turnier-ID 921 statt 150, 230 belegte Fußballspiele und 25 verwaiste Teams nach Sicherung bereinigt. Rohdaten bleiben als abgewiesene Datensätze erhalten; Import prüft Sportart und Turnier-ID.
- Historische OddsPapi-Quoten ab Januar 2026: vollständiger Abgleich aller passenden Saisons mit `scripts\sync_oddspapi.py --history`, einschließlich Bundesliga, 2. Bundesliga und EHF.
- Schlusskurs ist der letzte aktive Preis strikt vor Anpfiff; Preise ab Anpfiff und undatierte Werte werden nicht verwendet.
- Cache und Prüfstatus berücksichtigen die Buchmacherauswahl. Alte OddsPapi-Stände werden bei einem Wechsel neu geprüft. Manuelle 1X2- und Handicap-Einträge sind auch ohne Torlinie geschützt.
- Mindestens 5,1 Sekunden Abrufabstand, Budgetprüfung auch vor Wiederholungen und keine API-Schlüssel in HTTP-Info-Logs.
- Vorübergehende Anbieterfehler werden wiederholt; dauerhaft fehlerhafte Spiele bleiben erneut abrufbar. Eindeutige Fremdsport-Quelldaten werden vor der Quotenzuordnung ausgeschlossen.

- „Linien & Quoten“: Filter für fehlende Quoten (ohne Torlinie, ohne 1X2, ohne Handicap, ganz ohne Quoten) und „Alle Spiele“; Klick in der Statistik setzt „ohne Torlinie“.
- **Lesezeichen-Knopf für oddsportal** („Linien & Quoten“): auf einer Spielseite im eigenen Browser anklicken, das Tool erkennt das Spiel (Anstoß, Ergebnis, gemerkte Teamnamen) und speichert die Quoten des offenen Reiters (1X2, Over/Under, Asian Handicap; nur „Full Time“). Unsichere Zuordnungen wählt man aus der Liste (`POST /api/oddsportal/import`).
- Lesezeichen-Knopf mit einem Klick: klickt 1X2, Over/Under und Asian Handicap selbst durch, das Tool-Fenster schließt sich nach dem Speichern, die Rückmeldung erscheint als Kästchen auf oddsportal.
- **Tampermonkey-Skript für oddsportal** (`/handball-xg.user.js`, wird beim Bauen erzeugt): läuft beim Öffnen einer Handball-Spielseite von selbst, klickt die drei Reiter durch und speichert direkt im Tool, ohne Fenster. Nur bei unsicherer Zuordnung öffnet ein Klick auf das Kästchen die Auswahl. Rückmeldung (auch beim Lesezeichen) mit Zähler, wie vielen beendeten Spielen des Wettbewerbs noch Torlinie, Handicap oder 1X2 fehlen.
- Tampermonkey-Skript markiert auf oddsportal-Ergebnislisten, welche Spiele im Tool noch Quoten brauchen (rot „fehlt: Linie, HC, 1X2“, grün ✓, grau „?“), und führt per Klick von einem fehlenden Spiel zum nächsten (`POST /api/oddsportal/list`). Zuordnung über die gemerkte Spiel-ID oder Teamnamen in der Adresse plus Ergebnis. Ein Handicap gilt als erledigt, wenn oddsportal keins im Bereich 1,70–2,00 hatte.
- Behoben: Heim/Gast kamen aus dem Seitentitel, der auf h2h-Seiten die Teams vertauscht – dadurch wurden falsche Teamnamen gemerkt und Quoten teils beim falschen Spiel gespeichert. Jetzt aus dem Spielkopf; ein abweichendes Ergebnis oder widersprüchliche Namen verhindern das automatische Speichern; die oddsportal-Spiel-ID wird je Spiel gemerkt. Anker der Spielseiten (`#over-under;2`, `#ah;2`) werden erkannt.
- Einfügen von Quotentabellen: Anzahl Buchmacher aus der Übersichtszeile zählt bei der Wahl der Hauptlinie mit.
- „Linien & Quoten“: Spiele löschen – einzeln (✕) oder per Auswahl, mit Rückfrage. Würfe, Linie und Summen werden mitgelöscht, Quelldaten bleiben als Rohdaten erhalten (`POST /api/games/delete`).

## 0.7.0 – 2026-10-25
- **Quotentabelle einfügen** auf „Linien & Quoten“: Tabelle einer Quotenseite (Over/Under, Asian Handicap, 1X2) kopieren und einfügen; das Tool erkennt alle Linien, nimmt die Torlinie mit beiden Quoten zwischen 1,70 und 2,00, zeigt eine Vorschau und springt nach dem Speichern zum nächsten Spiel ohne Linie.

## 0.6.1 – 2026-10-25
- Quoten von OddsPapi jetzt auch für die koreanische H-Liga (Männer 36187, Frauen 38953), automatisch ab Saison 26/27.
- Buchmacher für historische Quoten einstellbar (`ODDSPAPI_BOOKMAKERS`); der Normal-Tarif gibt nur die gebuchten frei (22bet).

## 0.6.0 – 2026-10-25
- **Koreanische H-Liga** von koreahandball.com: Spielplan und jeder einzelne Wurf aus dem Spielverlauf (Zone, Ergebnis, Werfer, Torwart, Vorlage), Männer und Frauen ab Saison 24/25. Mit den vorhandenen Access-Daten zusammengeführt: offizielle Ergebnisse und Anstoßzeiten, Linien aus Access bleiben erhalten.
- xG für Korea pro Wurf statt „Würfe × Ligaschnitt“.
- Versionsnummer und dieses Änderungsprotokoll.

## 0.5.1 – 2026-10-25
- OddsPapi: Auffrischtakt der Vorab-Quoten einstellbar (`ODDSPAPI_PREMATCH_REFRESH_HOURS`), Normal-Tarif mit 5.000 Abfragen/Monat.

## 0.5.0 – 2026-10-25
- Prognosen zeigen Over/Under, 1X2 und Handicap, sobald Quoten vorhanden sind; Quelle und Stand im Tooltip.

## 0.4.1 – 2026-10-25
- Vorsaison bei den Team-Werten standardmäßig aus; das xG-Modell pro Wurf lernt weiter aus allen früheren Spielen.

## 0.4.0 – 2026-10-25
- Quoten von OddsPapi für die russische Superliga (Torlinie nach der Regel 1,70–2,00, Schlusskurse, automatischer Abgleich).
- Statistik fehlender Quoten und Torlinien auf „Linien & Quoten“.

## 0.3.0 – 2026-10-25
- Alle 308 eigenen Strategien aus `handball.ipynb` als Formeln, „Alle testen“.
- Seite „Metriken & Profit“, zeitlich korrektes xG, Frauen-Superliga, weitere Ligen aus Access und HandballAPI.

## 0.2.0 – 2026-10-24
- Start ohne Konsolenfenster (`start.vbs` / `stop.vbs`).
- Quoten und Linien aus der Access-Datenbank `RusHandbal.accdb`.

## 0.1.0 – 2026-10-24
- Erster Stand: Import der russischen Superliga von rushandball.ru mit jedem Wurf, xG-Modell, Strategien mit Backtest, React-Oberfläche.
