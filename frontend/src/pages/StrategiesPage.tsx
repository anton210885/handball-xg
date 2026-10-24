import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Backtest, Rule, Strategy } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt, pct } from "../labels";
import { useLoad } from "../useLoad";

const EMPTY: Strategy = {
  name: "",
  market: "over",
  min_games: 3,
  rules: [{ feature: "pred_total_minus_line", op: ">=", value: 2 }],
};

export default function StrategiesPage() {
  const { competitionId } = useCompetition();
  const meta = useLoad(() => api.meta(), []);
  const saved = useLoad(() => api.strategies(), []);
  const [s, setS] = useState<Strategy>(EMPTY);
  const [result, setResult] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);

  const features = meta.data?.features ?? {};
  const setRule = (i: number, patch: Partial<Rule>) =>
    setS({ ...s, rules: s.rules.map((r, j) => (j === i ? { ...r, ...patch } : r)) });

  const run = async () => {
    setError(null);
    try {
      setResult(await api.backtest(s, competitionId));
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
    } catch (e: any) {
      setError(e.message);
    }
  };

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

      <div className="grid2" style={{ gridTemplateColumns: "minmax(260px, 1fr) 2fr" }}>
        <div className="panel">
          <h2>Gespeichert</h2>
          {(saved.data ?? []).length === 0 && <div className="muted small">Noch keine Strategie gespeichert.</div>}
          {(saved.data ?? []).map((x) => (
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

        <div className="panel">
          <h2>{s.id ? "Strategie bearbeiten" : "Strategie bauen"}</h2>
          <div className="row" style={{ marginBottom: 10 }}>
            <input placeholder="Name" value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} style={{ flex: 1, minWidth: 180 }} />
            <select value={s.market} onChange={(e) => setS({ ...s, market: e.target.value })}>
              {Object.entries(meta.data?.markets ?? {}).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <label className="small muted">min. Spiele je Team</label>
            <input className="cell" type="number" value={s.min_games} onChange={(e) => setS({ ...s, min_games: Number(e.target.value) })} />
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>Alle Bedingungen müssen erfüllt sein (UND):</div>
          {s.rules.map((r, i) => (
            <div key={i} className="row" style={{ marginBottom: 6 }}>
              <select value={r.feature} onChange={(e) => setRule(i, { feature: e.target.value })} style={{ flex: 1, minWidth: 220 }}>
                {Object.entries(features).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <select value={r.op} onChange={(e) => setRule(i, { op: e.target.value })}>
                {(meta.data?.ops ?? []).map((o) => <option key={o}>{o}</option>)}
              </select>
              <input className="cell" type="number" step="0.5" value={r.value} onChange={(e) => setRule(i, { value: Number(e.target.value) })} />
              <button className="secondary" onClick={() => setS({ ...s, rules: s.rules.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <div className="row" style={{ marginTop: 10 }}>
            <button className="secondary" onClick={() => setS({ ...s, rules: [...s.rules, { feature: "pred_total", op: ">=", value: 58 }] })}>
              + Bedingung
            </button>
            <span style={{ flex: 1 }} />
            <button onClick={run}>Backtest</button>
            <button className="secondary" onClick={save}>Speichern</button>
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="panel">
            <h2>Backtest</h2>
            <div className="kpis">
              <div className="kpi"><b>{result.bets}</b><span>Wetten</span></div>
              <div className="kpi"><b>{result.wins} / {result.losses} / {result.pushes}</b><span>Gewonnen / verloren / zurück</span></div>
              <div className="kpi"><b>{pct(result.hit_rate)}</b><span>Trefferquote</span></div>
              <div className="kpi"><b className={result.profit >= 0 ? "pos" : "neg"}>{fmt(result.profit, 2)}</b><span>Gewinn (Einsatz 1)</span></div>
              <div className="kpi"><b className={(result.roi ?? 0) >= 0 ? "pos" : "neg"}>{pct(result.roi)}</b><span>Rendite</span></div>
            </div>
            {result.bets === 0 && (
              <div className="note small">
                Keine auswertbaren Spiele. Over/Under und Handicap brauchen eingetragene Linien bei beendeten Spielen
                (Seite „Linien & Quoten“), 1/2 braucht Quoten.
              </div>
            )}
            <div className="small muted">
              Ohne eingetragene Quote rechnet der Backtest mit 1,80 (wie deine alte Auswertung). Wenige Wetten = wenig Aussagekraft.
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
