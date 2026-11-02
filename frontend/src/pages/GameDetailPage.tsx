import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import BoxScore from "../components/BoxScore";
import CourtMap from "../components/CourtMap";
import GoalMap from "../components/GoalMap";
import { ATTACK_LABEL, dateTime, fmt, OUTCOME_LABEL, pct, ZONE_LABEL } from "../labels";
import { useLoad } from "../useLoad";

const SOURCE_LABEL: Record<string, string> = { handballapi: "HandballAPI", koreahandball: "koreahandball.com", frhlive: "frhlive2.com" };

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
            {g.url ? <a href={g.url} target="_blank">rushandball.ru</a> : <span>{SOURCE_LABEL[g.source ?? ""] ?? "Access-Bestandsimport"}</span>}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="score">{g.finished ? `${g.home_score} : ${g.away_score}` : "–"}</div>
          <div className="muted">
            xG {fmt(g.home_xg)} : {fmt(g.away_xg)}
            {g.finished && g.home_ht !== null && g.away_ht !== null && ` · HZ ${g.home_ht}:${g.away_ht}`}
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

      {/* Summen aus Access nur zeigen, solange es keine einzelnen Würfe gibt – sonst widersprüchliche Zahlen */}
      {(g.aggregate_stats?.length ?? 0) > 0 && g.shots.length === 0 && <div className="panel">
        <h2>Zusammengefasste Statistiken</h2>
        <div className="small muted">Diese Quelle liefert Summen statt einzelner Wurfereignisse. Abgeleitete Außenwürfe bleiben gekennzeichnet. Kategorien nach Wurfposition und Angriffsart können sich überschneiden und werden nicht pauschal addiert.</div>
        <table><thead><tr><th>Team</th><th>Tore</th><th>Würfe</th><th>Datenqualität</th></tr></thead><tbody>{g.aggregate_stats?.map(st => <tr key={String(st.is_home)}><td>{st.is_home ? g.home.name : g.away.name}</td><td>{st.goals ?? "–"}</td><td>{st.shots ?? "–"}</td><td>{st.flags.includes("wing_shots_estimated_residual") ? "Außenwürfe teilweise als Rest berechnet. " : ""}{st.flags.includes("shot_total_derived_from_spatial_counts") ? "Wurfzahl aus Positionssummen abgeleitet. " : ""}{st.flags.includes("player_goals_disagree_with_result") ? "Spieler-Torsumme abweichend; xG nicht berechnet. " : ""}{st.flags.includes("wing_residual_conflict") ? "Widersprüchlicher Außenwurf-Rest bleibt leer." : ""}</td></tr>)}</tbody></table>
        {g.aggregate_stats?.some(st => Array.isArray(st.categories.players)) && <details style={{ marginTop: 12 }}><summary>Spielerwerte und berechnete Außenwürfe</summary><div className="table-wrap"><table><thead><tr><th>Team</th><th>Spieler</th><th>Position</th><th>Tore</th><th>Würfe</th><th>Außenwürfe</th><th>Herkunft</th></tr></thead><tbody>{g.aggregate_stats?.flatMap(st => (st.categories.players ?? []).map((p: any, i: number) => <tr key={`${st.is_home}-${i}`}><td>{st.is_home ? g.home.name : g.away.name}</td><td>{p.player?.name ?? "–"}</td><td>{p.position ?? "–"}</td><td>{p.statistics?.goals ?? "–"}</td><td>{p.statistics?.shotsTaken ?? "–"}</td><td>{p.statistics?.wingShots_normalized ?? "–"}</td><td>{p.flags?.includes("wing_shots_estimated_residual") ? "Als Rest geschätzt" : p.statistics?.wingShots_normalized != null ? (st.source.startsWith("access") ? "Altbestand; Berechnung nicht verifiziert" : "Quelle") : "Nicht ableitbar"}</td></tr>))}</tbody></table></div></details>}
      </div>}
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
          <BoxScore shots={g.shots} team={g.home.name} isHome />
          <BoxScore shots={g.shots} team={g.away.name} isHome={false} />
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
        <div className="note">{g.data_level === "aggregate" ? "Für dieses Spiel liegen zusammengefasste Statistiken vor, keine einzelnen Wurfereignisse." : g.data_level === "results" && g.finished ? "Ergebnisdaten vorhanden. Wurfstatistiken fehlen; xG-Metriken bleiben leer, Tor-Durchschnitte sind nutzbar." : "Für dieses Spiel gibt es noch keine Würfe (noch nicht gespielt oder nicht importiert)."}</div>
      )}
    </>
  );
}
