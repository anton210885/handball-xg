/** Metriken aus dem alten Notebook, die besonders interessieren – werden in Listen farbig markiert.
 *
 * Je nach Markt zählen andere zuerst:
 *  - Sieger/Handicap (home, away, draw, hdp_*): Unterschied der beiden Teams (difference_…, powerRaiting_…, home/away…)
 *  - Over/Under: Summe beider Teams und Abstand zur Linie (…Sum…, …_to_over)
 */
/** Linien und Quoten vor Anpfiff – immer ganz oben, bei jedem Markt. */
export const LINE_METRICS = new Set(["over_line", "hdp_line", "odds_home", "odds_away", "odds_draw", "odds_over", "odds_under"]);

export const SIDE_METRICS = new Set([
  "difference_avgXG", "powerRaiting_avgXG", "powerRaiting_avgXGA", "powerRaiting_expGoals", "difference_expGoal",
  "homeExpGoal_with_GK", "awayExpGoal_with_GK", "powerRaiting_expGoals_with_GK", "difference_expGoals_with_GK",
  "homeExpGoal_with_GK_power", "awayExpGoal_with_GK_power", "powerRaiting_expGoals_with_GK_power", "difference_expGoals_with_GK_power",
  "last5_Games_powerRaiting_XG", "last5_Games_powerRaiting_XGA", "last5_Games_homeExpGoal_with_GK", "last5_Games_awayExpGoal_with_GK",
  "last5_Games_powerRaiting_expGoals_with_GK", "last5_Games_difference_expGoals_with_GK", "last5_Games_difference_XG",
]);

export const TOTAL_METRICS = new Set([
  "differenceSum_avgXG", "differenceSum_expGoal", "expSumGoal", "Sum_expGoal_with_GK", "Sum_expGoal_with_GK_power",
  "differenceSum_expGoal_to_over", "differenceSum_avgXG_to_over",
  "differenceSum_expGoals_with_GK_to_over", "differenceSum_expGoals_with_GK_power_to_over",
  "last5_Games_Sum_XG", "last5_Games_differenceSum_XG_to_over", "last5_Games_Sum_expGoal_with_GK",
  "last5_Games_differenceSum_expGoals_with_GK_to_over", "Sum_count", "Sum_count_minus1",
]);

/** Grundwerte aus dem Notebook – markiert, aber nach den marktspezifischen. */
const BASE_METRICS = new Set([
  "Home_avgXG", "Away_avgXG", "Home_avgXGA", "Away_avgXGA",
  "home_XGD", "away_XGD", "home_XGAD", "away_XGAD", "home_expGoal", "away_expGoal",
]);

export const FAVORITE_METRICS = new Set([...LINE_METRICS, ...SIDE_METRICS, ...TOTAL_METRICS, ...BASE_METRICS]);
export const isFavorite = (name: string) => FAVORITE_METRICS.has(name);

export const isTotalMarket = (market: string) => market === "over" || market === "under";

/** 0 = passt zum Markt (zuerst), 1 = andere Notebook-Metrik, 2 = Rest. */
export function favoriteRank(name: string, market: string): 0 | 1 | 2 {
  const own = isTotalMarket(market) ? TOTAL_METRICS : SIDE_METRICS;
  if (LINE_METRICS.has(name) || own.has(name)) return 0;
  return FAVORITE_METRICS.has(name) ? 1 : 2;
}
