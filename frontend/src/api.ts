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
};

export type Game = {
  id: number;
  competition_id: number;
  start: string;
  finished: boolean;
  shots_imported: boolean;
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
export type GameDetail = Game & { shots: Shot[]; zones: { home: Record<string, ZoneStat>; away: Record<string, ZoneStat> } };

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
};

export type Rule = { feature: string; op: string; value: number };
export type Strategy = { id?: number; name: string; market: string; rules: Rule[]; min_games: number; notes?: string | null };
export type Meta = { features: Record<string, string>; markets: Record<string, string>; ops: string[] };
export type Backtest = {
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

  teams: (competition_id?: number) => request<any[]>(`/teams${q({ competition_id })}`),
  xgModel: (shrinkage: number) => request<any>(`/xg/model${q({ shrinkage })}`),
  xgRecompute: (shrinkage: number) => request(`/xg/recompute`, { method: "POST", body: JSON.stringify({ shrinkage }) }),

  fetchOdds: (competition_id: number, game_ids?: number[]) =>
    request<{ results: any[]; remaining: number | null; limit: number | null }>("/odds/fetch", {
      method: "POST",
      body: JSON.stringify({ competition_id, game_ids }),
    }),

  meta: () => request<Meta>("/meta"),
  strategies: () => request<Strategy[]>("/strategies"),
  saveStrategy: (s: Strategy) =>
    s.id
      ? request(`/strategies/${s.id}`, { method: "PUT", body: JSON.stringify(s) })
      : request<{ id: number }>("/strategies", { method: "POST", body: JSON.stringify(s) }),
  deleteStrategy: (id: number) => request(`/strategies/${id}`, { method: "DELETE" }),
  backtest: (s: Strategy, competition_id?: number) =>
    request<Backtest>(`/strategies/backtest${q({ competition_id })}`, { method: "POST", body: JSON.stringify(s) }),
  predictions: (competition_id?: number) => request<(Game & { strategies: { id: number; name: string; market: string }[] })[]>(
    `/predictions${q({ competition_id })}`,
  ),
};
