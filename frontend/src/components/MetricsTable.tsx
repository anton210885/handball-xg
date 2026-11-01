import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Game } from "../api";
import { dateTime, fmt } from "../labels";

type Col = { key: string; label: string; title?: string; value: (g: Game) => number | string | null | undefined; text?: (g: Game) => string };

const total = (g: Game) => (g.home_score !== null && g.away_score !== null ? g.home_score + g.away_score : null);

const BASE: Col[] = [
  { key: "start", label: "Datum (MSK)", value: (g) => g.start, text: (g) => dateTime(g.start) },
  { key: "home", label: "Heim", value: (g) => g.home.name },
  { key: "away", label: "Gast", value: (g) => g.away.name },
  { key: "result", label: "Ergebnis", title: "Sortiert nach Tordifferenz", value: (g) => (g.home_score ?? 0) - (g.away_score ?? 0), text: (g) => `${g.home_score}:${g.away_score}` },
  { key: "total", label: "Tore ges.", value: total },
  { key: "home_xg", label: "xG Heim", value: (g) => g.home_xg },
  { key: "away_xg", label: "xG Gast", value: (g) => g.away_xg },
];

/** Alle beendeten Spiele mit sämtlichen Metriken vor Anpfiff; Klick auf eine Spalte sortiert. */
export default function MetricsTable({ games, labels }: { games: Game[]; labels: Record<string, string> }) {
  const nav = useNavigate();
  const [sort, setSort] = useState<{ key: string; desc: boolean }>({ key: "start", desc: true });
  const cols = useMemo<Col[]>(
    () => [...BASE, ...Object.entries(labels).map(([k, label]) => ({ key: k, label: k, title: label, value: (g: Game) => g.features?.[k] }))],
    [labels],
  );
  const rows = useMemo(() => {
    const col = cols.find((c) => c.key === sort.key) ?? cols[0];
    return [...games].sort((a, b) => {
      const x = col.value(a), y = col.value(b);
      // Fehlende Werte immer ans Ende
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      const d = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return sort.desc ? -d : d;
    });
  }, [games, cols, sort]);

  return (
    <div className="table-wrap" style={{ maxHeight: "75vh" }}>
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={c.key === "home" || c.key === "away" ? "" : "num"} title={c.title} style={{ cursor: "pointer" }}
                onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))}>
                {c.label}
                {sort.key === c.key ? (sort.desc ? " ▼" : " ▲") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.id} className="click" onClick={() => nav(`/spiele/${g.id}`)}>
              {cols.map((c) => {
                const v = c.value(g);
                return (
                  <td key={c.key} className={c.key === "home" || c.key === "away" ? "" : "num"}>
                    {c.text ? c.text(g) : typeof v === "number" ? fmt(v, Number.isInteger(v) ? 0 : 2) : v ?? "–"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
