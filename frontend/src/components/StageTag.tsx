import { Game } from "../api";

export const STAGE_TYPES: Record<string, string> = { league: "Hauptrunde", knockout: "KO-Spiel", placement: "Platzierungsrunde" };

// Filter nach Spielphase (für Spiele und Linien & Quoten)
export const STAGE_FILTER: Record<string, { label: string; test: (g: Game) => boolean }> = {
  "": { label: "alle Phasen", test: () => true },
  league: { label: "nur Hauptrunde", test: (g) => g.stage_type === "league" },
  knockout: { label: "nur KO-Spiele", test: (g) => g.stage_type === "knockout" },
  placement: { label: "nur Platzierungsrunde", test: (g) => g.stage_type === "placement" },
  unknown: { label: "Phase unbekannt", test: (g) => !g.stage_type },
};

// Kleines Etikett für alles außer der Hauptrunde; der genaue Phasenname steht im Tooltip
export default function StageTag({ game }: { game: Game }) {
  if (!game.stage_type || game.stage_type === "league") return null;
  return (
    <span className={`tag${game.stage_type === "knockout" ? " bad" : ""}`} title={game.stage ?? undefined} style={{ marginLeft: 6 }}>
      {game.stage_type === "knockout" ? "KO" : "Platzierung"}
    </span>
  );
}
