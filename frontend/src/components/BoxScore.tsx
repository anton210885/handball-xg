import type { Shot } from "../api";
import { fmt } from "../labels";

// Spalten wie in der koreahandball-Statistik; Russland (Zonen links/Mitte/rechts) wird darauf abgebildet
const CATS = [
  ["6m", "6 m"],
  ["wing", "Außen"],
  ["9m", "9 m"],
  ["7m", "7 m"],
  ["fb", "Gegenstoß"],
  ["bt", "Durchbruch"],
  ["eg", "Leeres Tor"],
] as const;
type Cat = (typeof CATS)[number][0];

function category(s: Shot): Cat | null {
  const z = s.court_zone ?? "";
  if (z === "7m") return "7m";
  if (z === "empty_goal") return "eg";
  // Gegenstoß zählt vor der Wurfposition, wie bei koreahandball
  if (z === "fastbreak" || (s.attack_type && s.attack_type !== "positional")) return "fb";
  if (z === "breakthrough") return "bt";
  if (z === "line" || z.startsWith("close_")) return "6m";
  if (z.startsWith("wing")) return "wing";
  if (z.startsWith("long")) return "9m";
  return null;
}

type Tally = { goals: number; shots: number; xg: number; cats: Record<string, [number, number]> };
const empty = (): Tally => ({ goals: 0, shots: 0, xg: 0, cats: {} });

function add(t: Tally, s: Shot, success: boolean) {
  t.shots += 1;
  t.goals += success ? 1 : 0;
  t.xg += s.xg ?? 0;
  const c = category(s);
  if (c) {
    const v = (t.cats[c] ??= [0, 0]);
    v[0] += success ? 1 : 0;
    v[1] += 1;
  }
}

function tallyBy(shots: Shot[], key: (s: Shot) => string | null, counted: (s: Shot) => boolean, success: (s: Shot) => boolean) {
  const rows = new Map<string, Tally>();
  const total = empty();
  for (const s of shots) {
    if (!counted(s)) continue;
    const k = key(s) ?? "ohne Namen";
    if (!rows.has(k)) rows.set(k, empty());
    add(rows.get(k)!, s, success(s));
    add(total, s, success(s));
  }
  return { rows: [...rows.entries()].sort((a, b) => b[1].goals - a[1].goals || b[1].shots - a[1].shots), total };
}

const ratio = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)} %` : "–");
const cell = (v?: [number, number]) => (v ? `${v[0]}/${v[1]}` : "");

function Table({ title, what, data, xg }: { title: string; what: string; data: ReturnType<typeof tallyBy>; xg: boolean }) {
  const row = (name: string, t: Tally, strong = false) => (
    <tr key={name} style={strong ? { fontWeight: 600 } : undefined}>
      <td>{name}</td>
      <td className="num">{t.goals}/{t.shots}</td>
      <td className="num">{ratio(t.goals, t.shots)}</td>
      {CATS.map(([c]) => <td key={c} className="num">{cell(t.cats[c])}</td>)}
      {xg && <td className="num">{fmt(t.xg)}</td>}
      {xg && <td className="num">{fmt(t.goals - t.xg)}</td>}
    </tr>
  );
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{title}</th>
            <th className="num">{what}</th>
            <th className="num">%</th>
            {CATS.map(([c, label]) => <th key={c} className="num">{label}</th>)}
            {xg && <th className="num" title="Erwartete Tore laut Modell">xG</th>}
            {xg && <th className="num" title="Tore minus xG">+/−</th>}
          </tr>
        </thead>
        <tbody>
          {data.rows.map(([name, t]) => row(name, t))}
          {row("Summe", data.total, true)}
        </tbody>
      </table>
    </div>
  );
}

/** Spieler- und Torhüterstatistik eines Teams, berechnet aus den einzelnen Würfen. */
export default function BoxScore({ shots, team, isHome }: { shots: Shot[]; team: string; isHome: boolean }) {
  const own = shots.filter((s) => s.is_home === isHome);
  // Torhüter dieses Teams: Würfe des Gegners aufs Tor (Tor oder Parade), bei denen er im Tor stand
  const faced = shots.filter((s) => s.is_home !== isHome && s.goalkeeper);
  const players = tallyBy(own, (s) => s.shooter, () => true, (s) => s.outcome === "goal");
  const keepers = tallyBy(faced, (s) => s.goalkeeper, (s) => s.outcome === "goal" || s.outcome === "save", (s) => s.outcome === "save");
  return (
    <div className="panel">
      <h2>{team}</h2>
      <Table title="Spieler" what="Tore/Würfe" data={players} xg />
      {keepers.rows.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Table title="Torhüter" what="Paraden/Würfe" data={keepers} xg={false} />
        </div>
      )}
    </div>
  );
}
