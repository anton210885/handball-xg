import { useState } from "react";
import type { GoalPredictor } from "../api";
import { fmt } from "../labels";

/** Streudiagramm Vorhersage (x) gegen Ergebnis (y) mit Diagonale (perfekte Vorhersage) und Ausgleichsgerade. */
export default function Scatter({ points, p, xLabel, yLabel }: { points: [number, number][]; p: GoalPredictor; xLabel: string; yLabel: string }) {
  const [hover, setHover] = useState<{ x: number; y: number; n: number } | null>(null);
  if (!points.length) return <div className="muted small">Keine Punkte.</div>;
  const W = 560, H = 380, L = 48, R = 12, T = 12, B = 40;
  const xs = points.map(q => q[0]), ys = points.map(q => q[1]);
  const lo = Math.floor(Math.min(...xs, ...ys)), hi = Math.ceil(Math.max(...xs, ...ys));
  const sx = (v: number) => L + (v - lo) / (hi - lo || 1) * (W - L - R);
  const sy = (v: number) => H - B - (v - lo) / (hi - lo || 1) * (H - T - B);
  const step = Math.max(1, Math.round((hi - lo) / 8));
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(v);
  // Gleiche Punkte (ganze Tore) zusammenfassen: Größe zeigt die Anzahl
  const counts = new Map<string, { x: number; y: number; n: number }>();
  for (const [x, y] of points) {
    const k = `${Math.round(x * 2) / 2}|${y}`;
    const c = counts.get(k) ?? { x: Math.round(x * 2) / 2, y, n: 0 };
    c.n += 1; counts.set(k, c);
  }
  const max = Math.max(...[...counts.values()].map(c => c.n));
  return <div style={{ position: "relative" }}>
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: W, display: "block" }} role="img" aria-label={`${yLabel} gegen ${xLabel}`}
      onMouseLeave={() => setHover(null)}>
      {ticks.map(t => <g key={t}>
        <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="var(--border)" />
        <text x={L - 6} y={sy(t) + 4} fontSize="11" textAnchor="end" fill="var(--muted)">{t}</text>
        <text x={sx(t)} y={H - B + 16} fontSize="11" textAnchor="middle" fill="var(--muted)">{t}</text>
      </g>)}
      <line x1={sx(lo)} y1={sy(lo)} x2={sx(hi)} y2={sy(hi)} stroke="var(--muted)" strokeDasharray="4 4" />
      {[...counts.values()].map(c => <circle key={`${c.x}|${c.y}`} cx={sx(c.x)} cy={sy(c.y)} r={2.5 + 4 * Math.sqrt(c.n / max)}
        fill="var(--accent)" fillOpacity={0.35} stroke="var(--panel)" strokeWidth={1}
        onMouseEnter={() => setHover(c)} />)}
      {p.slope != null && p.intercept != null && <line x1={sx(lo)} y1={sy(p.intercept + p.slope * lo)} x2={sx(hi)} y2={sy(p.intercept + p.slope * hi)}
        stroke="var(--accent)" strokeWidth={2} />}
      <text x={(L + W - R) / 2} y={H - 6} fontSize="12" textAnchor="middle" fill="var(--text)">{xLabel}</text>
      <text x={14} y={(T + H - B) / 2} fontSize="12" textAnchor="middle" fill="var(--text)" transform={`rotate(-90 14 ${(T + H - B) / 2})`}>{yLabel}</text>
    </svg>
    {hover && <div className="small" style={{ position: "absolute", left: `${sx(hover.x) / W * 100}%`, top: sy(hover.y) - 34, transform: "translateX(-50%)",
      background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 6, padding: "2px 8px", pointerEvents: "none", whiteSpace: "nowrap" }}>
      Vorhersage ≈ {fmt(hover.x, 1)} · Ergebnis {hover.y} · {hover.n} {hover.n === 1 ? "Spiel" : "Spiele"}
    </div>}
    <div className="small muted">Gestrichelt: perfekte Vorhersage (Ergebnis = Vorhersage). Durchgezogen: Ausgleichsgerade. Größere Punkte = mehr Spiele.</div>
  </div>;
}
