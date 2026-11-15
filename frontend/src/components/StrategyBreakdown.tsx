import { useEffect, useState } from "react";
import { api, BreakdownResult, MarketCell, Strategy } from "../api";
import { fmt, pct } from "../labels";

const ORDER = ["home", "away", "draw", "over", "under", "hdp_home", "hdp_away"];
const SHORT: Record<string, string> = {
  home: "Home", away: "Away", draw: "Draw", over: "Over", under: "Under", hdp_home: "Handicap Heim", hdp_away: "Handicap Gast",
};
type Show = "profit" | "roi" | "hit";
type Range = [number, number];
type RangeName = "home" | "away" | "over" | "hdp";

/** Bereiche als Text: „35.5-40; 40.5-44.5“ (Komma oder Punkt als Dezimalzeichen). */
const rangesText = (r: Range[]) => r.map(([a, b]) => `${a} bis ${b}`.replace(/\./g, ",")).join("; ");
function parseRanges(text: string): Range[] | null {
  const parts = text.split(/[;\n]+/).map((x) => x.trim()).filter(Boolean);
  const out: Range[] = [];
  for (const p of parts) {
    const m = p.replace(/−/g, "-").match(/^(-?\d+(?:[.,]\d+)?)\s*(?:bis|–|-)\s*(-?\d+(?:[.,]\d+)?)$/);
    if (!m) return null;
    const a = Number(m[1].replace(",", ".")), b = Number(m[2].replace(",", "."));
    out.push([Math.min(a, b), Math.max(a, b)]);
  }
  return out.length ? out : null;
}

function Cell({ c, show, own }: { c?: MarketCell; show: Show; own: boolean }) {
  if (!c || c.bets === 0) return <td className="num muted">–</td>;
  const main = show === "profit" ? (c.profit > 0 ? "+" : "") + fmt(c.profit, 1) : show === "roi" ? pct(c.roi) : pct(c.hit_rate);
  const tone = c.bets < 10 ? "" : c.profit > 0 ? "pos" : c.profit < 0 ? "neg" : "";
  const title = `${c.bets} Wetten · ${c.wins} gewonnen${c.pushes ? ` · ${c.pushes} zurück` : ""}\n` +
    `Profit ${fmt(c.profit, 2)} · Rendite ${pct(c.roi)} · Trefferquote ${pct(c.hit_rate)} · Ø Quote ${fmt(c.avg_odds, 2)}` +
    (c.roi_low !== null && c.roi_high !== null ? `\nRendite 95 %: ${pct(c.roi_low)} bis ${pct(c.roi_high)}` : "");
  return (
    <td className={`num ${tone}`} title={title} style={own ? { background: "var(--accent-soft, rgba(80,120,255,.08))" } : undefined}>
      <b>{main}</b>
      <div className="small muted">{c.bets} W · {show === "hit" ? pct(c.roi) : pct(c.hit_rate)}</div>
    </td>
  );
}

