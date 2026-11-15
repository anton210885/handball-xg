import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Rule } from "../api";
import { describe, Names } from "./ConditionEditor";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

const ruleText = (r: Rule): string =>
  (r as any).formula ?? `${(r as any).feature} ${(r as any).op} ${(r as any).value}`;

const signed = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${fmt(v, d)}`;
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${fmt(v * 100, 1)} %`);
const cls = (v: number | null | undefined) => (v && v > 0 ? "pos" : v && v < 0 ? "neg" : "");

/** Kurzansicht einer Strategie: Bedingungen, Backtest, Verifikator-Ergebnisse und letzte Tipps. */
export default function StrategyPopup({ id, onClose }: { id: number; onClose: () => void }) {
  const navigate = useNavigate();
  const all = useLoad(() => api.strategies(), []);
  const meta = useLoad(() => api.meta(), []);
  const stats = useLoad(() => api.strategyStats(), []);
  const live = useLoad(() => api.verifyDetail(id), [id]);
  const s = all.data?.find((x) => x.id === id);
  const bt = stats.data?.[String(id)];
  const v = live.data;
  const markets = meta.data?.markets ?? {};
  const names: Names = useMemo(() => {
    const out: Names = {};
    for (const [k, d] of Object.entries(meta.data?.feature_details ?? {})) out[k] = { label: d.label, description: d.description };
    for (const [k, l] of Object.entries(meta.data?.features ?? {})) out[k] ??= { label: l };
    return out;
  }, [meta.data]);
  const recent = (v?.picks ?? []).filter((p) => p.finished).slice(-10).reverse();
  const open = (v?.picks ?? []).filter((p) => !p.finished);

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog panel strategy-popup" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", flexWrap: "nowrap" }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ margin: 0, overflowWrap: "anywhere" }}>{s?.name || v?.name || `Strategie ${id}`}</h2>
            <div className="small muted" style={{ marginTop: 4 }}>
              #{id} · <span className="tag">{markets[s?.market ?? v?.market ?? ""] ?? s?.market ?? v?.market}</span>
              {s?.archived && <span className="tag bad">archiviert</span>}
              {s && <> · min. {s.min_games} Spiele je Team{s.min_odds || s.max_odds ? ` · Quote ${s.min_odds ?? "…"}–${s.max_odds ?? "…"}` : ""} · Einsatz {s.stake ?? 1}</>}
            </div>
          </div>
          <button className="secondary" onClick={onClose}>Schließen</button>
        </div>

        {s && s.rules.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="small muted">Bedingungen</div>
            <ul className="rule-list">
              {s.rules.map((r, i) => {
                const text = ruleText(r);
                const label = describe(text, names);
                const plain = text.split(/\s/)[0];
                return <li key={i}><span>{label}</span>{!label.includes(plain) && <code className="tiny muted">{text}</code>}</li>;
              })}
            </ul>
          </div>
        )}

        <div className="popup-cols">
          <div>
            <h3>Backtest (alle beendeten Spiele)</h3>
            {bt ? (
              <div className="kpis">
                <div className="kpi"><b>{bt.bets}</b><span>Wetten</span></div>
                <div className="kpi"><b className={cls(bt.profit)}>{signed(bt.profit)}</b><span>Profit</span></div>
                <div className="kpi"><b className={cls(bt.roi)}>{pct(bt.roi)}</b><span>ROI</span></div>
              </div>
            ) : <div className="muted small">{stats.error ?? "Lade …"}</div>}
          </div>
          <div>
            <h3>Verifikator (echte Tipps vor Anpfiff)</h3>
            {v ? (
              <>
                <div className="kpis">
                  <div className="kpi"><b>{v.settled}</b><span>abgerechnet{v.open ? ` · ${v.open} offen` : ""}</span></div>
                  <div className="kpi"><b>{v.hit_rate === null ? "–" : `${fmt(v.hit_rate * 100, 0)} %`}</b><span>Treffer ({v.wins}/{v.losses})</span></div>
                  <div className="kpi"><b className={cls(v.profit)}>{signed(v.profit)}</b><span>Profit</span></div>
                  <div className="kpi"><b className={cls(v.roi)}>{pct(v.roi)}</b><span>ROI</span></div>
                </div>
                {v.settled > 0 && (
                  <div className="small muted">
                    Aktuell {v.current} {v.current_kind === "win" ? "gewonnen" : "verloren"} in Folge · längste Verlustserie {v.max_loss}
                  </div>
                )}
              </>
            ) : <div className="muted small">{live.error ?? "Lade …"}</div>}
          </div>
        </div>

        {open.length > 0 && (
          <>
            <h3>Offene Tipps</h3>
            <div className="table-wrap">
              <table>
                <tbody>
                  {open.map((p) => (
                    <tr key={p.game_id}>
                      <td><Link to={`/spiele/${p.game_id}`}>{p.home} – {p.away}</Link><div className="muted tiny">{dateTime(p.start)}</div></td>
                      <td className="num">{p.line !== null ? fmt(p.line, 1) : ""} @ {fmt(p.odds, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {recent.length > 0 && (
          <>
            <h3>Letzte Ergebnisse</h3>
            <div className="table-wrap">
              <table>
                <tbody>
                  {recent.map((p) => (
                    <tr key={p.game_id}>
                      <td><Link to={`/spiele/${p.game_id}`}>{p.home} – {p.away}</Link><div className="muted tiny">{dateTime(p.start)}</div></td>
                      <td>{p.home_score}:{p.away_score}</td>
                      <td className="num">{p.line !== null ? fmt(p.line, 1) : ""} @ {fmt(p.odds, 2)}</td>
                      <td><span className={`tag ${p.result === "win" ? "good" : p.result === "loss" ? "bad" : ""}`}>{p.result === "win" ? "gewonnen" : p.result === "loss" ? "verloren" : "zurück"}</span></td>
                      <td className={`num ${cls(p.profit)}`}>{signed(p.profit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {v && v.picks.length === 0 && <div className="small muted" style={{ marginTop: 8 }}>Der Verifikator hat für diese Strategie noch keine Tipps festgehalten.</div>}

        <div className="row" style={{ marginTop: 14, gap: 8 }}>
          <button onClick={() => s && navigate("/strategien", { state: { draft: s } })} disabled={!s}>Im Baukasten öffnen (Backtest)</button>
          <button className="secondary" onClick={() => navigate("/verifikator", { state: { strategyId: id } })}>Im Verifikator öffnen</button>
        </div>
      </div>
    </div>
  );
}
