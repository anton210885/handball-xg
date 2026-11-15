import { useEffect, useMemo, useState } from "react";
import { api, GoalPredictor, GoalTable } from "../api";
import { useCompetition } from "../App";
import { useGameFilter } from "../components/GameFilter";
import { fmt } from "../labels";
import { useLoad } from "../useLoad";
import Scatter from "../components/Scatter";
import MetricCompare from "../components/MetricCompare";
import MetricRanking from "../components/MetricRanking";

const TARGETS: Record<string, string> = { total: "Tore gesamt", home: "Heimtore", away: "Gasttore", margin: "Tordifferenz Heim − Gast" };
// Vorschläge je Ziel: [Anzeige, Formel]
const PRESETS: Record<string, [string, string][]> = {
  total: [
    ["homeExpGoal_with_GK_power + awayExpGoal_with_GK_power", "homeExpGoal_with_GK_power + awayExpGoal_with_GK_power"],
    ["… mit GK_power, alte xG-Berechnung (_alt)", "homeExpGoal_with_GK_power_alt + awayExpGoal_with_GK_power_alt"],
    ["homeExpGoal_with_GK + awayExpGoal_with_GK", "homeExpGoal_with_GK + awayExpGoal_with_GK"],
    ["home_expGoal + away_expGoal", "home_expGoal + away_expGoal"],
    ["home_expGoal + away_expGoal, alte xG-Berechnung (_alt)", "home_expGoal_alt + away_expGoal_alt"],
    ["last5_Games_Sum_expGoal_with_GK", "last5_Games_Sum_expGoal_with_GK"],
    ["Tore-Form gesamt (pred_total_goals)", "pred_total_goals"],
    ["Faire Torlinie (fair_total)", "fair_total"],
  ],
  home: [["homeExpGoal_with_GK_power", "homeExpGoal_with_GK_power"], ["homeExpGoal_with_GK_power_alt (alte xG-Berechnung)", "homeExpGoal_with_GK_power_alt"], ["homeExpGoal_with_GK", "homeExpGoal_with_GK"],
    ["home_expGoal", "home_expGoal"], ["Tore-Form Heim (home_goals_form)", "home_goals_form"]],
  away: [["awayExpGoal_with_GK_power", "awayExpGoal_with_GK_power"], ["awayExpGoal_with_GK_power_alt (alte xG-Berechnung)", "awayExpGoal_with_GK_power_alt"], ["awayExpGoal_with_GK", "awayExpGoal_with_GK"],
    ["away_expGoal", "away_expGoal"], ["Tore-Form Gast (away_goals_form)", "away_goals_form"]],
  margin: [["homeExpGoal_with_GK_power − awayExpGoal_with_GK_power", "homeExpGoal_with_GK_power - awayExpGoal_with_GK_power"],
    ["… mit GK_power, alte xG-Berechnung (_alt)", "homeExpGoal_with_GK_power_alt - awayExpGoal_with_GK_power_alt"],
    ["home_expGoal − away_expGoal", "home_expGoal - away_expGoal"], ["Faire Differenz (fair_margin)", "fair_margin"]],
};
const STORE = "goalCorrelationFormula";
const PAGE = 200;
const r2 = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

function Card({ title, s }: { title: string; s: GoalPredictor | undefined }) {
  return <div className="panel" style={{ flex: 1, minWidth: 260, margin: 0 }}>
    <div className="small muted">{title}</div>
    <div style={{ fontSize: 32, fontWeight: 700 }}>r = {r2(s?.r)}</div>
    <div className="small">R² = {r2(s?.r2)} · {s?.games ?? 0} Spiele · Ø Abweichung {fmt(s?.mae, 2)} Tore · Bias {fmt(s?.bias, 2)}</div>
  </div>;
}

