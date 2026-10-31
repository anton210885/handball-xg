# Änderungen

Die Versionsnummer steht in `backend/app/__init__.py` und `frontend/package.json` (ein Test prüft, dass beide gleich sind). Sie wird im Seitenmenü und unter `/api/version` angezeigt.

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
