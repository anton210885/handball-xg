import { Link } from "react-router-dom";
import { api, Line } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

const SOURCE: Record<string, string> = {
  "oddspapi-pre": "OddsPapi (vor dem Spiel)",
  "oddspapi-close": "OddsPapi (Schlusskurs)",
  access: "Access",
  manual: "von Hand",
  handballapi: "HandballAPI",
};

/** Quelle und Stand der Quoten als Tooltip. */
function lineTitle(line: Line | null) {
  if (!line) return "keine Quoten";
  const when = line.updated_at ? new Date(line.updated_at + "Z").toLocaleString("de-DE") : "";
  return `${SOURCE[line.source ?? ""] ?? line.source ?? ""}${when ? ` · Stand ${when}` : ""}`;
}

export default function PredictionsPage() {
  const { competitionId } = useCompetition();
  const { data, error, loading } = useLoad(() => api.predictions(competitionId), [competitionId]);
  const games = (data ?? []).slice(0, 40);

  return (
    <>
      <div className="topbar">
        <h1>Prognosen</h1>
        <span className="muted small">
          Nächste offene Spiele · Werte aus den bisherigen Spielen beider Teams · Quoten, sobald vorhanden (Maus über
          eine Quote zeigt Quelle und Stand)
        </span>
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <div className="muted">Lade …</div>}
      {!loading && games.length === 0 && <div className="note">Keine offenen Spiele. Erst unter „Daten-Import“ eine Saison laden.</div>}
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Datum (MSK)</th>
              <th>Spiel</th>
              <th className="num">erw. Heim</th>
              <th className="num">erw. Gast</th>
              <th className="num">erw. gesamt</th>
              <th className="num">Over-Linie</th>
              <th className="num">Differenz</th>
              <th className="num">Over</th>
              <th className="num">Under</th>
              <th className="num">1</th>
              <th className="num">X</th>
              <th className="num">2</th>
              <th className="num">Handicap</th>
              <th>Strategien</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const diff = g.features?.pred_total_minus_line;
              const line = g.line;
              // Over/Under-Quote nur zusammen mit einer Linie zeigen (sonst ist es der Platzhalter 1,80)
              const hasLine = line?.over_line !== null && line?.over_line !== undefined;
              const odds = (v: number | null | undefined) => (
                <td className="num" title={lineTitle(line)}>{v ? fmt(v, 2) : "–"}</td>
              );
              return (
                <tr key={g.id}>
                  <td>{dateTime(g.start)}</td>
                  <td>
                    <Link to={`/spiele/${g.id}`}>
                      {g.home.name} – {g.away.name}
                    </Link>
                  </td>
                  <td className="num">{fmt(g.features?.pred_home)}</td>
                  <td className="num">{fmt(g.features?.pred_away)}</td>
                  <td className="num">
                    <b>{fmt(g.features?.pred_total)}</b>
                  </td>
                  <td className="num">{fmt(g.line?.over_line)}</td>
                  <td className={`num ${diff && diff > 0 ? "pos" : diff && diff < 0 ? "neg" : ""}`}>
                    {diff !== undefined && diff !== null ? (diff > 0 ? "+" : "") + fmt(diff) : "–"}
                  </td>
                  {odds(hasLine ? line?.odds_over : null)}
                  {odds(hasLine ? line?.odds_under : null)}
                  {odds(line?.odds_home)}
                  {odds(line?.odds_draw)}
                  {odds(line?.odds_away)}
                  <td className="num" title={lineTitle(line)}>
                    {line?.hdp_line !== null && line?.hdp_line !== undefined ? (line.hdp_line > 0 ? "+" : "") + fmt(line.hdp_line) : "–"}
                  </td>
                  <td>
                    {g.strategies.map((s) => (
                      <span key={s.id} className="tag good">
                        {s.name || s.market}
                      </span>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
