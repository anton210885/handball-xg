import type { Competition, MetricAnalysis } from "./api";

export function leagueName(c: Competition): string {
  if (c.league) return `${c.country ?? ""} · ${c.league}`.replace(/^ · /, "");
  // Stage and gender belong to the competition, not the league identity.
  const name = c.name.split(/\s[–—]\s/)[0]
    .replace(/\b(Männer|Frauen|men|women)\b/gi, "")
    .replace(/\b\d{2}(?:\d{2})?[/-]\d{2}(?:\d{2})?\b/g, "")
    .replace(/\s+/g, " ").trim();
  return name === "Суперлига" ? "Russland · Superliga" : name;
}

export function analysisCompetitions(competitions: Competition[], gender: string, league: string): Competition[] {
  return competitions.filter(c => (c.with_stats ?? c.with_shots) > 0 && (gender === "all" || c.gender === gender) && (league === "all" || leagueName(c) === league));
}

export function correlationDescending(metrics: MetricAnalysis[]): MetricAnalysis[] {
  return [...metrics].sort((a,b) => (b.correlation ?? -Infinity) - (a.correlation ?? -Infinity));
}
