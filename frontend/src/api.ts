// Dünne Hülle um die REST-API des Python-Backends

export type Line = {
  over_line: number | null;
  hdp_line: number | null;
  odds_home: number | null;
  odds_draw: number | null;
  odds_away: number | null;
  odds_over: number | null;
  odds_under: number | null;
  source?: string;
  updated_at?: string | null;
};

export type Game = {
  id: number;
  competition_id: number;
  start: string;
  finished: boolean;
  shots_imported: boolean;
  stats_imported?: boolean;
  data_level?: string;
  source?: string;
  stage?: string | null;
  stage_type?: "league" | "knockout" | "placement" | null;
  home: { id: number; name: string };
  away: { id: number; name: string };
  home_score: number | null;
  away_score: number | null;
  home_ht: number | null;
  away_ht: number | null;
  home_xg?: number | null;
  away_xg?: number | null;
  url: string;
  line: Line | null;
  features?: Record<string, number | null>;
};

export type Shot = {
  id: number;
  is_home: boolean;
  minute: number;
  outcome: string;
  shooter: string | null;
  goalkeeper: string | null;
  court_zone: string | null;
  goal_zone: string | null;
  attack_type: string | null;
  majority: boolean;
  minority: boolean;
  jump: boolean | null;
  assisted: boolean;
  xg: number | null;
};

export type ZoneStat = { shots: number; goals: number; xg: number };
export type AggregateStats = { is_home: boolean; shots: number | null; goals: number | null; source: string; flags: string[]; categories: Record<string, any> };
export type GameDetail = Game & { aggregate_stats?: AggregateStats[]; shots: Shot[]; zones: { home: Record<string, ZoneStat>; away: Record<string, ZoneStat> } };

export type GoalTable = {
  target: string; target_label: string; formula: string; bookmaker_label: string; excluded_errors: number;
  games: { id: number; start: string; competition: string; season: string; home: string; away: string; score: string; played: number;
    actual: number; metric: number | null; bookmaker: number | null }[];
  stats_metric: GoalPredictor; stats_bookmaker: GoalPredictor; metric_same_games: GoalPredictor; bookmaker_same_games: GoalPredictor;
  min_games: number;
  by_min_games: { min_games: number; stats_metric: GoalPredictor; stats_bookmaker: GoalPredictor; metric_same_games: GoalPredictor; bookmaker_same_games: GoalPredictor }[];
};
export type MetricCompareResult = {
  target: string; target_label: string; min_games: number; columns: string[]; formulas: string[]; bookmaker_index: number;
  rows: { label: string; kind: string; games: number; cells: { r: number | null; mae: number | null; bias: number | null; r_low?: number | null; r_high?: number | null;
    z_vs_line?: number | null; p_vs_line?: number | null; beats_line_sure?: boolean }[] }[];
};
export type MetricVsLine = {
  games: number; r: number | null; r_line: number | null; z_vs_line: number | null; p_vs_line: number | null; beats_line_sure: boolean;
  added: number | null; added_p: number | null; added_sure: boolean; added_games: number;
};
export type MetricRank = MetricVsLine & {
  name: string; label: string; games_all: number; r_all: number | null; by_min_games?: (MetricVsLine & { min_games: number })[];
  by_league?: (MetricVsLine & { league: string })[];
  added_train?: number | null; added_train_sure?: boolean; added_train_games?: number;
  added_test?: number | null; added_test_p?: number | null; added_test_games?: number; holds?: boolean;
};
export type MetricRankResult = {
  target: string; target_label: string; bookmaker_label: string; min_games: number; thresholds: number[]; games: number; metrics: MetricRank[];
  group: string; leagues: string[]; groups: { label: string; games: number }[]; seasons: string[]; test_season: string | null;
};
export type CustomPredictor = { target: string; name: string; formula: string };
export type GoalPredictor = {
  key: string; label: string; custom?: boolean; games: number; r?: number | null; r2?: number | null; mae?: number; bias?: number;
  slope?: number | null; intercept?: number | null; mean_pred?: number; mean_actual?: number;
  games_with_bookmaker?: number; r_vs_bookmaker?: number | null; mae_same_games?: number | null; mae_bookmaker_same_games?: number | null;
};
export type GoalCorrelation = {
  games: number; excluded_errors: number;
  targets: { key: string; label: string; predictors: GoalPredictor[] }[];
  scatter: { target: string; key: string; points: [number, number][] } | null;
};