/** Spiele der Strategie nach Over-Linie und Quoten aufgeteilt – Ergebnis für alle sieben Märkte. */
export default function StrategyBreakdown({ strategy, compIds, excludeErrors, lineRanges = [], oddsRanges = [], hdpRanges = [], onApply }: {
  strategy: Strategy; compIds: number[]; excludeErrors: boolean;
  lineRanges?: Range[]; oddsRanges?: Range[]; hdpRanges?: Range[]; onApply?: (name: RangeName, low: number, high: number) => void;
}) {
  const [lineText, setLineText] = useState(() => rangesText(lineRanges));
  const [oddsText, setOddsText] = useState(() => rangesText(oddsRanges));
  const [hdpText, setHdpText] = useState(() => rangesText(hdpRanges));
  const [tab, setTab] = useState(0);
  const [show, setShow] = useState<Show>("profit");
  const [data, setData] = useState<BreakdownResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const line = parseRanges(lineText), odds = parseRanges(oddsText), hdp = parseRanges(hdpText);
    if (!line || !odds || !hdp) { setError("Bereiche bitte als „von bis bis“ mit Strichpunkt getrennt, z. B. 35,5 bis 40; 40,5 bis 44,5"); return; }
    setError(null); setBusy(true);
    try { setData(await api.strategyBreakdown(strategy, compIds, excludeErrors, line, odds, hdp)); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); }, [strategy, compIds.join(","), excludeErrors]);

  const table = data?.tables[tab];
  const markets = ORDER.filter((m) => !data || m in data.markets);
  const showLabel = show === "profit" ? "Profit (1 Einheit je Wette)" : show === "roi" ? "Rendite" : "Trefferquote";

  return (
    <div className="panel table-wrap">
      <h2>Aufteilung nach Linie und Quote – alle Märkte</h2>
      <div className="small muted" style={{ marginBottom: 8 }}>
        Dieselben {data?.games ?? "…"} beendeten Spiele, auf die deine Strategie passt – für jeden Markt abgerechnet, als hättest du dort gesetzt
        (1 Einheit je Wette). Die Spalte deines Marktes ist hinterlegt. Handicap rechnet mit Quote 1,80 (Handicap-Quoten sind nicht gespeichert);
        Over/Under ohne eingetragene Quote ebenfalls mit 1,80. Unter 10 Wetten ohne Farbe. Maus über eine Zelle zeigt alle Zahlen.
      </div>
      <div className="row" style={{ gap: 12, flexWrap: "wrap", alignItems: "end", marginBottom: 10 }}>
        <label className="small" style={{ flex: "1 1 320px" }}>Bereiche Over-Linie (von-bis; …)<br />
          <input value={lineText} onChange={(e) => setLineText(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label className="small" style={{ flex: "1 1 320px" }}>Bereiche Quote Home und Away<br />
          <input value={oddsText} onChange={(e) => setOddsText(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label className="small" style={{ flex: "1 1 320px" }}>Bereiche Handicap-Linie (Heim)<br />
          <input value={hdpText} onChange={(e) => setHdpText(e.target.value)} style={{ width: "100%" }} />
        </label>
        <button className="secondary" onClick={load} disabled={busy}>{busy ? "Rechne …" : "Neu aufteilen"}</button>
        <button className="secondary" title="Vordefinierte Bereiche wiederherstellen"
          onClick={() => { setLineText(rangesText(lineRanges)); setOddsText(rangesText(oddsRanges)); setHdpText(rangesText(hdpRanges)); }}>Standard</button>
      </div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        <span style={{ flex: 1 }} />
        {(["profit", "roi", "hit"] as Show[]).map((k) => (
          <button key={k} className={show === k ? "" : "secondary"} onClick={() => setShow(k)}>
            {k === "profit" ? "Profit" : k === "roi" ? "Rendite" : "Trefferquote"}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 10 }}>
        {(data?.tables ?? []).map((t, i) => (
          <button key={t.key} className={tab === i ? "" : "secondary"} onClick={() => setTab(i)}>{t.title}</button>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      {table && data && (
        <table>
          <thead>
            <tr>
              <th>{({ over_line: "Over-Linie", odds_home: "Quote Home", odds_away: "Quote Away", hdp_line: "Handicap-Linie" } as Record<string, string>)[table.key] ?? table.key}</th>
              <th className="num">Spiele</th>
              {onApply && <th></th>}
              {markets.map((m) => (
                <th key={m} className="num" title={data.markets[m]}>{SHORT[m] ?? m}{m === strategy.market ? " ★" : ""}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r) => (
              <tr key={r.label} className={r.games === 0 ? "muted" : ""}>
                <td>{r.label}</td>
                <td className="num">{r.games}</td>
                {onApply && (
                  <td>
                    {r.low !== null && r.high !== null && (
                      <button className="secondary small" style={{ padding: "2px 8px" }}
                        title={`Diesen Bereich als Filter in die Strategie übernehmen (${table.title.replace("Nach ", "")} ${r.label}); danach Backtest neu starten`}
                        onClick={() => onApply(table.name as RangeName, r.low!, r.high!)}>übernehmen</button>
                    )}
                  </td>
                )}
                {markets.map((m) => <Cell key={m} c={r.markets[m]} show={show} own={m === strategy.market} />)}
              </tr>
            ))}
            <tr style={{ borderTop: "2px solid var(--border, #ccc)" }}>
              <td><b>Gesamt</b></td>
              <td className="num"><b>{data.games}</b></td>
              {onApply && <td></td>}
              {markets.map((m) => <Cell key={m} c={data.total[m]} show={show} own={m === strategy.market} />)}
            </tr>
          </tbody>
        </table>
      )}
      <div className="small muted" style={{ marginTop: 6 }}>
        Gezeigt: <b>{showLabel}</b>, darunter Wetten (W) und {show === "hit" ? "Rendite" : "Trefferquote"}. Bereiche schließen beide Grenzen ein; Spiele zwischen den Bereichen stehen unter „außerhalb der Bereiche“.
        „übernehmen“ setzt den Bereich oben bei der Strategie als Filter.
      </div>
    </div>
  );
}
