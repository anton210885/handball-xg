import { Shot } from "../api";
import { GOAL_ZONES } from "../labels";

/** Torzonen 3×3: Anteil Tore an allen aufs Tor gehenden Würfen je Feld. */
export default function GoalMap({ shots }: { shots: Shot[] }) {
  const onTarget = shots.filter((s) => s.goal_zone && (s.outcome === "goal" || s.outcome === "save"));
  const count = (zone: string, outcome?: string) =>
    onTarget.filter((s) => s.goal_zone === zone && (!outcome || s.outcome === outcome)).length;
  const max = Math.max(1, ...GOAL_ZONES.flat().map((z) => count(z)));
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 3, maxWidth: 260, border: "4px solid var(--court-line)", borderBottom: 0, padding: 3 }}>
        {GOAL_ZONES.flat().map((z) => {
          const n = count(z);
          const g = count(z, "goal");
          return (
            <div
              key={z}
              title={`${g} Tore / ${n} Würfe aufs Tor`}
              style={{
                aspectRatio: "1.5",
                borderRadius: 4,
                background: `color-mix(in srgb, var(--accent) ${Math.round((n / max) * 70)}%, var(--bg))`,
                display: "grid",
                placeItems: "center",
                fontWeight: 600,
              }}
            >
              {n ? `${g}/${n}` : "–"}
            </div>
          );
        })}
      </div>
      <div className="small muted" style={{ marginTop: 6 }}>
        Tore / Würfe aufs Tor je Torzone
      </div>
    </div>
  );
}
