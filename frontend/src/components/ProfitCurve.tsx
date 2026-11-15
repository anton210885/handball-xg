import { useMemo, useState } from "react";
import { fmt } from "../labels";

export type CurvePoint = { y: number; label: string; detail?: string };

/** Summierter Profit über die Wetten (eine Linie, Nulllinie, Tooltip beim Überfahren). */
export default function ProfitCurve({ points, height = 220 }: { points: CurvePoint[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720, H = height, L = 46, R = 12, T = 12, B = 26;
  const geo = useMemo(() => {
    const ys = [0, ...points.map((p) => p.y)];
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    const n = points.length;
    const x = (i: number) => L + (n <= 1 ? (W - L - R) / 2 : (i / (n - 1)) * (W - L - R));
    const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const step = niceStep((hi - lo) / 4);
    const ticks: number[] = [];
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(Math.round(t * 1e6) / 1e6);
    return { x, y, ticks };
  }, [points, H]);

  if (!points.length) return <div className="small muted">Noch keine abgerechneten Wetten.</div>;
  const { x, y, ticks } = geo;
  const path = [`M${x(0)},${y(0)}`, ...points.map((p, i) => `L${x(i)},${y(p.y)}`)].join(" ");
  // Startpunkt bei 0 vor der ersten Wette
  const xs = [x(0), ...points.map((_, i) => x(i))];
  const last = points[points.length - 1].y;
  const h = hover !== null ? points[hover] : null;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    let best = 0;
    for (let i = 0; i < points.length; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
    setHover(best);
  };

  return (
    <div className="curve-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="curve" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img"
        aria-label={`Summierter Profit, ${points.length} Wetten, zuletzt ${fmt(last, 2)}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className={t === 0 ? "curve-zero" : "curve-grid"} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="curve-axis">{fmt(t, Math.abs(step(ticks)) < 1 ? 1 : 0)}</text>
          </g>
        ))}
        <path d={path} className={last >= 0 ? "curve-line pos" : "curve-line neg"} />
        {xs.length > 1 && <text x={x(points.length - 1)} y={y(last) - 8} textAnchor="end" className="curve-label">{fmt(last, 2)}</text>}
        <text x={L} y={H - 6} className="curve-axis">{points[0].label}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="curve-axis">{points[points.length - 1].label}</text>
        {h && hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="curve-cross" />
            <circle cx={x(hover)} cy={y(h.y)} r={4.5} className={h.y >= 0 ? "curve-dot pos" : "curve-dot neg"} />
          </g>
        )}
      </svg>
      {h && hover !== null && (
        <div className="curve-tip" style={{
          left: `${(x(hover) / W) * 100}%`,
          // rechte Hälfte: Tooltip links vom Punkt, sonst rechts davon – bleibt im Bild
          transform: x(hover) > W / 2 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
        }}>
          <b>{fmt(h.y, 2)}</b> nach Wette {hover + 1}<br />
          <span className="muted">{h.label}</span>{h.detail && <><br />{h.detail}</>}
        </div>
      )}
    </div>
  );
}

function niceStep(raw: number) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}
const step = (t: number[]) => (t.length > 1 ? t[1] - t[0] : 1);

/** Kleine Verlaufslinie für Tabellen. */
export function Sparkline({ values, width = 90, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="muted small">–</span>;
  const ys = [0, ...values];
  const lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
  const pts = ys.map((v, i) => `${(i / (ys.length - 1)) * width},${height - 2 - ((v - lo) / span) * (height - 4)}`).join(" ");
  const zero = height - 2 - ((0 - lo) / span) * (height - 4);
  return (
    <svg width={width} height={height} className="spark" aria-hidden>
      <line x1={0} x2={width} y1={zero} y2={zero} className="curve-zero" />
      <polyline points={pts} className={values[values.length - 1] >= 0 ? "curve-line pos" : "curve-line neg"} />
    </svg>
  );
}
