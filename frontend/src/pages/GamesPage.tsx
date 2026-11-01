import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";
import MetricsTable from "../components/MetricsTable";
import StageTag, { STAGE_FILTER } from "../components/StageTag";

export default function GamesPage() {
  const { competitionId } = useCompetition();
  const [status, setStatus] = useState("finished");
  // „Alle Metriken“ zeigt nur beendete Spiele, mit jedem Wert vor Anpfiff
  const [view, setView] = useState("overview");
  const metrics = view === "metrics";
  const { data, error, loading } = useLoad(() => api.games(competitionId, metrics ? "finished" : status), [competitionId, status, metrics]);
  const meta = useLoad(() => api.meta(), []);
  const nav = useNavigate();
  const [stage, setStage] = useState("");
  const games = (status === "finished" ? [...(data ?? [])].reverse() : data ?? []).filter(STAGE_FILTER[stage].test);

  return (
    <>
      <div className="topbar">
        <h1>Spiele</h1>
        <select value={view} onChange={(e) => setView(e.target.value)} title="Ansicht">
          <option value="overview">Übersicht</option>
          <option value="metrics">Alle Metriken (beendet)</option>
        </select>
        {!metrics && <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="finished">Beendet</option>
          <option value="open">Offen</option>
          <option value="">Alle</option>
        </select>}
        <select value={stage} onChange={(e) => setStage(e.target.value)} title="Nach Spielphase filtern">
          {Object.entries(STAGE_FILTER).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        {metrics && <button onClick={() => (window.location.href = api.gamesExportUrl(competitionId, stage))}>Als Excel herunterladen</button>}
      </div>
      {error && <div className="error">{error}</div>}
      {metrics ? (
        <div className="panel">
          {loading && <div className="muted">Lade …</div>}
          <div className="small muted" style={{ marginBottom: 8 }}>
            {games.length} beendete Spiele · alle Metriken mit dem Stand vor Anpfiff, wie die Strategien sie sehen · Spaltenname
            zeigen für die Beschreibung, anklicken zum Sortieren, Zeile anklicken für das Spiel
          </div>
          <MetricsTable games={games} labels={meta.data?.features ?? {}} />
        </div>
      ) : (
      <div className="panel table-wrap">
        {loading && <div className="muted">Lade …</div>}
        <table>
          <thead>
            <tr>
              <th>Datum (MSK)</th>
              <th>Phase</th>
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
                  <td className="small" title={g.stage ?? undefined}>
                    {g.stage_type ? (g.stage_type === "league" ? "Hauptrunde" : <StageTag game={g} />) : <span className="muted">–</span>}
                  </td>
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
      )}
    </>
  );
}