export default function GoalCorrelationPage() {
  const { competitions } = useCompetition();
  const { ids, included, excludeErrors, ui: filterUi } = useGameFilter(competitions);
  const [target, setTarget] = useState("total");
  const saved = useMemo(() => { try { return localStorage.getItem(STORE); } catch { return null; } }, []);
  const [draft, setDraft] = useState(saved ?? PRESETS.total[0][1]);
  const [formula, setFormula] = useState(saved ?? PRESETS.total[0][1]);
  const [data, setData] = useState<GoalTable | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [minGames, setMinGames] = useState(0);
  const [minDraft, setMinDraft] = useState("0");
  const applyMin = () => { const n = Math.max(0, Math.min(100, Math.round(Number(minDraft) || 0))); setMinDraft(String(n)); setMinGames(n); };
  const names = useLoad(() => api.goalCorrelationNames(), []);


  useEffect(() => {
    if (!ids.length || !formula.trim()) { setData(null); return; }
    let live = true;
    setBusy(true); setError(""); setShown(PAGE);
    api.goalTable(ids, excludeErrors, target, formula, minGames)
      .then(d => live && setData(d))
      .catch(e => { if (live) { setError(e.message); setData(null); } })
      .finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [ids.join(","), excludeErrors, target, formula, minGames]);

  const apply = (f = draft) => {
    setDraft(f); setFormula(f.trim());
    try { localStorage.setItem(STORE, f.trim()); } catch { /* egal */ }
  };
  const points = (data?.games ?? []).filter(g => g.metric !== null).map(g => [g.metric as number, g.actual] as [number, number]);
  const bm = target === "total" ? "Over-Linie" : target === "margin" ? "Handicap-Linie" : "Buchmacher";
  // Spalten des Metrik-Vergleichs: Vorschläge des Ziels plus die eigene Formel
  const compareFormulas = useMemo(() => {
    const list = PRESETS[target].map(([label, f]) => ({ name: label, formula: f }));
    return list.some(m => m.formula === formula) || !formula ? list : [{ name: `Eigene: ${formula}`, formula }, ...list];
  }, [target, formula]);

  return <>
    <h1>Korrelation: Metrik gegen erzielte Tore</h1>
    <div className="panel">
      {filterUi}
      <div className="row" style={{ marginTop: 12 }}>
        <label>Erzielte Tore <select value={target} onChange={e => { setTarget(e.target.value); apply(PRESETS[e.target.value][0][1]); }}>
          {Object.entries(TARGETS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Metrik <select value={PRESETS[target].some(p => p[1] === formula) ? formula : ""} onChange={e => e.target.value && apply(e.target.value)}>
          <option value="">eigene Formel …</option>
          {PRESETS[target].map(([label, f]) => <option key={f} value={f}>{label}</option>)}</select></label>
        <label title="Beide Teams müssen vor dem Spiel mindestens so viele Spiele in dieser Saison gehabt haben. Früh in der Saison sind die Werte noch unsicher.">
          Ab Spielen beider Teams <input type="number" min={0} max={100} className="cell" style={{ width: 70 }} value={minDraft}
            onChange={e => setMinDraft(e.target.value)} onBlur={applyMin} onKeyDown={e => { if (e.key === "Enter") applyMin(); }} /></label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <datalist id="gc-names">{Object.entries(names.data ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</datalist>
        <input aria-label="Formel" list="gc-names" value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === "Enter") apply(); }}
          style={{ flex: 1, minWidth: 320, fontFamily: "monospace" }} placeholder="z. B. homeExpGoal_with_GK_power + awayExpGoal_with_GK_power" />
        <button onClick={() => apply()} disabled={draft.trim() === formula}>Anzeigen</button>
      </div>
      <div className="small muted" style={{ marginTop: 6 }}>
        Formel aus Werten vor dem Spiel mit + − × ÷ und Klammern; Namen werden beim Tippen vorgeschlagen.{" "}
        <details style={{ display: "inline" }}><summary style={{ display: "inline", cursor: "pointer", textDecoration: "underline" }}>Alle Namen ({Object.keys(names.data ?? {}).length})</summary>
          <div style={{ maxHeight: 220, overflowY: "auto" }}>{Object.entries(names.data ?? {}).map(([k, v]) => <div key={k}><code>{k}</code>{v !== k ? ` – ${v}` : ""}</div>)}</div>
        </details>
      </div>
      <div className="small muted" style={{ marginTop: 6 }}>
        {included.length} Saisons · {busy ? "rechne …" : data ? `${data.games.length} beendete Spiele${data.excluded_errors ? `, ${data.excluded_errors} wegen Datenfehlern weggelassen` : ""}` : ""}
      </div>
      {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
    </div>

    {data && <>
      <div className="row" style={{ alignItems: "stretch", gap: 12, marginBottom: 16 }}>
        <Card title={`Deine Metrik ↔ ${data.target_label}`} s={data.stats_metric} />
        <Card title={`${data.bookmaker_label} ↔ ${data.target_label}`} s={data.stats_bookmaker} />
      </div>
      <MetricCompare ids={ids} excludeErrors={excludeErrors} target={target} minGames={minGames} formulas={compareFormulas} />
      <MetricRanking ids={ids} excludeErrors={excludeErrors} target={target} minGames={minGames} onPick={f => apply(f)} />
      <div className="panel">
        <h2>Vergleich nach gespielten Spielen</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Beide Teams ab</th><th>Spiele</th><th>Metrik r</th><th>{bm} r</th><th>gleiche Spiele</th><th>Metrik r</th><th>{bm} r</th>
            <th>Ø Abw. Metrik</th><th>Ø Abw. {bm}</th><th title="Korrelation von (Metrik − Linie) mit (Tore − Linie)">r(Metrik − {bm}, Tore − {bm})</th></tr></thead>
          <tbody>{data.by_min_games.map(c => {
            const better = (c.metric_same_games.r ?? -2) > (c.bookmaker_same_games.r ?? -2);
            return <tr key={c.min_games} style={{ background: c.min_games === data.min_games ? "var(--accent-soft)" : undefined, cursor: "pointer" }}
              onClick={() => { setMinDraft(String(c.min_games)); setMinGames(c.min_games); }} title="Klicken: diese Grenze für Karten, Diagramm und Spiele übernehmen">
              <td>{c.min_games === 0 ? "alle" : `${c.min_games} Spielen`}</td><td>{c.stats_metric.games}</td>
              <td>{r2(c.stats_metric.r)}</td><td>{r2(c.stats_bookmaker.r)}</td>
              <td>{c.metric_same_games.games}</td>
              <td className={c.metric_same_games.games ? (better ? "good" : "") : ""}>{r2(c.metric_same_games.r)}</td><td>{r2(c.bookmaker_same_games.r)}</td>
              <td>{fmt(c.metric_same_games.mae, 2)}</td><td>{fmt(c.bookmaker_same_games.mae, 2)}</td>
              <td><b>{r2(c.metric_same_games.r_vs_bookmaker)}</b></td>
            </tr>;
          })}</tbody>
        </table></div>
        <div className="small muted" style={{ marginTop: 6 }}>Grün: Metrik auf denselben Spielen besser als die {bm}. Ab etwa 20 Spielen bleiben meist nur Spiele aus der zweiten Saisonhälfte übrig – auf die Anzahl achten.</div>
      </div>
      <div className="panel">
        <div className="small">
          <b>Auf denselben Spielen</b> (beide Werte vorhanden, {data.metric_same_games.games} Spiele): Metrik r = {r2(data.metric_same_games.r)}, {bm} r = {r2(data.bookmaker_same_games.r)} ·
          Ø Abweichung Metrik {fmt(data.metric_same_games.mae, 2)}, {bm} {fmt(data.bookmaker_same_games.mae, 2)} Tore ·
          r(Metrik − {bm}, Tore − {bm}) = <b>{r2(data.metric_same_games.r_vs_bookmaker)}</b>
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>
          <b>r</b>: steigt die Metrik, steigen auch die Tore? 1 = perfekt, 0 = kein Zusammenhang, negativ = gegenläufig.
          <b> R²</b> = r · r: Anteil der Schwankung der Tore, den die Metrik erklärt (0,20 = 20 %).
          Die letzte Zahl zeigt, ob die Abweichung deiner Metrik von der {bm} in die richtige Richtung zeigt – über 0 heißt, die Metrik weiß etwas, das die {bm} nicht weiß.
        </div>
        <div style={{ marginTop: 12 }}>
          <Scatter points={points} p={data.stats_metric} xLabel={data.formula} yLabel={`Erzielt: ${data.target_label}`} />
        </div>
      </div>
      <div className="panel">
        <h2>Spiele ({data.games.length})</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Datum</th><th>Wettbewerb</th><th>Spiel</th><th>Ergebnis</th><th title="Weniger Spiele der beiden Teams vor diesem Spiel">Spiele vorher</th><th>Erzielte Tore</th><th>Metrik</th><th>{bm}</th><th>Metrik − {bm}</th><th>Tore − {bm}</th></tr></thead>
          <tbody>{data.games.slice(0, shown).map(g => <tr key={g.id}>
            <td>{new Date(g.start).toLocaleDateString("de-DE")}</td><td className="small">{g.competition}</td>
            <td><a href={`/spiele/${g.id}`}>{g.home} – {g.away}</a></td><td>{g.score}</td><td>{g.played}</td>
            <td><b>{g.actual}</b></td><td>{fmt(g.metric, 1)}</td><td>{fmt(g.bookmaker, 1)}</td>
            <td>{g.metric !== null && g.bookmaker !== null ? fmt(g.metric - g.bookmaker, 1) : "–"}</td>
            <td>{g.bookmaker !== null ? fmt(g.actual - g.bookmaker, 1) : "–"}</td>
          </tr>)}</tbody>
        </table></div>
        {shown < data.games.length && <button style={{ marginTop: 8 }} onClick={() => setShown(shown + PAGE * 5)}>weitere anzeigen ({data.games.length - shown})</button>}
      </div>
    </>}
  </>;
}
