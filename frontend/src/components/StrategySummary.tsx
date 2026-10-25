import { useMemo, useState } from "react";
import { StrategySummary as Row } from "../api";
import { fmt, pct } from "../labels";

type SortKey = "name" | "bets" | "hit_rate" | "profit" | "roi" | "open";

/** Tabelle: alle Strategien mit Backtest-Ergebnis, filter- und sortierbar. */
export default function StrategySummary({
  rows,
  markets,
  onPick,
}: {
  rows: Row[];
  markets: Record<string, string>;
  onPick: (id: number) => void;
}) {
  const [text, setText] = useState("");
  const [minBets, setMinBets] = useState(0);
  const [market, setMarket] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "profit", desc: true });

  const shown = useMemo(() => {
    const t = text.toLowerCase();
    const list = rows.filter(
      (r) => (r.bets ?? 0) >= minBets && (!market || r.market === market) && (!t || r.name.toLowerCase().includes(t)),
    );
    const val = (r: Row) => (sort.key === "name" ? r.name : (r[sort.key] as number | null | undefined) ?? -Infinity);
    return list.sort((a, b) => {
      const x = val(a), y = val(b);
      const c = x < y ? -1 : x > y ? 1 : 0;
      return sort.desc ? -c : c;
    });
  }, [rows, text, minBets, market, sort]);

  const head = (key: SortKey, label: string, num = true) => (
    <th
      className={num ? "num" : ""}
      style={{ cursor: "pointer" }}
      onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : key !== "name" })}
    >
      {label} {sort.key === key ? (sort.desc ? "▼" : "▲") : ""}
    </th>
  );

  const total = shown.reduce((a, r) => a + (r.bets ?? 0), 0);
  const errors = rows.filter((r) => r.error);

  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <input placeholder="Name filtern, z. B. over_ oder Men_" value={text} onChange={(e) => setText(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">alle Märkte</option>
          {Object.entries(markets).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <label className="small muted">min. Wetten</label>
        <input className="cell" type="number" value={minBets} onChange={(e) => setMinBets(Number(e.target.value))} />
      </div>
      <div className="small muted" style={{ marginBottom: 6 }}>
        {shown.length} von {rows.length} Strategien · {total} Wetten · Klick auf einen Namen lädt die Strategie oben in den Baukasten
      </div>
      {errors.length > 0 && <div className="error small">{errors.map((e) => `${e.name}: ${e.error}`).join(" · ")}</div>}
      <div className="table-wrap" style={{ maxHeight: 520, overflowY: "auto" }}>
        <table>
          <thead>
            <tr>
              {head("name", "Strategie", false)}
              <th>Markt</th>
              {head("bets", "Wetten")}
              {head("hit_rate", "Treffer")}
              <th className="num">Einsatz / Wette</th>
              <th className="num">Ø Quote</th>
              {head("profit", "Profit")}
              {head("roi", "Rendite")}
              {head("open", "offen")}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="click" onClick={() => onPick(r.id)}>
                <td><a href="#" onClick={(e) => e.preventDefault()}>{r.name}</a></td>
                <td><span className="tag">{markets[r.market] ?? r.market}</span></td>
                <td className="num">{r.bets}</td>
                <td className="num">{pct(r.hit_rate)}</td>
                <td className="num">{fmt(r.stake ?? 1, 2)}</td>
                <td className="num">{fmt(r.avg_odds, 2)}</td>
                <td className={`num ${(r.profit ?? 0) >= 0 ? "pos" : "neg"}`}>{fmt(r.profit, 2)}</td>
                <td className={`num ${(r.roi ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(r.roi)}</td>
                <td className="num">{r.open || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
