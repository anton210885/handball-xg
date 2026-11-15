import { useMemo, useState } from "react";
import { RatePart, StrategyRateResult, StrategyRating } from "../api";
import { pct } from "../labels";

type Light = StrategyRating["light"];
const LIGHTS: { key: Light; label: string; color: string; icon: string; help: string }[] = [
  { key: "green", label: "Grün", color: "var(--good)", icon: "●", help: "Gewinn auf Lern- und Prüf-Saison und insgesamt sicher" },
  { key: "yellow", label: "Gelb", color: "var(--warn)", icon: "●", help: "Gewinn, aber noch nicht sicher oder Prüf-Saison zu kurz" },
  { key: "red", label: "Rot", color: "var(--bad)", icon: "●", help: "Kein Gewinn auf den Lern-Saisons oder Verlust auf der Prüf-Saison" },
  { key: "grey", label: "Grau", color: "var(--muted)", icon: "○", help: "Zu wenige Wetten für ein Urteil" },
];
const LIGHT = Object.fromEntries(LIGHTS.map(l => [l.key, l])) as Record<Light, typeof LIGHTS[number]>;

function Roi({ p, range = false }: { p: RatePart | null | undefined; range?: boolean }) {
  if (!p || !p.bets) return <td className="num muted">–</td>;
  const cls = p.roi === null ? "" : p.roi > 0 ? "pos" : "neg";
  return <td className="num" title={`${p.bets} Wetten · Trefferquote ${pct(p.hit_rate)} · Zufallsbereich ${pct(p.roi_low)} bis ${pct(p.roi_high)}`}>
    <span className={cls}>{pct(p.roi)}</span>
    <div className="small muted">{range && p.roi_low !== null ? `${pct(p.roi_low)} bis ${pct(p.roi_high)} · ` : ""}{p.bets} W.</div>
  </td>;
}

type Props = {
  data: StrategyRateResult; markets: Record<string, string>; onPick: (id: number) => void;
  testSeason: string | null; onTestSeason: (s: string) => void;
};

/** Alle Strategien mit Ampel: ausgesucht auf den Lern-Saisons, geprüft auf einer Saison, die dabei nicht mitzählt. */
export default function StrategyRatings({ data, markets, onPick, onTestSeason }: Props) {
  const [text, setText] = useState("");
  const [market, setMarket] = useState("");
  const [lights, setLights] = useState<Light[]>([]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of data.strategies) c[s.light] = (c[s.light] ?? 0) + 1;
    return c;
  }, [data]);
  const shown = data.strategies.filter(s =>
    (!lights.length || lights.includes(s.light)) && (!market || s.market === market) && (!text || s.name.toLowerCase().includes(text.toLowerCase())));
  const toggle = (l: Light) => setLights(lights.includes(l) ? lights.filter(x => x !== l) : [...lights, l]);
  const test = data.test_season;

  return <>
    <div className="row" style={{ marginBottom: 8 }}>
      {LIGHTS.map(l => <button key={l.key} className={lights.includes(l.key) ? "" : "secondary"} onClick={() => toggle(l.key)} title={l.help}>
        <span style={{ color: lights.includes(l.key) ? undefined : l.color }}>{l.icon}</span> {l.label} ({counts[l.key] ?? 0})</button>)}
      {lights.length > 0 && <button className="secondary" onClick={() => setLights([])}>alle</button>}
    </div>
    <div className="row" style={{ marginBottom: 8 }}>
      <input placeholder="Name filtern, z. B. over_ oder Women_" value={text} onChange={e => setText(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
      <select value={market} onChange={e => setMarket(e.target.value)}>
        <option value="">alle Märkte</option>
        {Object.entries(markets).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      {data.seasons.length > 1 && <label>Prüf-Saison <select value={test ?? ""} onChange={e => onTestSeason(e.target.value)}>
        {data.seasons.map(s => <option key={s} value={s}>{s}</option>)}</select></label>}
    </div>
    <div className="small muted" style={{ marginBottom: 8 }}>
      {test
        ? <>Ausgesucht wird auf den <b>Lern-Saisons</b> ({data.seasons.filter(s => s !== test).join(", ")}); die <b>Prüf-Saison {test}</b> zählt dabei nicht mit
          und zeigt, ob die Strategie auf neuen Spielen hält. </>
        : <>Für eine Prüf-Saison oben mindestens zwei Saisons mit Linien wählen. </>}
      Rendite mit Zufallsbereich (95 %): liegt der ganze Bereich über 0, ist der Gewinn kein Zufall mehr.
      Bei {data.strategies.length} Strategien sehen einige allein durch Glück gut aus – darum zählt Grün, nicht der höchste Profit.
      {" "}{shown.length} von {data.strategies.length} Strategien · Klick auf einen Namen lädt sie in den Baukasten.
    </div>
    <div className="table-wrap" style={{ maxHeight: 560, overflowY: "auto" }}>
      <table>
        <thead><tr>
          <th>Ampel · Strategie</th><th>Markt</th><th className="num" title="Anzahl Bedingungen – je mehr, desto eher nur an die Vergangenheit angepasst">Bed.</th>
          <th className="num">Rendite gesamt</th>
          {test && <><th className="num">Lern-Saisons</th><th className="num">Prüf-Saison {test}</th></>}
          <th className="num">offen</th>
        </tr></thead>
        <tbody>{shown.map(s => {
          const l = LIGHT[s.light];
          return <tr key={s.id}>
            <td title={s.light_reason} style={{ minWidth: 200 }}>
              <span style={{ color: l.color, fontSize: 16 }}>{l.icon}</span>{" "}
              <a href="#" onClick={e => { e.preventDefault(); onPick(s.id); }}>{s.name || `Strategie ${s.id}`}</a>
              <div className="small muted">{s.light_reason}</div>
              {s.error && <div className="small error">{s.error}</div>}</td>
            <td><span className="tag">{markets[s.market] ?? s.market}</span></td>
            <td className={`num ${(s.rules ?? 0) >= 5 ? "neg" : ""}`} title={(s.rules ?? 0) >= 5 ? "Viele Bedingungen: Gefahr, dass sie nur zur Vergangenheit passt" : undefined}>{s.rules ?? "–"}</td>
            <Roi p={s.total} range />
            {test && <><Roi p={s.train} /><Roi p={s.test} /></>}
            <td className="num">{s.open || ""}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  </>;
}
