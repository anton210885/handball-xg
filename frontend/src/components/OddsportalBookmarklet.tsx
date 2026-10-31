import { useEffect, useRef } from "react";
import { bookmarkletCode } from "../oddsportalScripts";

export default function OddsportalBookmarklet() {
  const link = useRef<HTMLAnchorElement>(null);
  // React lässt javascript:-Adressen im JSX nicht zu – daher von Hand setzen
  useEffect(() => link.current?.setAttribute("href", bookmarkletCode(window.location.origin)), []);
  return (
    <details className="panel">
      <summary style={{ cursor: "pointer", fontWeight: 600 }}>Quoten von oddsportal übernehmen</summary>
      <div className="small" style={{ marginTop: 10, lineHeight: 1.6 }}>
        <h3 style={{ margin: "0 0 6px" }}>Am schnellsten: automatisch beim Öffnen (Tampermonkey)</h3>
        <ol style={{ margin: 0, paddingLeft: 18 }}>
          <li>
            Einmalig die Browser-Erweiterung <b>Tampermonkey</b> aus dem Chrome Web Store installieren. In Chrome unter
            Erweiterungen → Tampermonkey → Details „Nutzerskripts zulassen“ einschalten.
          </li>
          <li>
            <a href="/handball-xg.user.js" target="_blank" rel="noreferrer">Handball-xG-Skript installieren</a> – Tampermonkey
            zeigt das Skript, dort auf „Installieren“ klicken. Fragt Tampermonkey beim ersten Speichern, ob das Skript
            mit dem Tool sprechen darf: „Immer erlauben“.
          </li>
          <li>
            Ab jetzt nur noch Handball-Spiele auf oddsportal öffnen. Das Skript klickt 1X2, Over/Under und Asian Handicap
            selbst durch und speichert. Oben rechts steht das Ergebnis und wie viele Quoten im Wettbewerb noch fehlen.
          </li>
          <li>
            Auf der Ergebnisliste einer Liga (z. B. „Results“) markiert das Skript jedes Spiel: rot „fehlt: …“, grün ✓,
            grau „?“ (noch nicht zugeordnet). Klick auf das Kästchen oben rechts öffnet das erste fehlende Spiel, nach dem
            Speichern führt ein Klick zum nächsten.
          </li>
        </ol>
        <p className="muted" style={{ margin: "6px 0 12px" }}>
          Das Tool muss dafür laufen (start.vbs). Updates holt sich Tampermonkey selbst von hier.
        </p>

        <h3 style={{ margin: "0 0 6px" }}>Ohne Erweiterung: Lesezeichen-Knopf</h3>
        <p style={{ margin: "0 0 8px" }}>
          Diesen Knopf mit der Maus in die Lesezeichenleiste ziehen (ein alter Knopf muss ersetzt werden):{" "}
          <a ref={link} className="tag" onClick={(e) => e.preventDefault()} title="In die Lesezeichenleiste ziehen">
            → Handball xG ⚡
          </a>
          . Auf der Spielseite anklicken, ein kleines Tool-Fenster speichert alles und schließt sich wieder.
        </p>
        <p className="muted" style={{ margin: "8px 0 0" }}>
          Torlinie und Handicap nach der Regel 1,70–2,00 (bei Gleichstand die mit mehr Buchmachern), 1X2 als Median.
          Gelesen wird nur die Seite, die du im eigenen Browser offen hast. Ist das Spiel nicht sicher erkannt (oranges
          Kästchen), wählst du es im Tool-Fenster aus; die Teamnamen merkt sich das Tool danach.
        </p>
      </div>
    </details>
  );
}
