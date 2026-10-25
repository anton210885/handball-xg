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
};

export type PasteResult = {
  lines: { line: number; a: number; b: number; count: number }[];
  handicaps: { line: number; a: number; b: number; count: number }[];
  warnings: string[];
  found: Partial<Record<"over_line" | "odds_over" | "odds_under" | "hdp_line" | "odds_home" | "odds_draw" | "odds_away", number>>;
  saved: boolean;
};

export type Rule = { feature?: string; op?: string; value?: number; formula?: string };
export type Strategy = { id?: number; name: string; market: string; rules: Rule[]; min_games: number; notes?: string | null; min_odds?: number | null; max_odds?: number | null; stake?: number };
export type MetricDetails = { label: string; description: string; formula: string; source: string; timing: string };
export type Meta = { feature_details?: Record<string, MetricDetails>; features: Record<string, string>; markets: Record<string, string>; ops: string[]; legacy_names: string[] };
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
  importStatus: () =>
    request<{ running: boolean; done: number; total: number; message: string; errors: string[] }>("/import/status"),

  games: (competition_id?: number, status?: string) => request<Game[]>(`/games${q({ competition_id, status })}`),
  game: (id: number) => request<GameDetail>(`/games/${id}`),
  setLine: (id: number, line: Partial<Line>) => request(`/games/${id}/line`, { method: "PUT", body: JSON.stringify(line) }),
  pasteOdds: (id: number, text: string, save: boolean) =>
    request<PasteResult>(`/games/${id}/paste-odds`, { method: "POST", body: JSON.stringify({ text, save }) }),

  teams: (competition_id?: number) => request<any[]>(`/teams${q({ competition_id })}`),
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
  backtest: (s: Strategy, competition_ids: number[]) =>
    request<Backtest>(`/strategies/backtest${q({ competition_ids: competition_ids.join(",") })}`, {
      method: "POST",
      body: JSON.stringify(s),
    }),
  strategySummary: (competition_ids: number[]) =>
    request<StrategySummary[]>(`/strategies/summary${q({ competition_ids: competition_ids.join(",") })}`),
  predictions: (competition_id?: number) => request<(Game & { strategies: { id: number; name: string; market: string }[] })[]>(
    `/predictions${q({ competition_id })}`,
  ),
};
