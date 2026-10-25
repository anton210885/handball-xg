import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, Backtest, Rule, Strategy, StrategySummary as SummaryRow } from "../api";
import MetricGuide from "../components/MetricGuide";
import StrategySummary from "../components/StrategySummary";
import { useCompetition } from "../App";
import { dateTime, fmt, pct } from "../labels";
import { useLoad } from "../useLoad";

const EMPTY: Strategy = {
  name: "",
  market: "over",
  min_games: 3,
  stake: 1,
  min_odds: null,
  max_odds: null,
  rules: [{ feature: "pred_total_minus_line", op: ">=", value: 2 }],
};

export default function StrategiesPage() {
  const { competitions } = useCompetition();
  const location = useLocation();
  const meta = useLoad(() => api.meta(), []);
  const saved = useLoad(() => api.strategies(), []);
  const [s, setS] = useState<Strategy>(EMPTY);
  useEffect(() => {
    if (location.state?.draft) setS(location.state.draft as Strategy);
  }, [location.state]);
  const [result, setResult] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [summary, setSummary] = useState<SummaryRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  // Saisons für Backtests: standardmäßig alle mit importierten Würfen
  const [compIds, setCompIds] = useState<number[]>([]);
  useEffect(() => {
    if (!compIds.length) setCompIds(competitions.filter((c) => (c.with_stats ?? c.with_shots) > 0).map((c) => c.id));
  }, [competitions]);
  const toggleComp = (id: number) => {
    setCompIds(compIds.includes(id) ? compIds.filter((x) => x !== id) : [...compIds, id]);
    setSummary(null);
    setResult(null);
  };

  useEffect(() => { setResult(null); }, [s]);

  const features = meta.data?.features ?? {};
  const setRule = (i: number, patch: Partial<Rule>) =>
    setS({ ...s, rules: s.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });

  const run = async () => {
    setError(null);
    try {
      setResult(await api.backtest(s, compIds));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const save = async () => {
    setError(null);
    try {
      const r: any = await api.saveStrategy(s);
      if (r?.id) setS({ ...s, id: r.id });
      saved.reload();
      setSummary(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const runSummary = async () => {
    setError(null);
    setBusy(true);
    try {
      setSummary(await api.strategySummary(compIds));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const pick = async (id: number) => {
    const x = (saved.data ?? []).find((y) => y.id === id);
    if (!x) return;
    setS(x);
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      setResult(await api.backtest(x, compIds));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const savedShown = (saved.data ?? []).filter((x) => x.name.toLowerCase().includes(filter.toLowerCase()));

  const remove = async (id: number) => {
    await api.deleteStrategy(id);
    if (s.id === id) setS(EMPTY);
    saved.reload();
  };

  return (
    <>
      <div className="topbar">
        <h1>Strategien</h1>
        <button className="secondary" onClick={() => { setS(EMPTY); setResult(null); }}>
          Neue Strategie
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      <MetricGuide meta={meta.data} />

      <div className="panel row small">
        <b>Backtest über:</b>
        {competitions
          .filter((c) => (c.with_stats ?? c.with_shots) > 0)
          .map((c) => (
            <label key={c.id} className="row" style={{ gap: 4 }}>
              <input type="checkbox" checked={compIds.includes(c.id)} onChange={() => toggleComp(c.id)} />
              {c.season} · {c.gender === "women" ? "Frauen" : "Männer"}
            </label>
          ))}
        <span className="muted">Linien gibt es bisher für 24/25 und 25/26 (bis Dez. 2025).</span>
      </div>

      <div className="grid2" style={{ gridTemplateColumns: "minmax(260px, 1fr) 2fr" }}>
        <div className="panel">
          <h2>Gespeichert ({(saved.data ?? []).length})</h2>
          <input placeholder="Suchen …" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "100%", marginBottom: 6 }} />
          {(saved.data ?? []).length === 0 && <div className="muted small">Noch keine Strategie gespeichert.</div>}
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
          {savedShown.map((x) => (
            <div key={x.id} className="row" style={{ justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
              <a href="#" onClick={(e) => { e.preventDefault(); setS(x); setResult(null); }}>
                {x.name || `Strategie ${x.id}`}
              </a>
              <span className="row">
                <span className="tag">{meta.data?.markets[x.market] ?? x.market}</span>
                <button className="secondary" onClick={() => remove(x.id!)}>✕</button>
              </span>
            </div>
          ))}
          </div>
        </div>

        <div className="panel">
          <h2>{s.id ? "Strategie bearbeiten" : "Strategie bauen"}</h2>
          <div className="row" style={{ marginBottom: 10 }}>
            <input placeholder="Name" value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} style={{ flex: 1, minWidth: 180 }} />
            <select value={s.market} onChange={(e) => setS({ ...s, market: e.target.value })}>
              {Object.entries(meta.data?.markets ?? {}).map(([k, v]) => (
                <option key={k} value={k} title={meta.data?.feature_details?.[k]?.description}>{v}</option>
              ))}
            </select>
            <label className="small muted">min. Spiele je Team</label>
            <input className="cell" type="number" value={s.min_games} onChange={(e) => setS({ ...s, min_games: Number(e.target.value) })} />
          </div>
          <div className="row" style={{ marginBottom: 10 }}>
            <label>Quote von <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.min_odds ?? ""} onChange={(e) => setS({ ...s, min_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
            <label>bis <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.max_odds ?? ""} onChange={(e) => setS({ ...s, max_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
            <label>Einsatz je Wette <input className="cell" type="number" min="0.01" step="0.01" value={s.stake ?? 1} onChange={(e) => setS({ ...s, stake: Number(e.target.value) })} /></label>
          </div>
          <div className="small muted" style={{ marginBottom: 10 }}>Der Quotenbereich gilt für den gewählten Wettmarkt. Profit und Einsatz werden in derselben Einheit angezeigt (z. B. Euro).</div>
          <div className="small muted" style={{ marginBottom: 6 }}>Alle Bedingungen müssen erfüllt sein (UND):</div>
          {s.rules.map((r, i) =>
            r.formula !== undefined ? (
              <div key={i} className="row" style={{ marginBottom: 6 }}>
                <span className="tag">Formel</span>
                <input
                  list="legacy-names"
                  value={r.formula}
                  onChange={(e) => setRule(i, { formula: e.target.value })}
                  style={{ flex: 1, minWidth: 220, fontFamily: "Consolas, monospace" }}
                />
                <button className="secondary" onClick={() => setS({ ...s, rules: s.rules.filter((_, j) => j !== i) })}>✕</button>
              </div>
            ) : (
            <div key={i} className="row" style={{ marginBottom: 6 }}>
              <select value={r.feature} onChange={(e) => setRule(i, { feature: e.target.value })} style={{ flex: 1, minWidth: 220 }}>
                {Object.entries(features).map(([k, v]) => (
                  <option key={k} value={k} title={meta.data?.feature_details?.[k]?.description}>{v}</option>
                ))}
              </select>
              <select value={r.op} onChange={(e) => setRule(i, { op: e.target.value })}>
                {(meta.data?.ops ?? []).map((o) => <option key={o}>{o}</option>)}
              </select>
              <input className="cell" type="number" step="0.5" value={r.value} onChange={(e) => setRule(i, { value: Number(e.target.value) })} />
              <button className="secondary" onClick={() => setS({ ...s, rules: s.rules.filter((_, j) => j !== i) })}>✕</button>
            </div>
            ),
          )}
          <datalist id="legacy-names">
            {(meta.data?.legacy_names ?? []).map((n) => <option key={n} value={n} />)}
          </datalist>
          <div className="row" style={{ marginTop: 10 }}>
            <button className="secondary" onClick={() => setS({ ...s, rules: [...s.rules, { feature: "pred_total", op: ">=", value: 58 }] })}>
              + Bedingung
            </button>
            <button
              className="secondary"
              title="Formel mit den alten Spaltennamen, z. B. (homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) - 3 > over"
              onClick={() => setS({ ...s, rules: [...s.rules, { formula: "(home_expGoal + away_expGoal) + 2 > over" }] })}
            >
              + Formel
            </button>
            <span style={{ flex: 1 }} />
            <button onClick={run}>Backtest</button>
            <button className="secondary" onClick={save}>Speichern</button>
            {s.id && <button className="secondary" onClick={() => { setS({ ...s, id: undefined, name: `${s.name} (Kopie)` }); setResult(null); }}>Als neue Strategie kopieren</button>}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Alle Strategien im Vergleich</h2>
          <button disabled={busy || !compIds.length} onClick={runSummary}>
            {busy ? "Rechne …" : summary ? "Neu berechnen" : "Alle testen"}
          </button>
        </div>
        {summary ? (
          <StrategySummary rows={summary} markets={meta.data?.markets ?? {}} onPick={pick} />
        ) : (
          <div className="small muted">Backtest aller gespeicherten Strategien über die gewählten Saisons.</div>
        )}
      </div>

      {result && (
        <>
          <div className="panel">
            <h2>Backtest</h2>
            <div className="kpis">
              <div className="kpi"><b>{result.bets}</b><span>Wetten</span></div>
              <div className="kpi"><b>{result.wins} / {result.losses} / {result.pushes}</b><span>Gewonnen / verloren / zurück</span></div>
              <div className="kpi"><b>{pct(result.hit_rate)}</b><span>Trefferquote</span></div>
              <div className="kpi"><b>{fmt(result.avg_odds, 2)}</b><span>Ø Quote</span></div>
              <div className="kpi"><b>{fmt(result.total_staked, 2)}</b><span>Gesamteinsatz</span></div>
              <div className="kpi"><b className={result.profit >= 0 ? "pos" : "neg"}>{fmt(result.profit, 2)}</b><span>Profit (Einsatz {fmt(result.stake, 2)} je Wette)</span></div>
              <div className="kpi"><b className={(result.roi ?? 0) >= 0 ? "pos" : "neg"}>{pct(result.roi)}</b><span>Rendite</span></div>
            </div>
            {result.bets === 0 && (
              <div className="note small">
                Keine auswertbaren Spiele. Over/Under und Handicap brauchen eingetragene Linien bei beendeten Spielen
                (Seite „Linien & Quoten“), 1/2 braucht Quoten.
              </div>
            )}
            <div className="small muted">
              Ohne eingetragene Over-/Under-Quote rechnet der Backtest mit 1,80 (wie deine alte Auswertung). Wenige Wetten = wenig Aussagekraft.
            </div>
          </div>

          {result.open.length > 0 && (
            <div className="panel table-wrap">
              <h2>Passt auf {result.open.length} offene Spiele</h2>
              <table>
                <tbody>
                  {result.open.map((g) => (
                    <tr key={g.id}>
                      <td>{dateTime(g.start)}</td>
                      <td><Link to={`/spiele/${g.id}`}>{g.home.name} – {g.away.name}</Link></td>
                      <td className="num">Prognose {fmt(g.features?.pred_total)}</td>
                      <td className="num">Linie {fmt(g.line?.over_line)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.details.length > 0 && (
            <div className="panel table-wrap">
              <h2>Einzelne Wetten</h2>
              <table>
                <thead>
                  <tr>
                    <th>Datum</th><th>Spiel</th><th className="num">Ergebnis</th><th className="num">Prognose</th>
                    <th className="num">Linie</th><th className="num">Quote</th><th>Ausgang</th><th className="num">Gewinn</th>
                  </tr>
                </thead>
                <tbody>
                  {result.details.map((b) => (
                    <tr key={b.id}>
                      <td>{dateTime(b.start)}</td>
                      <td><Link to={`/spiele/${b.id}`}>{b.home.name} – {b.away.name}</Link></td>
                      <td className="num">{b.home_score}:{b.away_score}</td>
                      <td className="num">{fmt(b.features?.pred_total)}</td>
                      <td className="num">{fmt(b.line?.over_line)}</td>
                      <td className="num">{fmt(b.odds, 2)}</td>
                      <td><span className={`tag ${b.result === "win" ? "good" : b.result === "loss" ? "bad" : ""}`}>{b.result === "win" ? "gewonnen" : b.result === "loss" ? "verloren" : "zurück"}</span></td>
                      <td className={`num ${b.profit >= 0 ? "pos" : "neg"}`}>{fmt(b.profit, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
