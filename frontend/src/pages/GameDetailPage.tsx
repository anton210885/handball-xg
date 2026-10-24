import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import CourtMap from "../components/CourtMap";
import GoalMap from "../components/GoalMap";
import { ATTACK_LABEL, dateTime, fmt, OUTCOME_LABEL, pct, ZONE_LABEL } from "../labels";
import { useLoad } from "../useLoad";

export default function GameDetailPage() {
  const id = Number(useParams().id);
  const { data: g, error } = useLoad(() => api.game(id), [id]);
  if (error) return <div className="error">{error}</div>;
  if (!g) return <div className="muted">Lade …</div>;
  const f = g.features ?? {};

  return (
    <>
      <div className="topbar">
        <div>
          <Link to="/spiele" className="small">
            ← Spiele
          </Link>
          <h1>
            {g.home.name} – {g.away.name}
          </h1>
          <div className="muted small">
            {dateTime(g.start)} MSK ·{" "}
            <a href={g.url} target="_blank">
              rushandball.ru
            </a>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="score">{g.finished ? `${g.home_score} : ${g.away_score}` : "–"}</div>
          <div className="muted">
            xG {fmt(g.home_xg)} : {fmt(g.away_xg)}
            {g.finished && ` · HZ ${g.home_ht}:${g.away_ht}`}
          </div>
        </div>
      </div>

      <div className="panel">
        <h2>Vor dem Spiel</h2>
        <div className="kpis">
          <div className="kpi"><b>{fmt(f.pred_home)}</b><span>erw. Tore Heim</span></div>
          <div className="kpi"><b>{fmt(f.pred_away)}</b><span>erw. Tore Gast</span></div>
          <div className="kpi"><b>{fmt(f.pred_total)}</b><span>erw. Tore gesamt</span></div>
          <div className="kpi"><b>{fmt(g.line?.over_line)}</b><span>Over-Linie</span></div>
          <div className="kpi"><b>{fmt(f.home_avg_xg)} / {fmt(f.home_avg_xga)}</b><span>Heim Ø xG / xG gegen</span></div>
          <div className="kpi"><b>{fmt(f.away_avg_xg)} / {fmt(f.away_avg_xga)}</b><span>Gast Ø xG / xG gegen</span></div>
        </div>
        <div className="small muted">
          Grundlage: Heim {f.home_games ?? 0} Spiele dieser Saison
          {f.home_prev_games ? ` + ${f.home_prev_games} der Vorsaison (Anteil aktuell ${pct(f.home_weight_current)})` : ""} ·
          Gast {f.away_games ?? 0} Spiele
          {f.away_prev_games ? ` + ${f.away_prev_games} der Vorsaison (Anteil aktuell ${pct(f.away_weight_current)})` : ""}
        </div>
      </div>

      {g.shots.length > 0 ? (
        <>
          <div className="grid2">
            {(["home", "away"] as const).map((side) => (
              <div className="panel" key={side}>
                <h2>Wurfkarte {side === "home" ? g.home.name : g.away.name}</h2>
                <CourtMap zones={g.zones[side]} />
                <div className="small muted" style={{ margin: "6px 0 14px" }}>
                  Tore/Würfe je Zone · grün = mehr Tore als xG, rot = weniger
                </div>
                <GoalMap shots={g.shots.filter((s) => s.is_home === (side === "home"))} />
              </div>
            ))}
          </div>
          <div className="panel table-wrap">
            <h2>Alle Würfe ({g.shots.length})</h2>
            <table>
              <thead>
                <tr>
                  <th className="num">Min.</th>
                  <th>Team</th>
                  <th>Werfer</th>
                  <th>Ergebnis</th>
                  <th>Zone</th>
                  <th>Angriff</th>
                  <th>Torzone</th>
                  <th>Torwart</th>
                  <th className="num">xG</th>
                </tr>
              </thead>
              <tbody>
                {g.shots.map((s) => (
                  <tr key={s.id}>
                    <td className="num">{Math.floor(s.minute) + 1}'</td>
                    <td>{s.is_home ? g.home.name : g.away.name}</td>
                    <td>{s.shooter ?? "–"}</td>
                    <td>
                      <span className={`tag ${s.outcome === "goal" ? "good" : ""}`}>{OUTCOME_LABEL[s.outcome] ?? s.outcome}</span>
                    </td>
                    <td>{s.court_zone ? ZONE_LABEL[s.court_zone] : "–"}</td>
                    <td>
                      {s.attack_type ? ATTACK_LABEL[s.attack_type] : "–"}
                      {s.majority && " · Überzahl"}
                      {s.minority && " · Unterzahl"}
                    </td>
                    <td>{s.goal_zone ?? "–"}</td>
                    <td>{s.goalkeeper ?? "–"}</td>
                    <td className="num">{fmt(s.xg, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="note">Für dieses Spiel gibt es noch keine Würfe (noch nicht gespielt oder nicht importiert).</div>
      )}
    </>
  );
}
