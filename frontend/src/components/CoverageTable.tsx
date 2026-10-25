import { useState } from "react";
import { api, Coverage } from "../api";
import { useLoad } from "../useLoad";

const GENDER: Record<string, string> = { men: "Männer", women: "Frauen" };

/** Wie viele Spiele je Saison ohne Torlinie, 1X2-Quoten oder Handicap sind. */
export default function CoverageTable({ onPick }: { onPick: (competitionId: number, status: string) => void }) {
  const { data, error } = useLoad(() => api.coverage(), []);
  const [country, setCountry] = useState("Russia");
  if (error) return <div className="error">{error}</div>;
  if (!data) return <div className="muted small">Lade Statistik …</div>;

  const countries = [...new Set(data.map((r) => r.country ?? "–"))].sort();
  const rows = data.filter((r) => !country || r.country === country);
  const sum = (k: keyof Coverage) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);
  const cell = (missing: number, total: number) => (
    <td className={`num ${missing ? "neg" : "pos"}`} title={`${total - missing} von ${total} vorhanden`}>
      {total ? missing : "–"}
    </td>
  );

  return (
    <div className="panel table-wrap">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Fehlende Quoten und Torlinien</h2>
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
            <th>Liga</th>
            <th>Saison</th>
            <th className="num">beendet</th>
            <th className="num">ohne Torlinie</th>
            <th className="num">ohne 1X2</th>
            <th className="num">ohne Handicap</th>
            <th className="num">offen</th>
            <th className="num">offen ohne Torlinie</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="click"
              title="Spiele dieser Saison zum Nachtragen öffnen"
              onClick={() => onPick(r.id, r.finished_no_line ? "finished" : "open")}
            >
              <td>
                {country ? "" : `${r.country} · `}
                {r.league} {GENDER[r.gender] ?? r.gender}
              </td>
              <td>{r.season}</td>
              <td className="num">{r.finished}</td>
              {cell(r.finished_no_line, r.finished)}
              {cell(r.finished_no_1x2, r.finished)}
              {cell(r.finished_no_hdp, r.finished)}
              <td className="num">{r.open || "–"}</td>
              {cell(r.open_no_line, r.open)}
            </tr>
          ))}
          <tr>
            <td><b>Summe</b></td>
            <td></td>
            <td className="num"><b>{sum("finished")}</b></td>
            <td className="num"><b>{sum("finished_no_line")}</b></td>
            <td className="num"><b>{sum("finished_no_1x2")}</b></td>
            <td className="num"><b>{sum("finished_no_hdp")}</b></td>
            <td className="num"><b>{sum("open")}</b></td>
            <td className="num"><b>{sum("open_no_line")}</b></td>
          </tr>
        </tbody>
      </table>
      <div className="small muted" style={{ marginTop: 6 }}>
        Grün = vollständig. Die Over/Under-Quote wird nicht gezählt, weil dort meist nur der Standardwert 1,80 steht.
        Klick auf eine Zeile öffnet die Spiele dieser Saison unten zum Nachtragen.
      </div>
    </div>
  );
}
