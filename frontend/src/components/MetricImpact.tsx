import { useEffect, useMemo, useState } from "react";
import { api, ImpactClass, ImpactMetric, ImpactResult, Strategy } from "../api";
import { fmt, pct } from "../labels";
import { nameLabel, Names } from "./ConditionEditor";
import { favoriteRank, isTotalMarket, LINE_METRICS } from "../favorites";

const ORDER = ["home", "away", "draw", "over", "under", "hdp_home", "hdp_away"];
type Sort = "best" | "spread" | "r" | "name";
type Group = "all" | "fav" | "legacy" | "new";

const signed = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "–" : (v > 0 ? "+" : "") + fmt(v, d));
const short = (v: number) => {
  const a = Math.abs(v);
  return fmt(v, a >= 100 ? 0 : a >= 10 ? 1 : 2);
};

/** Balken je Klasse: oben Anzahl Wetten, unten Profit (grün/rot um die Null-Linie) – wie das Notebook-Diagramm. */
function ImpactChart({ m, selected, onSelect }: { m: ImpactMetric; selected: number | null; onSelect: (i: number) => void }) {
  const k = m.classes.length;
  const W = Math.max(480, k * 44), barW = (W - 40) / k;
  const maxCount = Math.max(1, ...m.classes.map((c) => c.bets));
  const maxAbs = Math.max(1, ...m.classes.map((c) => Math.abs(c.profit)));
  const countH = 46, profitH = 110, top = 14, mid = top + countH + 18 + profitH / 2;
  return (
    <svg viewBox={`0 0 ${W} ${top + countH + 18 + profitH + 34}`} style={{ width: "100%", maxWidth: W, display: "block" }} role="img"
      aria-label={`Wetten und Profit je Klasse für ${m.name}`}>
      <text x={0} y={10} className="impact-axis">Wetten</text>
      <text x={0} y={top + countH + 14} className="impact-axis">Profit</text>
      <line x1={36} x2={W} y1={mid} y2={mid} className="impact-zero" />
      {m.classes.map((c, i) => {
        const x = 38 + i * barW;
        const ch = (c.bets / maxCount) * countH;
        const ph = (Math.abs(c.profit) / maxAbs) * (profitH / 2);
        const tip = `${short(c.low)} bis ${short(c.high)}\n${c.bets} Wetten · ${c.wins} gewonnen · Trefferquote ${pct(c.hit_rate)}\nProfit ${signed(c.profit, 2)} · Rendite ${pct(c.roi)}`;
        return (
          <g key={i} className={`impact-col${selected === i ? " sel" : ""}`} onClick={() => onSelect(i)} style={{ cursor: "pointer" }}>
            <title>{tip}</title>
            <rect x={x} y={top} width={barW - 2} height={countH + 18 + profitH + 30} className="impact-hit" />
            <rect x={x + 4} y={top + countH - ch} width={barW - 10} height={Math.max(ch, c.bets ? 1 : 0)} rx={2} className="impact-count" />
            {c.bets > 0 && <text x={x + barW / 2 - 1} y={top + countH - ch - 2} textAnchor="middle" className="impact-num">{c.bets}</text>}
            {c.bets > 0 && (
              <rect x={x + 4} y={c.profit >= 0 ? mid - ph : mid} width={barW - 10} height={Math.max(ph, 1)} rx={2}
                className={c.profit >= 0 ? "impact-pos" : "impact-neg"} opacity={c.bets < 5 ? 0.45 : 1} />
            )}
            <text x={x + barW / 2 - 1} y={top + countH + 18 + profitH + 12} textAnchor="middle" className="impact-num">{short(c.low)}</text>
          </g>
        );
      })}
      <text x={W - 2} y={top + countH + 18 + profitH + 26} textAnchor="end" className="impact-num">bis {short(m.classes[k - 1].high)}</text>
    </svg>
  );
}

