import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, InGameSide, MetricDetails, VerifyGameMetrics, VerifyGamePick } from "../api";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

const resultClass = (r: string) => (r === "win" ? "tag good" : r === "loss" ? "tag bad" : "tag");

function value(v: number | string | boolean | null) {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(Math.abs(v) >= 100 ? 1 : 3).replace(/\.?0+$/, "");
  if (typeof v === "boolean") return v ? "ja" : "nein";
  return v;
}

export function PickTags({ picks, markets, linkStrategies = false }: { picks: VerifyGamePick[]; markets: Record<string, string>; linkStrategies?: boolean }) {
  return (
    <span className="pick-tags">
      {picks.map((p) => (
        <span key={p.strategy_id} className={resultClass(p.result)} title={`${markets[p.market] ?? p.market} · Profit ${fmt(p.profit, 2)}`}>
          {linkStrategies ? p.name || "(ohne Namen)" : markets[p.market] ?? p.market}
          {p.line !== null ? ` ${fmt(p.line, 1)}` : ""} @ {fmt(p.odds, 2)}
        </span>
      ))}
    </span>
  );
}

/** Alle Vor-Spiel-Metriken und Quoten eines Spiels, nach Gruppen. Offen: Linien, Prognosen und die Gruppe zum getippten Markt. */
export function GameMetrics({ gameId, details, markets }: { gameId: number; details: Record<string, MetricDetails>; markets: Record<string, string> }) {
  const d = useLoad(() => api.verifyGameMetrics(gameId), [gameId]);
  const [showAlt, setShowAlt] = useState(false);
  const [query, setQuery] = useState("");
  if (d.error) return <div className="error">{d.error}</div>;
  if (!d.data) return <div className="muted small">Lade Metriken …</div>;
  const markets_ = new Set(d.data.picks.map((p) => p.market));
  const openByDefault = new Set(["lines", "line_gap", "value", "pred",
    ...(markets_.has("over") || markets_.has("under") ? ["total"] : []),
    ...([...markets_].some((m) => m !== "over" && m !== "under") ? ["side"] : [])]);
  const q = query.trim().toLowerCase();
  const renderGroup = (g: VerifyGameMetrics["groups"][number]) => {
    const items = g.metrics.filter((m) => (showAlt || !m.alt) && (!q || m.name.toLowerCase().includes(q) || (details[m.name]?.label ?? "").toLowerCase().includes(q)));
    if (!items.length) return null;
    return (
      <details key={g.key} className="metric-group" open={!!q || openByDefault.has(g.key)}>
        <summary>{g.label} <span className="muted">({items.length})</span></summary>
        <table>
          <tbody>
            {items.map((m) => (
              <tr key={m.name} title={details[m.name]?.description}>
                <td>
                  <code>{m.name}</code>
                  {details[m.name]?.label && details[m.name].label !== m.name && <div className="muted tiny">{details[m.name].label}</div>}
                </td>
                <td className="num">{value(m.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    );
  };
  const ig = d.data.in_game;
  const igRows: [string, (s: InGameSide) => string][] = [
    ["Tore", (s) => value(s.goals)],
    ["Halbzeit", (s) => value(s.ht)],
    ["Würfe", (s) => value(s.shots)],
    ["Tore laut Würfen", (s) => value(s.shot_goals)],
    ["davon 7-m-Würfe", (s) => value(s.seven_m)],
    ["xG (gespeichert)", (s) => (s.xg === null ? "–" : fmt(s.xg, 1))],
    ["Angriffe", (s) => value(s.attacks)],
  ];
  return (
    <div className="game-metrics">
      {d.data.picks.length > 0 && (
        <div className="small" style={{ marginBottom: 8 }}>
          Tipps auf dieses Spiel (Quote beim Tipp): <PickTags picks={d.data.picks} markets={markets} linkStrategies />
        </div>
      )}
      <div className="row small" style={{ gap: 12, alignItems: "center", marginBottom: 8 }}>
        <input placeholder="Metrik suchen …" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: 200 }} />
        <label><input type="checkbox" checked={showAlt} onChange={(e) => setShowAlt(e.target.checked)} /> auch Varianten „_alt“ (anderes xG-Modell)</label>
      </div>
      {d.data.phases.map((ph) => {
        const groups = d.data!.groups.filter((g) => g.phase === ph.key).map(renderGroup).filter(Boolean);
        if (ph.key === "game") {
          if (!ig) return null;
          return (
            <div key={ph.key} className={`metric-phase phase-${ph.key}`}>
              <h3>{ph.label}</h3>
              <div className="muted small">{ph.description}</div>
              <table className="in-game">
                <thead><tr><th></th><th className="num">Heim</th><th className="num">Gast</th></tr></thead>
                <tbody>
                  {igRows.map(([label, f]) => <tr key={label}><td>{label}</td><td className="num">{f(ig.home)}</td><td className="num">{f(ig.away)}</td></tr>)}
                </tbody>
              </table>
              {ig.home.xg !== null && <div className="muted tiny">xG laut heutigem Wurfmodell (nachträglich geschätzt) – nur zur Einordnung.</div>}
            </div>
          );
        }
        if (!groups.length) return null;
        return (
          <div key={ph.key} className={`metric-phase phase-${ph.key}`}>
            <h3>{ph.label}</h3>
            <div className="muted small">{ph.description}</div>
            <div className="metric-groups">{groups}</div>
          </div>
        );
      })}
    </div>
  );
}

/** Beendete Spiele mit abgerechneten Tipps – Zeile anklicken für alle Metriken und Quoten. */
export default function VerifyGames({ markets, details }: { markets: Record<string, string>; details: Record<string, MetricDetails> }) {
  const d = useLoad(() => api.verifyGames(), []);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "win" | "loss">("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (d.data ?? []).filter((g) =>
      (filter === "all" || g.picks.some((p) => p.result === filter)) &&
      (!q || `${g.home} ${g.away} ${g.league ?? ""} ${g.picks.map((p) => p.name).join(" ")}`.toLowerCase().includes(q)));
  }, [d.data, filter, query]);

  return (
    <div className="panel table-wrap">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 6, gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Beendete Spiele mit Tipps</h2>
        <div className="row small" style={{ gap: 10, alignItems: "center" }}>
          <input placeholder="Team, Liga oder Strategie …" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: 220 }} />
          <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="all">alle Tipps</option>
            <option value="win">mit gewonnenem Tipp</option>
            <option value="loss">mit verlorenem Tipp</option>
          </select>
        </div>
      </div>
      {d.error && <div className="error">{d.error}</div>}
      {d.loading && !d.data && <div className="muted small">Lade …</div>}
      <table>
        <thead>
          <tr><th>Anpfiff</th><th>Spiel</th><th>Liga</th><th>Ergebnis</th><th>Tipps (Strategie · Linie @ Quote)</th><th className="num">Profit</th></tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <Fragment key={g.game_id}>
              <tr className={open === g.game_id ? "selected" : ""} onClick={() => setOpen(open === g.game_id ? null : g.game_id)} style={{ cursor: "pointer" }}>
                <td className="small">{dateTime(g.start)}</td>
                <td><Link to={`/spiele/${g.game_id}`} onClick={(e) => e.stopPropagation()}>{g.home} – {g.away}</Link></td>
                <td className="small">{g.league ?? "–"}</td>
                <td>{g.home_score}:{g.away_score}</td>
                <td><PickTags picks={g.picks} markets={markets} linkStrategies /></td>
                <td className={`num ${g.profit > 0 ? "pos" : g.profit < 0 ? "neg" : ""}`}>{fmt(g.profit, 2)}</td>
              </tr>
              {open === g.game_id && (
                <tr className="expanded"><td colSpan={6}><GameMetrics gameId={g.game_id} details={details} markets={markets} /></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      {!d.loading && rows.length === 0 && <div className="small muted">Noch keine beendeten Spiele mit Tipps.</div>}
      <div className="small muted" style={{ marginTop: 6 }}>
        Zeile anklicken für alle Metriken und Quoten des Spiels, nach Gruppen. Grün = Tipp gewonnen, rot = verloren.
      </div>
    </div>
  );
}
