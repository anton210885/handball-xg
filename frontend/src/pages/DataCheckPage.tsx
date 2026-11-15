import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, MetricAudit } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

const COLS: [string, string, number][] = [
  ["games", "Spiele bisher", 0],
  ["avg_goals", "Ø Tore", 2],
  ["avg_goals_against", "Ø Gegentore", 2],
  ["avg_total", "Ø Torsumme", 2],
  ["last5_total_median", "Median Summe L5", 1],
  ["avg_xg", "Ø xG", 2],
  ["avg_xga", "Ø xG gegen", 2],
  ["finishing", "Abschluss", 2],
  ["keeper", "Torhüter", 2],
];

const val = (v: number | string | null | undefined, d = 3) => (v === null || v === undefined ? "–" : typeof v === "number" ? fmt(v, d) : v);

/** Alle Metriken unabhängig nachrechnen. */
function AuditPanel() {
  const [data, setData] = useState<MetricAudit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const run = () => {
    setRunning(true);
    setError(null);
    api.metricAudit().then(setData).catch((e) => setError(e.message)).finally(() => setRunning(false));
  };
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2 style={{ margin: 0 }}>Metriken nachrechnen (alle Spiele)</h2>
        <button onClick={run} disabled={running}>{running ? "Rechne … (ca. 20 Sekunden)" : data ? "Erneut prüfen" : "Prüfung starten"}</button>
      </div>
      <div className="small muted" style={{ margin: "6px 0 10px" }}>
        Rechnet die Vor-Spiel-Werte jedes Spiels auf einem zweiten, unabhängigen Weg nach und vergleicht sie mit den Werten,
        die Strategien und Verifikator benutzen. Gezählt werden nur beendete Spiele desselben Wettbewerbs an früheren Tagen.
      </div>
      {error && <div className="error">{error}</div>}
      {data && (
        <>
          <table>
            <thead>
              <tr><th>Prüfung</th><th className="num">geprüfte Werte</th><th className="num">abweichend</th><th>Ergebnis</th></tr>
            </thead>
            <tbody>
              {data.checks.map((c) => (
                <tr key={c.key} title={c.description}>
                  <td>{c.label}<div className="muted tiny">{c.description}</div></td>
                  <td className="num">{c.checked.toLocaleString("de-CH")}</td>
                  <td className={`num ${c.failed ? "neg" : ""}`}>{c.failed.toLocaleString("de-CH")}</td>
                  <td>{c.failed ? <span className="tag bad">prüfen</span> : <span className="tag good">✓ stimmt</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="small muted" style={{ marginTop: 6 }}>
            {data.games.toLocaleString("de-CH")} Spiele · Vorsaison-Gewicht k = {data.prior_weight}
            {data.prior_weight === 0 ? " (Vorsaison fließt nicht in die Durchschnitte ein)" : ""}
          </div>
          {data.checks.filter((c) => c.examples.length).map((c) => (
            <div key={c.key} className="table-wrap" style={{ marginTop: 12 }}>
              <h3 style={{ margin: "4px 0" }}>{c.label}: Beispiele</h3>
              <table>
                <thead><tr><th>Anpfiff</th><th>Spiel</th><th>Team</th><th>Metrik</th><th className="num">gespeichert</th><th className="num">erwartet</th></tr></thead>
                <tbody>
                  {c.examples.map((e, i) => (
                    <tr key={i}>
                      <td className="small">{dateTime(e.start)}</td>
                      <td><Link to={`/spiele/${e.game_id}`}>{e.game}</Link></td>
                      <td className="small">{e.team || "–"}</td>
                      <td><code>{e.metric}</code></td>
                      <td className="num">{val(e.value)}</td>
                      <td className="num">{val(e.expected)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

/** Ein Team Spiel für Spiel: Werte vor jedem Spiel und was das Spiel selbst brachte. */
function TeamHistoryPanel({ competitionId }: { competitionId: number }) {
  const teams = useLoad(() => api.teams(competitionId), [competitionId]);
  const [teamId, setTeamId] = useState<number | null>(null);
  const sorted = useMemo(() => [...(teams.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [teams.data]);
  useEffect(() => {
    if (sorted.length && !sorted.some((t) => t.id === teamId)) setTeamId(sorted[0].id);
  }, [sorted]); // eslint-disable-line react-hooks/exhaustive-deps
  const hist = useLoad(() => (teamId ? api.metricAuditTeam(competitionId, teamId) : Promise.resolve(null)), [competitionId, teamId]);
  const h = hist.data;
  const bad = h ? h.games.filter((g) => g.mismatch.length).length : 0;
  return (
    <div className="panel table-wrap">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Team-Verlauf Spiel für Spiel</h2>
        <select value={teamId ?? ""} onChange={(e) => setTeamId(Number(e.target.value))}>
          {sorted.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>
      <div className="small muted" style={{ margin: "6px 0 10px" }}>
        Jede Zeile zeigt die Werte <b>vor</b> dem Spiel. Die Zahl „Spiele bisher“ steigt nach jedem beendeten Spiel um 1, die
        Durchschnitte bewegen sich in Richtung des letzten Ergebnisses (sie steigen also nicht immer). Jeder Wert wird
        unabhängig nachgerechnet; weicht er ab, ist er rot und der richtige Wert steht darunter.
      </div>
      {(teams.error || hist.error) && <div className="error">{teams.error || hist.error}</div>}
      {hist.loading && !h && <div className="muted small">Lade …</div>}
      {h && (
        <>
          <div className="small" style={{ marginBottom: 6 }}>
            {h.team} · {h.season} {h.competition}{h.previous_competition ? ` · Vorsaison: ${h.previous_competition}` : ""} ·{" "}
            {bad ? <span className="tag bad">{bad} Spiele mit Abweichung</span> : <span className="tag good">✓ alle {h.games.length} Spiele stimmen</span>}
          </div>
          <table className="audit-table">
            <thead>
              <tr>
                <th>Anpfiff</th><th>Gegner</th><th>Ergebnis</th><th className="num">xG : xG gegen</th>
                {COLS.map(([k, label]) => <th key={k} className="num">{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {h.games.map((g) => (
                <tr key={g.game_id} className={g.mismatch.length ? "audit-bad" : ""}>
                  <td className="small">{dateTime(g.start)}</td>
                  <td><Link to={`/spiele/${g.game_id}`}>{g.home ? "vs " : "@ "}{g.opponent}</Link></td>
                  <td>{g.goals !== null ? `${g.goals}:${g.goals_against}` : g.finished ? "?" : "offen"}</td>
                  <td className="num small">{g.xg !== null ? `${fmt(g.xg, 1)} : ${fmt(g.xga, 1)}` : "–"}</td>
                  {COLS.map(([k, , d]) => {
                    const wrong = g.mismatch.includes(k);
                    return (
                      <td key={k} className={`num ${wrong ? "neg" : ""}`}>
                        {val(g.stored[k], d)}
                        {wrong && <div className="tiny">erwartet {val(g.expected[k], d)}</div>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/** Rohdaten: verdächtige Ergebnisse, Würfe, Linien und Quoten im gewählten Wettbewerb. */
function RawChecksPanel({ competitionId }: { competitionId: number }) {
  const d = useLoad(() => api.dataChecks(competitionId), [competitionId]);
  const [check, setCheck] = useState("");
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const e of d.data?.entries ?? []) c[e.check] = (c[e.check] ?? 0) + 1;
    return c;
  }, [d.data]);
  const entries = (d.data?.entries ?? []).filter((e) => !check || e.check === check);
  return (
    <div className="panel table-wrap">
      <h2 style={{ marginTop: 0 }}>Rohdaten im gewählten Wettbewerb</h2>
      <div className="small muted" style={{ marginBottom: 8 }}>
        Ergebnisse, Würfe, Linien und Quoten, die unplausibel aussehen. „Fehler“ werden in Auswertungen auf Wunsch ausgeschlossen.
      </div>
      {d.error && <div className="error">{d.error}</div>}
      {d.loading && !d.data && <div className="muted small">Lade …</div>}
      {d.data && (
        <>
          <table>
            <thead><tr><th>Prüfung</th><th>Art</th><th className="num">Spiele</th></tr></thead>
            <tbody>
              {d.data.checks.map((c) => (
                <tr key={c.key} onClick={() => setCheck(check === c.key ? "" : c.key)} style={{ cursor: counts[c.key] ? "pointer" : undefined }}
                  className={check === c.key ? "selected" : ""}>
                  <td>{c.label}</td>
                  <td><span className={`tag ${c.severity === "error" ? "bad" : ""}`}>{c.severity === "error" ? "Fehler" : c.severity === "warning" ? "prüfen" : "Hinweis"}</span></td>
                  <td className={`num ${counts[c.key] && c.severity === "error" ? "neg" : ""}`}>{counts[c.key] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {entries.length > 0 && (
            <table style={{ marginTop: 12 }}>
              <thead><tr><th>Anpfiff</th><th>Spiel</th><th>Ergebnis</th><th>Prüfung</th><th>Detail</th></tr></thead>
              <tbody>
                {entries.slice(0, 300).map((e, i) => (
                  <tr key={i}>
                    <td className="small">{dateTime(e.game.start)}</td>
                    <td><Link to={`/spiele/${e.game_id}`}>{e.game.home} – {e.game.away}</Link></td>
                    <td>{e.game.home_score ?? "–"}:{e.game.away_score ?? "–"}</td>
                    <td className="small">{d.data!.checks.find((c) => c.key === e.check)?.label ?? e.check}</td>
                    <td className="small">{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="small muted" style={{ marginTop: 6 }}>Zeile anklicken, um nur diese Prüfung zu zeigen.</div>
        </>
      )}
    </div>
  );
}

export default function DataCheckPage() {
  const { competitionId } = useCompetition();
  return (
    <>
      <div className="topbar"><h1>Datenprüfung</h1></div>
      <AuditPanel />
      {competitionId && <TeamHistoryPanel competitionId={competitionId} />}
      {competitionId && <RawChecksPanel competitionId={competitionId} />}
    </>
  );
}
