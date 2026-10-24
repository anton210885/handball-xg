import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

export default function GamesPage() {
  const { competitionId } = useCompetition();
  const [status, setStatus] = useState("finished");
  const { data, error, loading } = useLoad(() => api.games(competitionId, status), [competitionId, status]);
  const nav = useNavigate();
  const games = status === "finished" ? [...(data ?? [])].reverse() : data ?? [];

  return (
    <>
      <div className="topbar">
        <h1>Spiele</h1>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="finished">Beendet</option>
          <option value="open">Offen</option>
          <option value="">Alle</option>
        </select>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="panel table-wrap">
        {loading && <div className="muted">Lade …</div>}
        <table>
          <thead>
            <tr>
              <th>Datum (MSK)</th>
              <th>Heim</th>
              <th>Gast</th>
              <th className="num">Ergebnis</th>
              <th className="num">xG Heim</th>
              <th className="num">xG Gast</th>
              <th className="num">Tore ges.</th>
              <th className="num">Prognose</th>
              <th className="num">Over-Linie</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const total = g.home_score !== null && g.away_score !== null ? g.home_score + g.away_score : null;
              return (
                <tr key={g.id} className="click" onClick={() => nav(`/spiele/${g.id}`)}>
                  <td>{dateTime(g.start)}</td>
                  <td>{g.home.name}</td>
                  <td>{g.away.name}</td>
                  <td className="num">{g.finished ? `${g.home_score}:${g.away_score}` : "–"}</td>
                  <td className="num">{fmt(g.home_xg)}</td>
                  <td className="num">{fmt(g.away_xg)}</td>
                  <td className="num">{total ?? "–"}</td>
                  <td className="num">{fmt(g.features?.pred_total)}</td>
                  <td className="num">{fmt(g.line?.over_line)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
