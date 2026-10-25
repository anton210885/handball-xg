# Änderungen

Die Versionsnummer steht in `backend/app/__init__.py` und `frontend/package.json` (ein Test prüft, dass beide gleich sind). Sie wird im Seitenmenü und unter `/api/version` angezeigt.

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
