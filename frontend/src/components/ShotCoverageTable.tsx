import { useState } from "react";
import { api, Coverage } from "../api";
import { useLoad } from "../useLoad";

const GENDER: Record<string, string> = { men: "Männer", women: "Frauen" };
const pct = (n: number, total: number) => (total ? `${Math.round((100 * n) / total)} %` : "–");

/** Beendete Spiele je Land, Saison und Geschlecht: mit jedem Wurf, nur Spielerstatistik oder ohne xG. */
export default function ShotCoverageTable() {
  const { data, error } = useLoad(() => api.coverage(), []);
  const [country, setCountry] = useState("");
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="muted small">Lade Statistik …</div>;

  const countries = [...new Set(data.map((r) => r.country ?? "–"))].sort();
  const rows = data
    .filter((r) => r.finished > 0 && (!country || r.country === country))
    .sort((a, b) => (a.country ?? "").localeCompare(b.country ?? "") || b.season.localeCompare(a.season) || a.gender.localeCompare(b.gender));
  const sum = (k: keyof Coverage) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);

  return (
    <div className="panel table-wrap">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Würfe pro Saison</h2>
        <select value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="">alle Länder</option>
          {countries.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>Land</th>
            <th>Liga</th>
            <th>Saison</th>
            <th className="num">beendet</th>
            <th className="num" title="Jeder Wurf mit Ort, Ergebnis und Torhüter">mit Würfen</th>
            <th className="num">Anteil</th>
            <th className="num" title="Nur Wurfzahlen je Spieler und Zone – xG ja, einzelne Würfe nein">nur Spielerstat.</th>
            <th className="num" title="Nur das Ergebnis, kein xG">ohne xG</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.country}</td>
              <td>{r.league} {GENDER[r.gender] ?? r.gender}</td>
              <td>{r.season}</td>
              <td className="num">{r.finished}</td>
              <td className={`num ${r.finished_shots === r.finished ? "pos" : ""}`}>{r.finished_shots}</td>
              <td className="num">{pct(r.finished_shots, r.finished)}</td>
              <td className="num">{r.finished_stats_only || "–"}</td>
              <td className={`num ${r.finished_no_xg ? "neg" : "pos"}`}>{r.finished_no_xg}</td>
            </tr>
          ))}
          <tr>
            <td><b>Summe</b></td>
            <td></td>
            <td></td>
            <td className="num"><b>{sum("finished")}</b></td>
            <td className="num"><b>{sum("finished_shots")}</b></td>
            <td className="num"><b>{pct(sum("finished_shots"), sum("finished"))}</b></td>
            <td className="num"><b>{sum("finished_stats_only")}</b></td>
            <td className="num"><b>{sum("finished_no_xg")}</b></td>
          </tr>
        </tbody>
      </table>
      <div className="small muted" style={{ marginTop: 6 }}>
        <b>Mit Würfen</b>: jeder Wurf einzeln (genaueste xG-Grundlage). <b>Nur Spielerstat.</b>: Wurfzahlen je Spieler
        und Zone, daraus wird das xG geschätzt. <b>Ohne xG</b>: nur Ergebnis.
      </div>
    </div>
  );
}