function MetricRow({ m, names, open, onToggle, onAdd, rank }: {
  rank: 0 | 1 | 2; m: ImpactMetric; names: Names; open: boolean; onToggle: () => void; onAdd?: (name: string, lo: number, hi: number) => void;
}) {
  const [sel, setSel] = useState<number | null>(null);
  const c: ImpactClass | null = sel !== null ? m.classes[sel] : m.best;
  return (
    <div className={`impact-row${rank === 0 ? " fav" : rank === 1 ? " fav2" : ""}`}>
      <button className="impact-head" onClick={onToggle} title={names[m.name]?.description}>
        <span className="impact-caret">{open ? "▾" : "▸"}</span>
        <span className="impact-name">{rank === 0 && <span className="fav-star" title="Deine Notebook-Metrik, passend zum gewählten Markt">★ </span>}{rank === 1 && <span className="fav-star dim" title="Deine Notebook-Metrik">☆ </span>}{nameLabel(m.name, names)} <code className="muted small">{m.name}</code></span>
        <span className="small muted">{m.bets} Wetten · r {fmt(m.r, 2)}</span>
        <span className={`small ${m.best && m.best.profit > 0 ? "pos" : ""}`}>
          {m.best ? <>beste Klasse {short(m.best.low)} bis {short(m.best.high)}: <b>{signed(m.best.profit)}</b> ({m.best.bets} W, {pct(m.best.roi)})</> : "–"}
        </span>
      </button>
      {open && (
        <div className="impact-body">
          <ImpactChart m={m} selected={sel} onSelect={(i) => setSel(i === sel ? null : i)} />
          {c && (
            <div className="row small" style={{ gap: 10, marginTop: 4 }}>
              <span>{sel === null ? "Beste Klasse" : "Gewählt"}: <b>{short(c.low)} bis {short(c.high)}</b> · {c.bets} Wetten · Trefferquote {pct(c.hit_rate)} ·
                Profit <b className={c.profit >= 0 ? "pos" : "neg"}>{signed(c.profit, 2)}</b> · Rendite {pct(c.roi)}</span>
              {onAdd && <button className="secondary small" onClick={() => onAdd(m.name, c.low, c.high)}>als Bedingung übernehmen</button>}
              <span className="muted">Balken anklicken wählt eine Klasse.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Einfluss der Metriken: für die Spiele der Strategie jede Metrik in Klassen, je Klasse Wetten und Profit. */
export default function MetricImpact({ strategy, compIds, excludeErrors, names, markets, legacyNames, onAdd }: {
  strategy: Strategy; compIds: number[]; excludeErrors: boolean; names: Names; markets: Record<string, string>;
  legacyNames: string[]; onAdd?: (name: string, lo: number, hi: number) => void;
}) {
  const [market, setMarket] = useState(strategy.market);
  const [bins, setBins] = useState(15);
  const [mode, setMode] = useState<"width" | "count">("width");
  const [sort, setSort] = useState<Sort>("best");
  const [group, setGroup] = useState<Group>("all");
  const [showAlt, setShowAlt] = useState(false);
  const [favFirst, setFavFirst] = useState(true);
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(30);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [data, setData] = useState<ImpactResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    setBusy(true); setError(null);
    api.metricImpact(strategy, compIds, excludeErrors, market, bins, mode)
      .then((d) => { if (!stop) setData(d); })
      .catch((e) => { if (!stop) setError(e.message); })
      .finally(() => { if (!stop) setBusy(false); });
    return () => { stop = true; };
  }, [strategy, compIds.join(","), excludeErrors, market, bins, mode]);

  const legacy = useMemo(() => new Set(legacyNames), [legacyNames]);
  const list = useMemo(() => {
    const q = search.trim().toLowerCase();
    const items = (data?.metrics ?? []).filter((m) =>
      (showAlt || !m.name.endsWith("_alt")) &&
      (group === "all" || (group === "fav" ? favoriteRank(m.name, market) < 2 : (group === "legacy") === legacy.has(m.name))) &&
      (!q || m.name.toLowerCase().includes(q) || nameLabel(m.name, names).toLowerCase().includes(q)));
    const key = (m: ImpactMetric) =>
      sort === "best" ? -(m.best?.profit ?? -1e9) : sort === "spread" ? -(m.spread ?? -1e9) : sort === "r" ? -Math.abs(m.r ?? 0) : 0;
    // Over-Linie steht immer ganz oben, die übrigen Linien/Quoten direkt danach
    const fav = (m: ImpactMetric) => m.name === "over_line" ? -2 : !favFirst ? 0 : LINE_METRICS.has(m.name) ? -1 : favoriteRank(m.name, market);
    return [...items].sort((a, b) => fav(a) - fav(b) || key(a) - key(b) || nameLabel(a.name, names).localeCompare(nameLabel(b.name, names)));
  }, [data, search, group, showAlt, sort, names, legacy, favFirst, market]);

  const shown = list.slice(0, limit);
  const toggle = (n: string) => setOpen((o) => { const x = new Set(o); x.has(n) ? x.delete(n) : x.add(n); return x; });

  return (
    <div className="panel">
      <h2>Einfluss der Metriken {busy && <span className="muted small">– rechne …</span>}</h2>
      <div className="small muted" style={{ marginBottom: 8 }}>
        Für die {data?.total.bets ?? "…"} Wetten deiner Strategie (alle Filter oben gelten) wird jede Metrik in Klassen geteilt –
        wie <code>pd.cut(metrik, {bins})</code> im Notebook. Je Klasse: Anzahl Wetten (grau) und Profit mit 1 Einheit je Wette (grün/rot).
        Gesamt: Profit <b className={(data?.total.profit ?? 0) >= 0 ? "pos" : "neg"}>{signed(data?.total.profit, 1)}</b>, Rendite {pct(data?.total.roi)}.
        Klassen unter 5 Wetten sind blass – dort ist ein Plus meist Zufall.
        <br />Es erscheinen nur Werte, die <b>vor dem Spiel</b> feststehen: aus früheren Spielen (Spiele desselben Tages ausgeschlossen)
        sowie Quoten und Linien vor Anpfiff – nichts aus dem Ergebnis des Spiels selbst.
      </div>
      <div className="row" style={{ gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <label>Markt <select value={market} onChange={(e) => setMarket(e.target.value)}>
          {ORDER.filter((m) => m in markets).map((m) => <option key={m} value={m}>{markets[m]}{m === strategy.market ? " ★" : ""}</option>)}
        </select></label>
        <label>Klassen <select value={bins} onChange={(e) => setBins(Number(e.target.value))}>
          {[5, 8, 10, 15, 20].map((b) => <option key={b} value={b}>{b}</option>)}
        </select></label>
        <label>Einteilung <select value={mode} onChange={(e) => setMode(e.target.value as "width" | "count")}>
          <option value="width">gleich breit (wie pd.cut)</option>
          <option value="count">gleich viele Wetten (wie pd.qcut)</option>
        </select></label>
        <label>Sortieren <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="best">bester Profit einer Klasse</option>
          <option value="spread">größter Unterschied der Klassen</option>
          <option value="r">stärkster Zusammenhang (r)</option>
          <option value="name">Name</option>
        </select></label>
        <label>Metriken <select value={group} onChange={(e) => setGroup(e.target.value as Group)}>
          <option value="all">alle</option>
          <option value="fav">★ nur markierte</option>
          <option value="legacy">alte Notebook-Metriken</option>
          <option value="new">neue Metriken</option>
        </select></label>
        <label className="small"><input type="checkbox" checked={favFirst} onChange={(e) => setFavFirst(e.target.checked)} /> <span className="fav-star">★</span> markierte zuerst
          <span className="muted"> ({isTotalMarket(market) ? "Over/Under: Summe beider Teams und …_to_over" : "Sieger/Handicap: Unterschied der Teams"})</span></label>
        <label className="small"><input type="checkbox" checked={showAlt} onChange={(e) => setShowAlt(e.target.checked)} /> auch _alt (alte xG-Berechnung)</label>
        <input placeholder="Metrik suchen …" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 180 }} />
        <span style={{ flex: 1 }} />
        <button className="secondary" onClick={() => setOpen(new Set(shown.map((m) => m.name)))}>Alle aufklappen</button>
        <button className="secondary" onClick={() => setOpen(new Set())}>Alle zuklappen</button>
      </div>
      {error && <div className="error">{error}</div>}
      <div>
        {shown.map((m) => <MetricRow key={m.name} m={m} names={names} open={open.has(m.name)} onToggle={() => toggle(m.name)} onAdd={onAdd} rank={favoriteRank(m.name, market)} />)}
      </div>
      {list.length > limit && (
        <button className="secondary" style={{ marginTop: 8 }} onClick={() => setLimit(limit + 30)}>Weitere {Math.min(30, list.length - limit)} von {list.length - limit} zeigen</button>
      )}
      {data && list.length === 0 && <div className="muted small">Keine Metrik mit mindestens 10 Wetten.</div>}
      <div className="small muted" style={{ marginTop: 8 }}>
        „beste Klasse“ zählt nur Klassen mit mindestens 5 Wetten (bzw. 5 % aller Wetten). Wer viele Metriken durchsucht, findet immer
        irgendwo eine gute Klasse – prüfe eine übernommene Bedingung danach mit der Ampel (Lern- und Prüf-Saison).
      </div>
    </div>
  );
}
