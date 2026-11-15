import { Rule } from "./api";

/** Namensvorschlag für eine Strategie: MARKT · WER · BEREICHE · KERNBEDINGUNG · Version
 *  z. B. „HOME · M · Q-H 1.11–1.30 · diffGKpow ≥ 2 · v1“. */

const MARKET: Record<string, string> = {
  home: "HOME", away: "AWAY", draw: "DRAW", over: "OVER", under: "UNDER", hdp_home: "HDP-H", hdp_away: "HDP-A",
};

const RANGE_SHORT: Record<string, string> = {
  home: "Q-H", away: "Q-A", over: "L", hdp: "HDP", home_games: "Sp-H", away_games: "Sp-A",
};
const RANGE_KEY: Record<string, string> = {
  over: "over", over_line: "over", home: "home", odds_home: "home", away: "away", odds_away: "away",
  hdp: "hdp", hdp_line: "hdp", home_games: "home_games", away_games: "away_games",
};
const RANGE_ORDER = ["home", "away", "over", "hdp", "home_games", "away_games"];
const RANGE_RULE = /^\s*(home_games|away_games|over_line|over|odds_home|home|odds_away|away|hdp_line|hdp)\s*(>=|>|<=|<)\s*(-?\d+(?:[.,]\d+)?)\s*$/;
const SEX_RULE = /^\s*sex\s*==\s*['"](men|women)['"]\s*$/;
const LEAGUE_RULE = /^\s*league\s*==\s*'[^']*'(\s+or\s+league\s*==\s*'[^']*')*\s*$/;
const STAGE_RULE = /^\s*tour\s*(<|==)\s*40\s*$/;

const COUNTRY: Record<string, string> = {
  Russland: "RUS", Russia: "RUS", Germany: "GER", Deutschland: "GER", Croatia: "CRO", Kroatien: "CRO",
  Romania: "ROU", Rumänien: "ROU", Korea: "KOR", International: "",
};

const formula = (r: Rule) => (r.formula !== undefined ? r.formula : `${r.feature} ${r.op} ${r.value}`);

/** Feste Kurzformen für die langen Metriknamen. */
export function shortMetric(name: string): string {
  return name
    .replace(/^last5_Games_/, "L5-")
    .replace(/^home(?=[A-Z_])_?/, "h").replace(/^away(?=[A-Z_])_?/, "a")
    .replace(/_?expGoals?_with_GK_power/i, "GKpow").replace(/_?expGoals?_with_GK/i, "GK")
    .replace(/^differenceSum_?/, "Sum").replace(/^difference_?/, "diff").replace(/^powerRaiting_?/, "PR")
    .replace(/^Sum_?/, "Sum").replace(/_to_over$/, "-over").replace(/_minus_line$/, "-L")
    .replace(/expGoal/, "xG").replace(/avgXG/, "xG");
}

function num(x: number, odds: boolean): string {
  const t = odds ? x.toFixed(2) : String(x);
  return t.replace("-", "−");
}

function leagueShort(label: string): string {
  const [country, ...rest] = label.split(" · ");
  const league = rest.join(" ") || country;
  const code = COUNTRY[country] ?? country.slice(0, 3).toUpperCase();
  if (!code) return league.replace("Champions League", "CL").replace("European League", "EL").replace(/\s+/g, "-");
  return `${code} ${league.replace(/\s+/g, "")}`;
}

function condition(text: string): string {
  const t = text.trim()
    .replace(/[A-Za-z_][A-Za-z0-9_]*/g, (n) => (n === "and" || n === "or" ? n : shortMetric(n)))
    .replace(/>=/g, "≥").replace(/<=/g, "≤").replace(/\s+/g, " ").replace(/\( /g, "(").replace(/ \)/g, ")");
  return t.length > 34 ? t.slice(0, 33) + "…" : t;
}

export function suggestName(market: string, rules: Rule[], existing: string[] = []): string {
  const parts: string[] = [MARKET[market] ?? market.toUpperCase()];

  // Wer: Geschlecht, Liga, Spielart
  let sex: string | undefined, leagues: string[] = [], stage: string | undefined;
  const bounds: Record<string, { from?: number; to?: number }> = {};
  const rest: string[] = [];
  for (const r of rules) {
    const f = formula(r);
    const sx = f.match(SEX_RULE);
    if (sx) { sex = sx[1]; continue; }
    if (LEAGUE_RULE.test(f)) { leagues = [...f.matchAll(/'([^']*)'/g)].map((m) => m[1]); continue; }
    const st = f.match(STAGE_RULE);
    if (st) { stage = st[1] === "<" ? "Meister" : "KO"; continue; }
    const rg = f.match(RANGE_RULE);
    if (rg) {
      const key = RANGE_KEY[rg[1]];
      const v = Number(rg[3].replace(",", "."));
      bounds[key] = { ...bounds[key], [rg[2].startsWith(">") ? "from" : "to"]: v };
      continue;
    }
    rest.push(f);
  }
  const who = [sex === "men" ? "M" : sex === "women" ? "W" : "alle"];
  if (leagues.length === 1 || leagues.length === 2) who.push(leagues.map(leagueShort).join("+"));
  else if (leagues.length > 2) who.push(`${leagues.length} Ligen`);
  parts.push(who.join(" "));

  for (const key of RANGE_ORDER) {
    const b = bounds[key];
    if (!b) continue;
    const odds = key === "home" || key === "away";
    const text = b.from !== undefined && b.to !== undefined ? `${num(b.from, odds)}–${num(b.to, odds)}`
      : b.from !== undefined ? `≥${num(b.from, odds)}` : `≤${num(b.to!, odds)}`;
    parts.push(`${RANGE_SHORT[key]} ${text}`);
  }
  if (stage) parts.push(stage);
  if (rest.length) parts.push(condition(rest[0]) + (rest.length > 1 ? ` +${rest.length - 1}` : ""));

  // Version: nächste freie Nummer für denselben Namen
  const base = parts.join(" · ");
  const used = existing
    .map((n) => n.match(/^(.*) · v(\d+)$/))
    .filter((m): m is RegExpMatchArray => !!m && m[1] === base)
    .map((m) => Number(m[2]));
  return `${base} · v${used.length ? Math.max(...used) + 1 : 1}`;
}