export type Competition = {
  id: number;
  name: string;
  season: string;
  gender: string;
  handballapi_tournament_id: number | null;
  handballapi_season_id: number | null;
  previous_competition_id: number | null;
  last_import: string | null;
  games: number;
  finished: number;
  with_shots: number;
  with_stats?: number;
  source?: string;
  country?: string | null;
  league?: string | null;
};

// Entweder Merkmal + Vergleich + Wert, oder eine Formel wie "(home_expGoal + away_expGoal) + 2 > over"
export type Coverage = {
  id: number;
  country: string | null;
  league: string | null;
  gender: string;
  season: string;
  finished: number;
  open: number;
  finished_no_line: number;
  finished_no_1x2: number;
  finished_no_hdp: number;
  open_no_line: number;
  open_no_1x2: number;
  open_no_hdp: number;
  finished_shots: number; // beendet, jeder Wurf gespeichert
  finished_stats_only: number; // beendet, nur Wurfzahlen je Spieler und Zone
  finished_no_xg: number; // beendet, nur Ergebnis
};

export type PasteResult = {
  lines: { line: number; a: number; b: number; count: number }[];
  handicaps: { line: number; a: number; b: number; count: number }[];
  warnings: string[];
  found: Partial<Record<"over_line" | "odds_over" | "odds_under" | "hdp_line" | "odds_home" | "odds_draw" | "odds_away", number>>;
  saved: boolean;
};

export type OddsportalResult = {
  home: string | null;
  away: string | null;
  league: string | null;
  market: string | null; // z. B. "1X2+O/U+AH"
  period: string;
  kickoff_local: string | null;
  score: [number, number] | null;
  found: Partial<Record<keyof Line, number>>;
  lines: { line: number; a: number; b: number; count: number }[];
  handicaps: { line: number; a: number; b: number; count: number }[];
  warnings: string[];
  candidates: (Game & { competition: string; match_score: number; reasons: string[] })[];
  game: (Game & { competition: string }) | null;
  saved: boolean;
  remaining: { finished: number; line: number; hdp: number; x12: number } | null; // beendete Spiele ohne Quoten
};
export type OddsportalPage = {
  text?: string;
  url?: string;
  pages?: { url: string; text: string; missing?: string }[];
  title: string;
  tz_offset: number;
};

