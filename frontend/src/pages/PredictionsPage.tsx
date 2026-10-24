import { Link } from "react-router-dom";
import { api } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

export default function PredictionsPage() {
  const { competitionId } = useCompetition();
  const { data, error, loading } = useLoad(() => api.predictions(competitionId), [competitionId]);
  const games = (data ?? []).slice(0, 40);

  return (
    <>
      <div className="topbar">
        <h1>Prognosen</h1>
        <span className="muted small">Nächste offene Spiele · Werte aus den bisherigen Spielen beider Teams</span>
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
              <th>Strategien</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const diff = g.features?.pred_total_minus_line;
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
