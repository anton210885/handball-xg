import { useEffect, useMemo, useState } from "react";
import { api, Analysis, MetricBin, Strategy } from "../api";
import { useCompetition } from "../App";
import { useLoad } from "../useLoad";
import { analysisCompetitions, correlationDescending, leagueName } from "../analysisFilters";
import MetricGuide, { MetricInfo } from "../components/MetricGuide";
import { fmt, pct } from "../labels";

const base: Strategy = { name: "Metrik-Analyse", market: "over", rules: [], min_games: 0, stake: 1 };
const LINE_RANGES = [[40.5,44.5], [45.5,49.5], [50.5,54.5], [55.5,59.5], [60.5,65.5], [66.5,99]];
const MARKETS = { home: "Home", draw: "Draw", away: "Away", over: "Over", under: "Under" };
const condition = (b: MetricBin) => `${b.lower === null ? "−∞" : fmt(b.lower, 4)} ≤ Wert < ${b.upper === null ? "+∞" : fmt(b.upper, 4)}`;

export default function AnalysisPage() {
  const { competitions } = useCompetition();
  const meta = useLoad(() => api.meta(), []);
  const [quoteFilters, setQuoteFilters] = useState<Record<string, number | "">>({});
  const setRule = (i: number, patch: Partial<Strategy["rules"][number]>) => setS({ ...s, rules: s.rules.map((r,j) => i === j ? { ...r, ...patch } : r) });
  const [range, setRange] = useState(3);
  const [lineMin, lineMax] = LINE_RANGES[range];
  const [s, setS] = useState<Strategy>(base);
  const [gender, setGender] = useState("all");
  const [league, setLeague] = useState("all");
  const leagues = useMemo(() => [...new Set(competitions.filter(c => (c.with_stats ?? c.with_shots) > 0 && (gender === "all" || c.gender === gender)).map(leagueName))].sort(), [competitions, gender]);
  const included = useMemo(() => analysisCompetitions(competitions, gender, league), [competitions, gender, league]);
  const ids = useMemo(() => included.map(c => c.id), [included]);
  const [result, setResult] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [minBets, setMinBets] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setResult(null); }, [s, ids, lineMin, lineMax, quoteFilters]);
  const run = async () => {
    if (s.min_odds != null && s.max_odds != null && s.min_odds > s.max_odds) { setError("Quote Min darf nicht größer als Quote Max sein."); return; }
    const rules: Strategy["rules"] = [...s.rules];
    for (const side of ["home", "away"]) {
      const lo = quoteFilters[`${side}_min`], hi = quoteFilters[`${side}_max`];
      if (typeof lo === "number" && typeof hi === "number" && lo > hi) { setError(`${side === "home" ? "Home" : "Away"}: Min darf nicht größer als Max sein.`); return; }
      for (const [bound, op] of [["min", ">="], ["max", "<="]]) {
        const value = quoteFilters[`${side}_${bound}`];
        if (typeof value === "number") {
          if (!Number.isFinite(value) || value <= 1) { setError("Quoten müssen größer als 1 sein."); return; }
          rules.push({ feature: `odds_${side}`, op, value });
        }
      }
    }
    rules.push({ feature: "over_line", op: ">=", value: lineMin });
    rules.push({ feature: "over_line", op: "<=", value: lineMax });
    setBusy(true); setError(""); setResult(null);
    try { const x = await api.analyze({ ...s, rules, min_games: 0 }, ids); x.metrics = correlationDescending(x.metrics); setResult(x); setSelected(x.metrics.find(m => m.correlation !== null)?.key ?? x.metrics[0]?.key ?? ""); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const metric = result?.metrics.find(m => m.key === selected);
  const metrics = result?.metrics.filter(m => m.label.toLowerCase().includes(search.toLowerCase()) || m.key.includes(search)) ?? [];
  const scale = Math.max(.01, ...((metric?.bins ?? []).flatMap(b => [Math.abs(b.train.roi ?? 0), Math.abs(b.test.roi ?? 0)])));
  return <>
    <h1>Metriken & Profit</h1>
    <div className="panel">
      <div className="row">
        <label>Markt <select value={s.market} onChange={e => setS({ ...s, market: e.target.value })}>{Object.entries(MARKETS).map(([k,v]) => <option key={k} value={k} title={meta.data?.feature_details?.[k]?.description}>{v}</option>)}</select></label>
        <label>Marktquote Min <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.min_odds ?? ""} onChange={e => setS({ ...s, min_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
        <label>Marktquote Max <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.max_odds ?? ""} onChange={e => setS({ ...s, max_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
        <label>Bookmaker-Torlinienbereich <select value={range} onChange={e => setRange(Number(e.target.value))}>{LINE_RANGES.map(([lo,hi],i) => <option key={i} value={i}>{lo.toLocaleString("de-DE")}–{hi.toLocaleString("de-DE")}</option>)}</select></label>
        <label>Einsatz <input className="cell" type="number" min="0.01" step="0.01" value={s.stake ?? 1} onChange={e => setS({ ...s, stake: Number(e.target.value) })} /></label>

      </div>
      <div className="row" style={{ marginTop: 12 }}>
        {[["home", "Home"], ["away", "Away"]].map(([side,label]) => <div className="row" key={side}>
          {["min", "max"].map(bound => <label key={bound}>{label} Quote {bound === "min" ? "Min" : "Max"} <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={quoteFilters[`${side}_${bound}`] ?? ""} onChange={e => setQuoteFilters({ ...quoteFilters, [`${side}_${bound}`]: e.target.value === "" ? "" : Number(e.target.value) })} /></label>)}
        </div>)}
      </div>
      <div style={{ marginTop: 16 }}>
        <h2>Zusätzliche Metrikbedingungen (optional)</h2>
        <div className="small muted">Alle gesetzten Quotenfilter, Torlinienbereich und Bedingungen gelten gemeinsam (UND). Leere Home-/Away-Felder schränken nicht ein. Ist eine gefilterte Quote oder Metrik beim Spiel nicht vorhanden, wird das Spiel ausgeschlossen.</div>
        {s.rules.map((r,i) => <div className="row" key={i} style={{ marginTop: 8 }}>
          {r.formula !== undefined ? <input style={{ flex: 1, minWidth: 260 }} aria-label="Formel" placeholder="z. B. pred_home > pred_away" value={r.formula} onChange={e => setRule(i, { formula: e.target.value })} /> : <>
            <select aria-label="Metrik" style={{ flex: 1 }} value={r.feature} onChange={e => setRule(i, { feature: e.target.value })}>{Object.entries(meta.data?.features ?? {}).map(([k,v]) => <option key={k} value={k} title={meta.data?.feature_details?.[k]?.description}>{v}</option>)}</select>
            <select aria-label="Vergleich" value={r.op} onChange={e => setRule(i, { op: e.target.value })}>{(meta.data?.ops ?? []).map(op => <option key={op}>{op}</option>)}</select>
            <input aria-label="Metrikwert" className="cell" type="number" step="any" value={r.value} onChange={e => setRule(i, { value: Number(e.target.value) })} />
          </>}
          <button className="secondary" onClick={() => setS({ ...s, rules: s.rules.filter((_,j) => i !== j) })}>Entfernen</button>
        </div>)}
        <div className="row" style={{ marginTop: 8 }}>
          <button className="secondary" disabled={!meta.data} onClick={() => setS({ ...s, rules: [...s.rules, { feature: "pred_total_minus_line", op: ">=", value: 0 }] })}>+ Metrikbedingung</button>
          <button className="secondary" onClick={() => setS({ ...s, rules: [...s.rules, { formula: "pred_home > pred_away" }] })}>+ Formel</button>
        </div>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <label>Gruppe <select value={gender} onChange={e => { setGender(e.target.value); setLeague("all"); }}><option value="all">Alle</option><option value="men">Männer</option><option value="women">Frauen</option></select></label>
        <label>Liga <select value={league} onChange={e => setLeague(e.target.value)}><option value="all">Alle</option>{leagues.map(l => <option key={l} value={l}>{l}</option>)}</select></label>
        <span className="small muted">Alle Saisons enthalten · {included.length} Wettbewerbe · {included.reduce((n,c) => n+(c.with_stats ?? c.with_shots),0)} beendete Spiele</span>
        <button disabled={busy || !ids.length} onClick={run}>{busy ? "Analysiere …" : "Analyse berechnen"}</button>
      </div>
      <p className="small muted">Die Analyse verwendet die Quote des gewählten Marktes zwischen Min und Max und die Bookmaker-Torlinie im gewählten Bereich (Grenzen einschließlich). Leere Quotenfelder bedeuten keine Begrenzung. Home-/Away-Quotenfilter und zusätzliche Metrikbedingungen werden vor der Berechnung von Profit, Korrelationen und Grafiken gemeinsam angewendet. Ohne eingetragene Metrikbedingung gibt es keine zusätzliche +1-Regel. Für Over/Under gilt bei fehlender Quote die Standardquote 1,80; für Home/Draw/Away muss eine Quote vorhanden sein. Ältere ca. 70 % der Spieldaten dienen zur Suche; neuere ca. 30 % zur Prüfung. Spiele vom selben Tag bleiben zusammen. Die Wertebereiche entstehen ausschließlich aus den älteren Daten.</p>
      <div className="note small">Korrelation ist kein Kausalnachweis. Viele getestete Metriken können zufällige Treffer ergeben. {meta.data?.feature_details ? "Für jede Vor-Spiel-Metrik werden nur frühere Kalendertage verwendet; auch die xG-Lerndaten schließen das Zielspiel und spätere Spiele aus. Quoten/Linien müssen tatsächliche Pre-Match-Eingaben sein; ihr historischer Erfassungszeitpunkt ist nicht versioniert." : "Die Vor-Spiel-Absicherung benötigt den aktualisierten Server. Bitte stop.vbs und start.vbs ausführen."}</div>
    </div>
    {error && <div className="error">{error}</div>}
    <MetricGuide meta={meta.data} />
    {result && <>
      <div className="note small">{result.available_lines?.games ?? 0} beendete Spiele mit Torlinie in der gewählten Gruppe und Liga (alle Saisons). Vorhandener Torlinienbereich: {fmt(result.available_lines?.min)} bis {fmt(result.available_lines?.max)}.</div>
      <div className="panel kpis">
        <div className="kpi"><b>{result.overall.bets}</b><span>Auswertbare Wetten</span></div>
        <div className="kpi"><b className={result.overall.profit >= 0 ? "pos" : "neg"}>{fmt(result.overall.profit,2)}</b><span>Profit gesamt</span></div>
        <div className="kpi"><b>{pct(result.overall.roi)}</b><span>Rendite gesamt</span></div>
        <div className="kpi"><b>{result.train.bets} / {result.test.bets}</b><span>Ältere / neuere Wetten</span></div>
      </div>
      {!result.overall.bets && <div className="note">Keine auswertbaren Spiele im gewählten Bereich. Es zählen nur beendete Spiele mit gespeicherter Bookmaker-Torlinie. Prüfe Markt, Quotenfilter und Torlinienbereich oder wähle eine andere Gruppe bzw. Liga.</div>}
      <div className="panel">
        <h2>Welche Metriken hängen am stärksten mit Profit zusammen?</h2>
        <p className="small muted">Pearson-Korrelation zwischen Metrik und Nettoertrag je Wette in den älteren Daten. Sortiert nach r absteigend (positiv bis negativ); nicht berechenbare Werte stehen am Ende. Positiv: höhere Werte gehen mit höherem Ertrag einher; negativ: niedrigere Werte. Konstante Werte haben keine berechenbare Korrelation.</p>
        <input placeholder="Metrik suchen …" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="table-wrap" style={{ maxHeight: 370, overflowY: "auto" }}><table>
          <thead><tr><th>Metrik (anklicken)</th><th>Zusammenhang −1 bis +1</th><th>r</th><th>Wetten / fehlend</th></tr></thead>
          <tbody>{metrics.map(m => <tr key={m.key} className="click" onClick={() => setSelected(m.key)} style={{ background: m.key === selected ? "var(--border)" : undefined }}>
            <td><button className="secondary" onClick={() => setSelected(m.key)}>{m.label}</button></td>
            <td><svg width="200" height="22" role="img" aria-label={`Korrelation ${fmt(m.correlation,3)}`}><line x1="100" x2="100" y1="0" y2="22" stroke="currentColor" />{m.correlation !== null && <rect x={m.correlation >= 0 ? 100 : 100 + m.correlation*95} y="4" width={Math.abs(m.correlation)*95} height="14" fill={m.correlation >= 0 ? "#22c55e" : "#ef4444"} />}</svg></td>
            <td>{fmt(m.correlation,3)}</td><td>{m.coverage} / {m.missing}</td>
          </tr>)}</tbody></table></div>
      </div>
      {metric && <div className="panel">
        <h2>{metric.label}: Unter welchen Bedingungen profitabel?</h2>
        <MetricInfo info={meta.data?.feature_details?.[metric.key]} />
        <p className="small muted">Balken zeigen die Rendite je Wertebereich: blau = ältere Daten, orange = neuere Daten{result.cutoff ? ` ab ${result.cutoff}` : " (zu wenig Spieldaten für eine Trennung)"}. Profit in Einheiten des gewählten Einsatzes. Fehlende Metrikwerte werden ausgeschlossen.</p>
        <svg viewBox={`0 0 800 ${Math.max(90,metric.bins.length*66+20)}`} style={{ width: "100%", maxHeight: 380 }} role="img" aria-label="Rendite nach Metrik-Wertebereich, ältere und neuere Spiele">
          <line x1="480" x2="480" y1="0" y2={metric.bins.length*66} stroke="currentColor" />
          {metric.bins.map((b,i) => <g key={i} transform={`translate(0,${i*66})`}>
            <text x="0" y="26" fill="currentColor" fontSize="13">{condition(b)}</text>
            {[b.train,b.test].map((v,j) => <g key={j}><rect x={480+Math.min(0,(v.roi ?? 0)/scale*210)} y={j*24+3} width={Math.abs(v.roi ?? 0)/scale*210} height="17" fill={j === 0 ? "#3b82f6" : "#f59e0b"} /><text x="710" y={j*24+17} fill="currentColor" fontSize="12">{pct(v.roi)} (n={v.bets})</text></g>)}
          </g>)}
        </svg>
        <label className="small">Mindestanzahl für Kennzeichnung <input className="cell" type="number" min="1" value={minBets} onChange={e => setMinBets(Math.max(1,Number(e.target.value)))} /></label>
        <div className="table-wrap"><table><thead><tr><th>Bedingung</th><th>Ältere: Wetten</th><th>Profit</th><th>ROI</th><th>Neuere: Wetten</th><th>Profit</th><th>ROI</th><th>Bewertung</th></tr></thead>
          <tbody>{metric.bins.map((b,i) => <tr key={i}><td>{condition(b)}</td><td>{b.train.bets}</td><td className={b.train.profit >= 0 ? "pos" : "neg"}>{fmt(b.train.profit,2)}</td><td>{pct(b.train.roi)}</td><td>{b.test.bets}</td><td className={b.test.profit >= 0 ? "pos" : "neg"}>{fmt(b.test.profit,2)}</td><td>{pct(b.test.roi)}</td><td>{b.train.bets < minBets || b.test.bets < minBets ? "Wenig Daten" : b.train.profit > 0 && b.test.profit > 0 ? "Beide profitabel" : "Nicht beide profitabel"}</td></tr>)}</tbody>
        </table></div>
      </div>}
    </>}
  </>;
}