export type Rule = { feature?: string; op?: string; value?: number; formula?: string };
export type Strategy = { id?: number; name: string; market: string; rules: Rule[]; min_games: number; notes?: string | null; min_odds?: number | null; max_odds?: number | null; stake?: number; archived?: boolean };
export type MetricDetails = { label: string; description: string; formula: string; source: string; timing: string };
export type AuditExample = { game_id: number; start: string; side: string; team: string; game: string; metric: string; value: number | string | null; expected: number | string | null };
export type AuditCheck = { key: string; label: string; description: string; checked: number; failed: number; examples: AuditExample[] };
export type MetricAudit = { games: number; prior_weight: number; checks: AuditCheck[] };
export type TeamHistoryRow = {
  game_id: number; start: string; home: boolean; opponent: string; finished: boolean;
  goals: number | null; goals_against: number | null; xg: number | null; xga: number | null;
  stored: Record<string, number | null>; expected: Record<string, number | null>; mismatch: string[];
};
export type TeamHistory = { competition: string; season: string; team: string; prior_weight: number; previous_competition: string | null; games: TeamHistoryRow[] };
export type DataChecks = {
  checks: { key: string; label: string; severity: string }[];
  entries: { game_id: number; check: string; severity: string; detail: string; game: Record<string, any> }[];
};
export type Meta = { feature_details?: Record<string, MetricDetails>; features: Record<string, string>; markets: Record<string, string>; ops: string[]; legacy_names: string[]; line_ranges?: [number, number][]; odds_ranges?: [number, number][]; hdp_ranges?: [number, number][] };
export type RatePart = { bets: number; hit_rate: number | null; profit: number; roi: number | null; roi_low: number | null; roi_high: number | null; avg_odds: number | null };
export type StrategyRating = {
  id: number; name: string; market: string; rules?: number; open?: number; stake?: number; error?: string;
  total?: RatePart; train?: RatePart | null; test?: RatePart | null; light: "green" | "yellow" | "red" | "grey"; light_reason: string;
};
export type StrategyRateResult = { seasons: string[]; test_season: string | null; games: number; strategies: StrategyRating[] };
export type StrategySummary = {
  id: number;
  name: string;
  market: string;
  bets?: number;
  wins?: number;
  pushes?: number;
  hit_rate?: number | null;
  profit?: number;
  stake?: number;
  total_staked?: number;
  avg_odds?: number | null;
  roi?: number | null;
  open?: number;
  error?: string;
};
export type AnalysisStats = { bets: number; profit: number; roi: number | null; avg_odds: number | null };
export type MetricBin = { lower: number | null; upper: number | null; train: AnalysisStats; test: AnalysisStats };
export type MetricAnalysis = { key: string; label: string; correlation: number | null; coverage: number; missing: number; bins: MetricBin[] };
export type Analysis = { available_lines?: { min: number | null; max: number | null; games: number }; market: string; stake: number; overall: AnalysisStats; train: AnalysisStats; test: AnalysisStats; cutoff: string | null; metrics: MetricAnalysis[] };
export type Backtest = {
  stake: number;
  total_staked: number;
  avg_odds: number | null;
  bets: number;
  wins: number;
  pushes: number;
  losses: number;
  hit_rate: number | null;
  profit: number;
  roi: number | null;
  details: (Game & { result: string; odds: number; profit: number })[];
  open: Game[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    if (res.status === 401) window.dispatchEvent(new Event("hxg-unauthorized"));
    if (res.status === 405 && path.startsWith("/analysis")) {
      throw new Error("Der laufende Server hat einen älteren Programmstand. Bitte Handball xG mit stop.vbs beenden und mit start.vbs neu starten, danach die Seite neu laden.");
    }
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keine JSON-Antwort */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

const q = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  competitions: () => request<Competition[]>("/competitions"),
  coverage: () => request<Coverage[]>("/coverage"),
  oddspapiStatus: () =>
    request<{ configured: boolean; used_this_month: number; budget: number; every_hours: number; running: boolean;
      last_run: string | null; message: string }>("/oddspapi/status"),
  oddspapiSync: (competition_id?: number) =>
    request<{ reports?: any[]; calls?: number; used_this_month?: number; budget?: number; message?: string; error?: string }>(
      `/oddspapi/sync${q({ competition_id })}`,
      { method: "POST" },
    ),
  addCompetition: (c: { id: number; name: string; season: string; gender: string }) =>
    request("/competitions", { method: "POST", body: JSON.stringify(c) }),
  patchCompetition: (id: number, body: Partial<Competition>) =>
    request(`/competitions/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  startImport: (id: number, reimport = false) => request(`/competitions/${id}/import${q({ reimport: String(reimport) })}`, { method: "POST" }),
  autoImportStatus: () =>
    request<{ every_hours: number; running: boolean; last_run: string | null; next_run: string | null; message: string }>("/import/auto"),
  importStatus: () =>
    request<{ running: boolean; done: number; total: number; message: string; errors: string[] }>("/import/status"),

  games: (competition_id?: number, status?: string) => request<Game[]>(`/games${q({ competition_id, status })}`),
  gamesExportUrl: (competition_id?: number, stage?: string) => `/api/games/export.xlsx${q({ competition_id, stage })}`,
  verifyOverview: () => request<{ status: { last_run: string | null; message: string | null }; strategies: VerifyRow[] }>("/verify"),
  verifyRefresh: () => request<{ added: number; updated: number; removed: number }>("/verify/refresh", { method: "POST" }),
  verifyDetail: (id: number) => request<VerifyDetail>(`/verify/${id}`),
  verifyGames: (strategyId?: number) => request<VerifyGame[]>(`/verify/games${strategyId ? `?strategy_id=${strategyId}` : ""}`),
  verifyGameMetrics: (gameId: number) => request<VerifyGameMetrics>(`/verify/games/${gameId}`),
  gameLineup: (id: number) => request<{ home: LineupTeam; away: LineupTeam }>(`/games/${id}/lineup`),
  game: (id: number) => request<GameDetail>(`/games/${id}`),
  setLine: (id: number, line: Partial<Line>) => request(`/games/${id}/line`, { method: "PUT", body: JSON.stringify(line) }),
  deleteGames: (ids: number[]) =>
    request<{ deleted: number }>("/games/delete", { method: "POST", body: JSON.stringify({ ids }) }),
  oddsportalImport: (page: OddsportalPage, game_id?: number) =>
    request<OddsportalResult>("/oddsportal/import", { method: "POST", body: JSON.stringify({ ...page, game_id }) }),
  pasteOdds: (id: number, text: string, save: boolean) =>
    request<PasteResult>(`/games/${id}/paste-odds`, { method: "POST", body: JSON.stringify({ text, save }) }),

  teams: (competition_id?: number) => request<any[]>(`/teams${q({ competition_id })}`),
  metricAudit: () => request<MetricAudit>("/metric-audit"),
  metricAuditTeam: (competition_id: number, team_id: number) => request<TeamHistory>(`/metric-audit/team${q({ competition_id, team_id })}`),
  dataChecks: (competition_id?: number) => request<DataChecks>(`/data-checks${q({ competition_id })}`),
  xgModel: (shrinkage: number) => request<any>(`/xg/model${q({ shrinkage })}`),
  xgRecompute: (shrinkage: number) => request(`/xg/recompute`, { method: "POST", body: JSON.stringify({ shrinkage }) }),

  fetchOdds: (competition_id: number, game_ids?: number[]) =>
    request<{ results: any[]; remaining: number | null; limit: number | null }>("/odds/fetch", {
      method: "POST",
      body: JSON.stringify({ competition_id, game_ids }),
    }),

  analyze: (s: Strategy, ids: number[]) => request<Analysis>(`/analysis${q({ competition_ids: ids.join(",") })}`, { method: "POST", body: JSON.stringify(s) }),
  meta: () => request<Meta>("/meta"),
  strategies: () => request<Strategy[]>("/strategies"),
  saveStrategy: (s: Strategy) =>
    s.id
      ? request(`/strategies/${s.id}`, { method: "PUT", body: JSON.stringify(s) })
      : request<{ id: number }>("/strategies", { method: "POST", body: JSON.stringify(s) }),
  deleteStrategy: (id: number) => request(`/strategies/${id}`, { method: "DELETE" }),
  strategyStats: () => request<Record<string, { bets: number; profit: number | null; roi: number | null }>>("/strategies/stats"),
  archiveStrategies: (ids: number[], archived = true) =>
    request<{ changed: number; open_picks_removed: number }>("/strategies/archive", { method: "POST", body: JSON.stringify({ ids, archived }) }),
  backtest: (s: Strategy, competition_ids: number[], excludeErrors = false) =>
    request<Backtest>(`/strategies/backtest${q({ competition_ids: competition_ids.join(","), exclude_errors: excludeErrors ? "true" : undefined })}`, {
      method: "POST",
      body: JSON.stringify(s),
    }),
  metricImpact: (strategy: Strategy, competition_ids: number[], excludeErrors: boolean, market: string, bins: number, mode: string) =>
    request<ImpactResult>("/strategies/metric-impact", {
      method: "POST",
      body: JSON.stringify({ strategy, competition_ids, exclude_errors: excludeErrors, market, bins, mode }),
    }),
  strategyBreakdown: (strategy: Strategy, competition_ids: number[], excludeErrors: boolean, lineRanges: [number, number][], oddsRanges: [number, number][], hdpRanges: [number, number][]) =>
    request<BreakdownResult>("/strategies/breakdown", {
      method: "POST",
      body: JSON.stringify({ strategy, competition_ids, exclude_errors: excludeErrors, line_ranges: lineRanges, odds_ranges: oddsRanges, hdp_ranges: hdpRanges }),
    }),
  strategyRate: (competition_ids: number[], excludeErrors: boolean, testSeason: string | null) =>
    request<StrategyRateResult>("/strategies/rate", { method: "POST", body: JSON.stringify({ competition_ids, exclude_errors: excludeErrors, test_season: testSeason }) }),
  strategySummary: (competition_ids: number[]) =>
    request<StrategySummary[]>(`/strategies/summary${q({ competition_ids: competition_ids.join(",") })}`),
  goalCorrelation: (ids: number[], excludeErrors: boolean, custom: CustomPredictor[], target?: string, key?: string) =>
    request<GoalCorrelation>("/goal-correlation", { method: "POST", body: JSON.stringify({ competition_ids: ids, exclude_errors: excludeErrors, custom, target, key }) }),
  goalTable: (ids: number[], excludeErrors: boolean, target: string, formula: string, minGames = 0) =>
    request<GoalTable>("/goal-correlation/games", { method: "POST", body: JSON.stringify({ competition_ids: ids, exclude_errors: excludeErrors, target, formula, min_games: minGames }) }),
  goalCompare: (ids: number[], excludeErrors: boolean, target: string, minGames: number, formulas: { name: string; formula: string }[], split: boolean) =>
    request<MetricCompareResult>("/goal-correlation/compare", { method: "POST", body: JSON.stringify({ competition_ids: ids, exclude_errors: excludeErrors, target, min_games: minGames, formulas, split }) }),
  goalRank: (ids: number[], excludeErrors: boolean, target: string, minGames: number, byMinGames = false, group = "Alle gewählten Spiele", byLeague = false,
    testSeason: string | null = null) =>
    request<MetricRankResult>("/goal-correlation/rank", { method: "POST", body: JSON.stringify({
      competition_ids: ids, exclude_errors: excludeErrors, target, min_games: minGames, by_min_games: byMinGames, group, by_league: byLeague, test_season: testSeason }) }),
  goalCorrelationNames: () => request<Record<string, string>>("/goal-correlation/names"),
  predictions: (competition_id?: number, days?: number) => request<(Game & { strategies: { id: number; name: string; market: string }[] })[]>(
    `/predictions${q({ competition_id, days })}`,
  ),
};

export type MarketCell = {
  bets: number; wins: number; pushes: number; hit_rate: number | null; profit: number; roi: number | null;
  roi_low: number | null; roi_high: number | null; avg_odds: number | null;
};
export type BreakdownRow = { label: string; low: number | null; high: number | null; games: number; markets: Record<string, MarketCell> };
export type BreakdownResult = {
  markets: Record<string, string>; games: number; total: Record<string, MarketCell>;
  line_ranges: [number, number][]; odds_ranges: [number, number][]; hdp_ranges: [number, number][];
  tables: { key: string; name: string; title: string; rows: BreakdownRow[] }[];
};

export type ImpactClass = { low: number; high: number; bets: number; wins: number; profit: number; roi: number | null; hit_rate: number | null };
export type ImpactMetric = { name: string; bets: number; r: number | null; best: ImpactClass | null; worst: ImpactClass | null; spread: number | null; classes: ImpactClass[] };
export type ImpactResult = {
  market: string; bins: number; mode: string; metrics: ImpactMetric[];
  total: { bets: number; wins: number; profit: number; roi: number | null; hit_rate: number | null };
};

export type LineupPlayer = {
  name: string; games: number; xg: number; goals: number; xg_per_game: number; goals_per_game: number;
  finishing: number; share: number; last5: number; regular: boolean; recent: boolean; last_game: number;
};
export type LineupTeam = { games: number; team_xg: number; with_previous?: boolean; players: LineupPlayer[] };

/** Verifikator: Strategie ab jetzt mitlaufen lassen. */
export type VerifyStats = {
  id: number; name: string; market: string;
  picks: number; settled: number; open: number; wins: number; losses: number; pushes: number;
  hit_rate: number | null; profit: number; roi: number | null; avg_odds: number | null;
  first: string | null; last_game: string | null;
  current_kind: "win" | "loss" | null; current: number; current_loss: number; current_win: number;
  max_loss: number; median_loss: number | null; max_win: number; median_win: number | null;
};
export type VerifyRow = VerifyStats & { curve: number[] };
export type VerifyPick = {
  game_id: number; start: string; home: string; away: string; home_score: number | null; away_score: number | null;
  finished: boolean; market: string; line: number | null; odds: number; stake: number; created_at: string;
  result: "win" | "loss" | "push" | null; profit: number | null; cum: number | null;
};
export type VerifyDetail = VerifyStats & { picks: VerifyPick[] };
export type VerifyGamePick = { strategy_id: number; name: string; market: string; line: number | null; odds: number; stake: number; result: "win" | "loss" | "push"; profit: number };
export type VerifyGame = {
  game_id: number; start: string; home: string; away: string; home_score: number | null; away_score: number | null;
  league: string | null; picks: VerifyGamePick[]; profit: number;
};
export type VerifyMetric = { name: string; value: number | string | boolean | null; alt: boolean };
export type InGameSide = { goals: number | null; ht: number | null; attacks: number | null; shots: number | null; shot_goals: number | null; xg: number | null; seven_m: number | null };
export type VerifyGameMetrics = {
  game_id: number; picks: VerifyGamePick[];
  phases: { key: string; label: string; description: string }[];
  groups: { key: string; label: string; phase: string; metrics: VerifyMetric[] }[];
  in_game: { home: InGameSide; away: InGameSide; shots_imported: boolean } | null;
};
