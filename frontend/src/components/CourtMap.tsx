import { ZoneStat } from "../api";
import { fmt, ZONE_LABEL } from "../labels";

// Lage der Zonen auf einer halben Spielfeldhälfte (Tor oben), Koordinaten im viewBox 400×300
const POS: Record<string, [number, number]> = {
  wing_left: [32, 48],
  wing_right: [368, 48],
  line: [200, 78],
  close_left: [104, 118],
  close_center: [200, 138],
  close_right: [296, 118],
  long_left: [70, 215],
  long_center: [200, 240],
  long_right: [330, 215],
  "7m": [352, 270],
};

/** Wurfkarte: Kreisgröße = Würfe, Farbe = Tore im Vergleich zu xG (grün = besser als erwartet). */
export default function CourtMap({ zones }: { zones: Record<string, ZoneStat> }) {
  const max = Math.max(1, ...Object.values(zones).map((z) => z.shots));
  return (
    <div className="court">
      <svg viewBox="0 0 400 300" role="img" aria-label="Wurfkarte">
        <rect x="0" y="0" width="400" height="300" fill="var(--court)" rx="6" />
        {/* Tor, 6-m- und 9-m-Raum */}
        <rect x="170" y="0" width="60" height="8" fill="var(--court-line)" />
        <path d="M 60 0 Q 60 100 200 100 Q 340 100 340 0" fill="none" stroke="var(--court-line)" strokeWidth="2" />
        <path d="M 10 0 Q 10 170 200 170 Q 390 170 390 0" fill="none" stroke="var(--court-line)" strokeWidth="1.5" strokeDasharray="6 5" />
        <line x1="190" y1="120" x2="210" y2="120" stroke="var(--court-line)" strokeWidth="2" />
        {Object.entries(POS).map(([zone, [x, y]]) => {
          const z = zones[zone];
          if (!z || !z.shots) return null;
          const r = 9 + 22 * Math.sqrt(z.shots / max);
          const diff = z.goals - z.xg;
          const color = diff > 0.5 ? "var(--good)" : diff < -0.5 ? "var(--bad)" : "var(--accent)";
          return (
            <g key={zone}>
              <title>{`${ZONE_LABEL[zone]}: ${z.goals}/${z.shots} Tore, xG ${fmt(z.xg)}`}</title>
              <circle cx={x} cy={y} r={r} fill={color} fillOpacity="0.2" stroke={color} strokeWidth="2" />
              <text x={x} y={y - 1} textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--text)">
                {z.goals}/{z.shots}
              </text>
              <text x={x} y={y + 12} textAnchor="middle" fontSize="10" fill="var(--muted)">
                xG {fmt(z.xg)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
