export const ZONE_LABEL: Record<string, string> = {
  wing_left: "Außen links",
  wing_right: "Außen rechts",
  line: "Kreis (6 m)",
  close_left: "Nah links",
  close_center: "Nah Mitte",
  close_right: "Nah rechts",
  long_left: "Rückraum links",
  long_center: "Rückraum Mitte",
  long_right: "Rückraum rechts",
  "7m": "7 m",
  // Zonen der koreanischen Liga (ohne links/rechts)
  wing: "Außen",
  long: "Rückraum (9 m)",
  breakthrough: "Durchbruch",
  fastbreak: "Gegenstoß",
  empty_goal: "Leeres Tor",
};

export const GOAL_ZONES = [
  ["top_left", "top_center", "top_right"],
  ["mid_left", "mid_center", "mid_right"],
  ["low_left", "low_center", "low_right"],
];

export const OUTCOME_LABEL: Record<string, string> = {
  goal: "Tor",
  save: "Parade",
  miss: "Vorbei",
  missed: "Fehlwurf", // HBL: gehalten oder vorbei, die Quelle unterscheidet das nicht
  post: "Pfosten",
  block: "Block",
  error: "Fehler",
};

export const ATTACK_LABEL: Record<string, string> = {
  positional: "Positionsangriff",
  transition: "Umschalten",
  fastbreak: "Gegenstoß",
  breakaway: "Durchbruch 1:1",
  fast_center: "Schnelle Mitte",
};

export const fmt = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(digits);

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(0)} %`);

export const dateTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};
