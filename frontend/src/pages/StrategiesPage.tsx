import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, Backtest, Rule, Strategy, StrategyRateResult } from "../api";
import ConditionEditor, { describe, nameLabel, Names } from "../components/ConditionEditor";
import MetricGuide from "../components/MetricGuide";
import StrategyRatings from "../components/StrategyRatings";
import StrategyBreakdown from "../components/StrategyBreakdown";
import MetricImpact from "../components/MetricImpact";
import { useGameFilter } from "../components/GameFilter";
import { useCompetition } from "../App";
import { leagueName } from "../analysisFilters";
import { isFavorite } from "../favorites";
import { suggestName } from "../strategyName";
import ProfitCurve from "../components/ProfitCurve";
import { dateTime, fmt, pct } from "../labels";
import { useLoad } from "../useLoad";

/** Bausteine zum Hinzufügen: [Knopf, Formel, Erklärung]. */
const ADD: [string, string, string][] = [
  ["Metrik gegen Linie", "(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) - 3 > over", "Erwartete Tore (Heim + Gast) mit Zu-/Abschlag gegen die Over-Linie"],
  ["Metrik mit Zahl", "pred_total >= 58", "Ein Wert vor dem Spiel gegen eine feste Zahl"],
  ["Spieltag ab", "tour >= 5", "Erst ab diesem Spieltag (40 = KO-Spiel)"],
  ["freie Formel", "home_expGoal + away_expGoal + 2 > over", "Beliebige Formel mit + − × ÷ und Klammern"],
];

/** Regel als Formeltext; alte Regeln aus Feld/Operator/Wert werden dabei zur Formel. */
const ruleFormula = (r: Rule) => (r.formula !== undefined ? r.formula : `${r.feature} ${r.op} ${r.value}`);

/** Bereichs-Filter, die als eigene Felder „von / bis“ erscheinen (gespeichert als Bedingungen „name >= …“ / „name <= …“). */
export type RangeName = "home" | "away" | "over" | "hdp" | "home_games" | "away_games";
const RANGE_ALIASES: Record<string, RangeName> = {
  over: "over", over_line: "over", home: "home", odds_home: "home", away: "away", odds_away: "away", hdp: "hdp", hdp_line: "hdp",
  home_games: "home_games", away_games: "away_games",
};
const RANGE_RULE = /^\s*(home_games|away_games|over|over_line|home|odds_home|away|odds_away|hdp|hdp_line)\s*(>=|>|<=|<)\s*(-?\d+(?:[.,]\d+)?)\s*$/;
function rangeBound(r: Rule): { name: RangeName; side: "from" | "to"; value: number } | null {
  const m = ruleFormula(r).match(RANGE_RULE);
  if (!m) return null;
  return { name: RANGE_ALIASES[m[1]], side: m[2].startsWith(">") ? "from" : "to", value: Number(m[3].replace(",", ".")) };
}
const RANGE_TITLE: Record<RangeName, string> = {
  home: "Quote Home", away: "Quote Away", over: "Over-Linie", hdp: "Handicap-Linie", home_games: "Spiele Heimteam", away_games: "Spiele Gastteam",
};
const RANGE_HELP: Record<RangeName, string> = {
  home: "Quote auf Heimsieg", away: "Quote auf Auswärtssieg", over: "Tore-Linie des Buchmachers", hdp: "aus Sicht Heim, −5,5 = Heim gibt 5,5 Tore vor",
  home_games: "bisherige Spiele vor diesem Spiel", away_games: "bisherige Spiele vor diesem Spiel",
};
const GAMES_RANGES: [number, number][] = [[0, 2], [3, 5], [6, 9], [10, 14], [15, 19], [20, 29], [30, 99], [3, 99], [5, 99], [6, 99], [10, 99]];
/** Geschlecht („sex == 'men'“) und Meisterschaft („league == 'A' or league == 'B'“) als eigene Karten. */
const SEX_RULE = /^\s*sex\s*==\s*['"](men|women)['"]\s*$/;
const LEAGUE_RULE = /^\s*league\s*==\s*'[^']*'(\s+or\s+league\s*==\s*'[^']*')*\s*$/;
const ruleSex = (r: Rule) => ruleFormula(r).match(SEX_RULE)?.[1] as "men" | "women" | undefined;
const ruleLeagues = (r: Rule): string[] | null =>
  LEAGUE_RULE.test(ruleFormula(r)) ? [...ruleFormula(r).matchAll(/'([^']*)'/g)].map((m) => m[1]) : null;
/** Spielart über den Spieltag: KO-Spiele haben tour = 40 (wie in Access), alle anderen < 40. */
const STAGE_RULE = /^\s*tour\s*(<|==)\s*40\s*$/;
const ruleStage = (r: Rule): "league" | "knockout" | undefined => {
  const m = ruleFormula(r).match(STAGE_RULE);
  return m ? (m[1] === "<" ? "league" : "knockout") : undefined;
};
const isCardRule = (r: Rule) => !!rangeBound(r) || !!ruleSex(r) || !!ruleLeagues(r) || !!ruleStage(r);

const RANGE_ORDER: RangeName[] = ["home", "away", "over", "hdp", "home_games", "away_games"];
const numText = (x: number) => String(x).replace(".", ",").replace("-", "−");

const EMPTY: Strategy = {
  name: "",
  market: "over",
  min_games: 3,
  stake: 1,
  min_odds: null,
  max_odds: null,
  rules: [{ feature: "pred_total_minus_line", op: ">=", value: 2 }],
};

export default function StrategiesPage() {
  const { competitions } = useCompetition();
  const location = useLocation();
  const meta = useLoad(() => api.meta(), []);
  const saved = useLoad(() => api.strategies(), []);
  const stats = useLoad(() => (saved.data ? api.strategyStats() : Promise.resolve(null)), [saved.data]);
  const [s, setS] = useState<Strategy>(EMPTY);
  useEffect(() => {
    if (location.state?.draft) setS(location.state.draft as Strategy);
  }, [location.state]);
  const [result, setResult] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [showArchive, setShowArchive] = useState(false);
  const [summary, setSummary] = useState<StrategyRateResult | null>(null);
  const [testSeason, setTestSeason] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Spiele für Backtests: Gruppe, Liga, Saisons wie auf der Korrelationsseite
  const gameFilter = useGameFilter(competitions, (c) => c.finished > 0 && (c.with_stats ?? c.with_shots) > 0);
  const compIds = gameFilter.ids;
  const excludeErrors = gameFilter.excludeErrors;
  const selectionKey = `${compIds.join(",")}|${excludeErrors}`;
  useEffect(() => { setSummary(null); setResult(null); }, [selectionKey]);

  useEffect(() => { setResult(null); }, [s]);

  // Namen für Formeln mit Beschriftung und Erklärung (Werte vor dem Spiel, alte Formelnamen, _alt)
  const names: Names = useMemo(() => {
    const out: Names = {};
    for (const [k, d] of Object.entries(meta.data?.feature_details ?? {})) out[k] = { label: d.label, description: d.description };
    for (const [k, v] of Object.entries(meta.data?.features ?? {})) out[k] ??= { label: v };
    for (const k of meta.data?.legacy_names ?? []) out[k] ??= { label: k };
    return out;
  }, [meta.data]);

  // Over-Linie, Quote Home und Quote Away als Felder „von / bis“
  const bound = (name: RangeName, side: "from" | "to") =>
    s.rules.map(rangeBound).find((x) => x?.name === name && x.side === side)?.value;
  const withBound = (rules: Rule[], name: RangeName, side: "from" | "to", text: string): Rule[] => {
    const formula = `${name} ${side === "from" ? ">=" : "<="} ${text}`;
    let done = false;
    const out: Rule[] = [];
    for (const r of rules) {
      const x = rangeBound(r);
      if (!x || x.name !== name || x.side !== side) { out.push(r); continue; }
      if (done || text === "") continue;  // doppelte entfernen bzw. Feld geleert
      out.push({ formula });
      done = true;
    }
    if (!done && text !== "") out.push({ formula });
    return out;
  };
  const setBound = (name: RangeName, side: "from" | "to", text: string) => setS({ ...s, rules: withBound(s.rules, name, side, text) });
  /** Bereich aus der Aufteilung oder der Vorauswahl übernehmen (null = Filter entfernen). */
  const applyRange = (name: RangeName, low: number | null, high: number | null) => {
    let rules = withBound(s.rules, name, "from", low === null ? "" : String(low));
    rules = withBound(rules, name, "to", high === null ? "" : String(high));
    setS({ ...s, rules });
  };
  const presets = (name: RangeName): [number, number][] =>
    name === "home_games" || name === "away_games" ? GAMES_RANGES
      : (name === "over" ? meta.data?.line_ranges : name === "hdp" ? meta.data?.hdp_ranges : meta.data?.odds_ranges) ?? [];
  const rangeField = (name: RangeName) => {
    const from = bound(name, "from"), to = bound(name, "to");
    const active = from !== undefined || to !== undefined;
    const current = presets(name).findIndex(([lo, hi]) => lo === from && hi === to);
    const step = name === "over" || name === "hdp" ? 0.5 : name.endsWith("_games") ? 1 : 0.01;
    return (
      <div key={name} className={`range-card range-${name}${active ? " active" : ""}`}
        title={`Nur Spiele mit ${RANGE_TITLE[name]} in diesem Bereich, beide Grenzen eingeschlossen (leer = egal)`}>
        <div className="range-head">
          <span className="range-dot" /> <b>{RANGE_TITLE[name]}</b>
          <span className="small muted"> · {RANGE_HELP[name]}</span>
        </div>
        <div className="range-inputs">
          <input type="number" step={step} placeholder="von" value={from ?? ""} onChange={(e) => setBound(name, "from", e.target.value)} />
          <span className="muted">bis</span>
          <input type="number" step={step} placeholder="bis" value={to ?? ""} onChange={(e) => setBound(name, "to", e.target.value)} />
        </div>
        <select value={current} onChange={(e) => { const p = presets(name)[Number(e.target.value)]; applyRange(name, p ? p[0] : null, p ? p[1] : null); }}>
          <option value={-1}>{!active ? "Bereich wählen …" : current < 0 ? "eigener Bereich" : ""}</option>
          {presets(name).map(([lo, hi], i) => <option key={i} value={i}>{numText(lo)} bis {numText(hi)}</option>)}
          {active && <option value={-2}>egal (Filter entfernen)</option>}
        </select>
      </div>
    );
  };

  // Ein Bereich „von / bis“ zählt als eine Bedingung
  const conditionCount = s.rules.filter((r) => !rangeBound(r)).length + new Set(s.rules.map((r) => rangeBound(r)?.name).filter(Boolean)).size;

  // Geschlecht und Meisterschaft
  const sex = s.rules.map(ruleSex).find(Boolean);
  const leagues = s.rules.map(ruleLeagues).find((x) => x) ?? [];
  const setSex = (v: "men" | "women" | null) => {
    const rules = s.rules.filter((r) => !ruleSex(r));
    setS({ ...s, rules: v ? [...rules, { formula: `sex == '${v}'` }] : rules });
  };
  const setLeagues = (list: string[]) => {
    const rules = s.rules.filter((r) => !ruleLeagues(r));
    const formula = list.map((l) => `league == '${l.replace(/'/g, "")}'`).join(" or ");
    setS({ ...s, rules: list.length ? [...rules, { formula }] : rules });
  };
  const leagueOptions = useMemo(() => {
    const seen = new Map<string, Set<string>>();
    for (const c of competitions) {
      const name = leagueName(c);
      if (!seen.has(name)) seen.set(name, new Set());
      seen.get(name)!.add(c.gender);
    }
    return [...seen.entries()].map(([name, g]) => ({ name, genders: g })).sort((a, b) => a.name.localeCompare(b.name));
  }, [competitions]);
  const shownLeagues = leagueOptions.filter((l) => !sex || l.genders.has(sex) || leagues.includes(l.name));
  const stage = s.rules.map(ruleStage).find(Boolean);
  const setStage = (v: "league" | "knockout" | null) => {
    const rules = s.rules.filter((r) => !ruleStage(r));
    setS({ ...s, rules: v ? [...rules, { formula: v === "league" ? "tour < 40" : "tour == 40" }] : rules });
  };
  /** Text für den Satz „Wette auf … wenn …“. */
  const ruleText = (r: Rule) => {
    const st = ruleStage(r);
    if (st) return st === "league" ? "nur Meisterschaftsspiele (kein KO)" : "nur KO-Spiele";
    const g = ruleSex(r);
    if (g) return g === "men" ? "nur Männer" : "nur Frauen";
    const l = ruleLeagues(r);
    if (l) return `Meisterschaft ${l.join(" oder ")}`;
    return describe(ruleFormula(r), names);
  };

  const [running, setRunning] = useState(false);
  // Namensvorschlag nach dem Schema MARKT · WER · BEREICHE · KERNBEDINGUNG · Version
  const suggested = useMemo(
    () => suggestName(s.market, s.rules, (saved.data ?? []).filter((x) => x.id !== s.id).map((x) => x.name)),
    [s.market, s.rules, s.id, saved.data]);
  const [resultName, setResultName] = useState<{ name: string; suggested: string } | null>(null);
  const [analysis, setAnalysis] = useState<"split" | "impact">("split");
  /** Klasse aus „Einfluss der Metriken“ als Bedingung „name von … bis …“ übernehmen. */
  const addMetricRange = (name: string, lo: number, hi: number) => {
    const r4 = (v: number) => Math.round(v * 10000) / 10000;
    setS({ ...s, rules: [...s.rules, { formula: `${name} >= ${r4(lo)}` }, { formula: `${name} <= ${r4(hi)}` }] });
  };
  const run = async (view?: "split" | "impact") => {
    setError(null);
    setRunning(true);
    if (view) setAnalysis(view);
    try {
      setResult(await api.backtest(s, compIds, excludeErrors));
      setResultName({ name: s.name, suggested });
      // Ergebnis zeigen: zum Backtest herunterscrollen
      setTimeout(() => document.getElementById(view ? "analysis-tabs" : "backtest-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const save = async () => {
    setError(null);
    try {
      const r: any = await api.saveStrategy(s);
      if (r?.id) setS({ ...s, id: r.id });
      saved.reload();
      setSummary(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const runSummary = async (season: string | null = testSeason) => {
    setError(null);
    setBusy(true);
    try {
      const r = await api.strategyRate(compIds, excludeErrors, season);
      setSummary(r);
      setTestSeason(r.test_season);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const pick = async (id: number) => {
    const x = (saved.data ?? []).find((y) => y.id === id);
    if (!x) return;
    setS(x);
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      setResult(await api.backtest(x, compIds, excludeErrors));
    } catch (e: any) {
      setError(e.message);
    }
  };

  // Zuletzt gebaute zuerst (höchste Nummer oben)
  const activeCount = (saved.data ?? []).filter((x) => !x.archived).length;
  const archivedCount = (saved.data ?? []).length - activeCount;
  const savedShown = (saved.data ?? []).filter((x) => !!x.archived === showArchive && x.name.toLowerCase().includes(filter.toLowerCase()))
    .sort((a, b) => (b.id ?? 0) - (a.id ?? 0));

  const setArchived = async (id: number, archived: boolean) => {
    await api.archiveStrategies([id], archived);
    if (s.id === id) setS({ ...s, archived });
    saved.reload();
  };

  const remove = async (id: number) => {
    await api.deleteStrategy(id);
    if (s.id === id) setS(EMPTY);
    saved.reload();
  };

  return (
    <>
      <div className="topbar">
        <h1>Strategien</h1>
        <button className="secondary" onClick={() => { setS(EMPTY); setResult(null); }}>
          Neue Strategie
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      <MetricGuide meta={meta.data} />

      <div className="panel">
        <div className="small muted" style={{ marginBottom: 6 }}><b>Backtest über</b> – gilt für den Einzel-Backtest und die Ampel unten:</div>
        {gameFilter.ui}
        <div className="small muted" style={{ marginTop: 6 }}>{gameFilter.included.length} Wettbewerbe gewählt
          {gameFilter.league === "all" && gameFilter.gender === "all" && !gameFilter.seasons.length ? " (alle Ligen, beide Geschlechter, alle Saisons)" : ""}.</div>
      </div>

      <div className="grid2" style={{ gridTemplateColumns: "minmax(300px, 1fr) 2fr" }}>
        <div className="panel">
          <h2>Gespeichert ({activeCount})</h2>
          <div className="seg small" style={{ marginBottom: 6 }}>
            <button className={showArchive ? "secondary" : ""} onClick={() => setShowArchive(false)}>Aktiv ({activeCount})</button>
            <button className={showArchive ? "" : "secondary"} onClick={() => setShowArchive(true)}>Archiv ({archivedCount})</button>
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            {showArchive ? "Archivierte tippen nicht und fehlen in Ampel und Prognosen. „↺“ holt sie zurück." : "Zuletzt gebaute oben."}
          </div>
          <input placeholder="Suchen …" value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: "100%", marginBottom: 6 }} />
          {savedShown.length === 0 && <div className="muted small">{showArchive ? "Archiv ist leer." : "Noch keine aktive Strategie."}</div>}
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
          {savedShown.map((x) => (
            <div key={x.id} className={`saved-item ${s.id === x.id ? "active" : ""}`}
              onClick={() => { setS(x); setResult(null); }} title={x.name || `Strategie ${x.id}`}>
              <div className="saved-main">
                <div className="saved-name">{x.name || `Strategie ${x.id}`}</div>
                <div className="saved-meta">
                  <span className="muted">#{x.id}</span>
                  <span className="tag">{meta.data?.markets[x.market] ?? x.market}</span>
                  {x.name.startsWith("NB:") && <span className="muted">Notebook</span>}
                  <span className="saved-stats" title="Über alle beendeten Spiele ohne Datenfehler (Einsatz je Wette wie eingestellt)">
                    {stats.data?.[String(x.id)] ? (() => {
                      const st = stats.data![String(x.id)];
                      return <>
                        <span>{st.bets} Wetten</span>
                        <span className={st.profit && st.profit > 0 ? "pos" : st.profit && st.profit < 0 ? "neg" : ""}>
                          {st.profit === null ? "–" : `${st.profit > 0 ? "+" : ""}${st.profit.toFixed(2)}`}
                        </span>
                      </>;
                    })() : <span className="muted">…</span>}
                  </span>
                </div>
              </div>
              <button className="saved-del" title={x.archived ? "Zurückholen (wieder aktiv)" : "Archivieren"}
                onClick={(e) => { e.stopPropagation(); setArchived(x.id!, !x.archived); }}>{x.archived ? "↺" : "⤓"}</button>
              <button className="saved-del" title="Strategie endgültig löschen"
                onClick={(e) => { e.stopPropagation(); if (confirm(`Strategie „${x.name || x.id}“ löschen?`)) remove(x.id!); }}>✕</button>
            </div>
          ))}
          </div>
        </div>

        <div className="panel">
          <h2>{s.id ? "Strategie bearbeiten" : "Strategie bauen"}</h2>
          <div className="row" style={{ marginBottom: 10 }}>
            <input placeholder={suggested} value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} style={{ flex: 1, minWidth: 180 }} />
            <select value={s.market} onChange={(e) => setS({ ...s, market: e.target.value })}>
              {Object.entries(meta.data?.markets ?? {}).map(([k, v]) => (
                <option key={k} value={k} title={meta.data?.feature_details?.[k]?.description}>{v}</option>
              ))}
            </select>
            <label className="small muted">min. Spiele je Team</label>
            <input className="cell" type="number" value={s.min_games} onChange={(e) => setS({ ...s, min_games: Number(e.target.value) })} />
          </div>
          <div className="name-suggest small" style={{ marginBottom: 10 }}>
            <span className="muted">Namensvorschlag:</span> <b>{suggested}</b>
            {s.name !== suggested && <button className="secondary" style={{ marginLeft: 8 }} onClick={() => setS({ ...s, name: suggested })}
              title="Vorschlag als Namen übernehmen – Version bei Bedarf anpassen">übernehmen</button>}
          </div>
          <div className="row" style={{ marginBottom: 12 }}>
            <label>Einsatz je Wette <input className="cell" type="number" min="0.01" step="0.01" value={s.stake ?? 1} onChange={(e) => setS({ ...s, stake: Number(e.target.value) })} /></label>
            {(s.min_odds || s.max_odds) ? (
              <>
                <label title="Quote des gewählten Wettmarkts">Quote des Markts von <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.min_odds ?? ""} onChange={(e) => setS({ ...s, min_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                <label>bis <input className="cell" type="number" min="1.01" step="0.01" placeholder="egal" value={s.max_odds ?? ""} onChange={(e) => setS({ ...s, max_odds: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                <button className="secondary" onClick={() => setS({ ...s, min_odds: null, max_odds: null })}>entfernen</button>
              </>
            ) : null}
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>Spiele eingrenzen (gilt für jeden Markt, beide Grenzen eingeschlossen, leer = egal):</div>
          <div className="range-grid">
            <div className={`range-card range-sex${sex || stage ? " active" : ""}`}>
              <div className="range-head"><span className="range-dot" /> <b>Geschlecht</b><span className="small muted"> · Männer- oder Frauenspiele</span></div>
              <div className="row" style={{ gap: 6 }}>
                {([[null, "egal"], ["men", "Männer"], ["women", "Frauen"]] as const).map(([v, label]) => (
                  <button key={label} className={(sex ?? null) === v ? "" : "secondary"} style={{ flex: 1 }} onClick={() => setSex(v)}>{label}</button>
                ))}
              </div>
              <div className="range-head" style={{ marginTop: 4 }}><b>Spielart</b><span className="small muted"> · Meisterschaft (Hauptrunde) oder KO/Playoff</span></div>
              <div className="row" style={{ gap: 6 }}>
                {([[null, "egal"], ["league", "Meisterschaft"], ["knockout", "KO-Spiel"]] as const).map(([v, label]) => (
                  <button key={label} className={(stage ?? null) === v ? "" : "secondary"} style={{ flex: 1 }} onClick={() => setStage(v)}>{label}</button>
                ))}
              </div>
            </div>
            <div className={`range-card range-league${leagues.length ? " active" : ""}`}>
              <div className="range-head">
                <span className="range-dot" /> <b>Meisterschaft</b>
                <span className="small muted"> · {leagues.length ? `${leagues.length} gewählt` : "alle"}</span>
                {leagues.length > 0 && <button className="secondary small" style={{ float: "right", padding: "0 8px" }} onClick={() => setLeagues([])}>alle</button>}
              </div>
              <div className="league-list">
                {shownLeagues.map((l) => (
                  <label key={l.name} className="small">
                    <input type="checkbox" checked={leagues.includes(l.name)}
                      onChange={(e) => setLeagues(e.target.checked ? [...leagues, l.name] : leagues.filter((x) => x !== l.name))} />{" "}
                    {l.name}
                  </label>
                ))}
              </div>
            </div>
            {RANGE_ORDER.map(rangeField)}
          </div>
          <div className="note small" style={{ marginBottom: 10 }}>
            <b>Wette auf {meta.data?.markets[s.market] ?? s.market}, wenn</b>{" "}
            {s.rules.length ? s.rules.map((r, i) => <span key={i}>{i > 0 && <b> und </b>}{ruleText(r)}</span>) : "immer (keine Bedingung)"}
            {s.min_games > 0 && <> <b>und</b> beide Teams mindestens {s.min_games} Spiele</>}
            {(s.min_odds || s.max_odds) && <> <b>und</b> Quote {s.min_odds ? `ab ${fmt(s.min_odds, 2)}` : ""} {s.max_odds ? `bis ${fmt(s.max_odds, 2)}` : ""}</>}.
            {conditionCount >= 5 && <div className="neg" style={{ marginTop: 4 }}>⚠ {conditionCount} Bedingungen: Je mehr, desto weniger Wetten und desto eher passt die Strategie nur zur Vergangenheit.</div>}
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>Bedingungen (alle müssen erfüllt sein). Maus über einen Namen zeigt die Erklärung; „Text“ schaltet auf die Formel um.</div>
          {s.rules.map((r, i) => isCardRule(r) ? null : (
            <ConditionEditor key={`${s.id ?? "neu"}-${i}-${s.rules.length}`} formula={ruleFormula(r)} names={names} listId="strategy-names" market={s.market}
              onChange={(f) => setS({ ...s, rules: s.rules.map((x, j) => (j === i ? { formula: f } : x)) })}
              onRemove={() => setS({ ...s, rules: s.rules.filter((_, j) => j !== i) })} />
          ))}
          <datalist id="strategy-names">
            {Object.keys(names).map((n) => <option key={n} value={n}>{isFavorite(n) ? "★ " : ""}{nameLabel(n, names)}</option>)}
          </datalist>
          <div className="row" style={{ marginTop: 10 }}>
            <span className="small muted">Hinzufügen:</span>
            {ADD.map(([label, formula, help]) => (
              <button key={label} className="secondary" title={help} onClick={() => setS({ ...s, rules: [...s.rules, { formula }] })}>+ {label}</button>
            ))}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <span style={{ flex: 1 }} />
            {error && <span className="neg small">{error}</span>}
            <button className="secondary" onClick={() => run("impact")} disabled={running || !compIds.length}
              title="Backtest rechnen und direkt den Einfluss jeder Metrik auf den Profit zeigen">Einfluss der Metriken</button>
            <button onClick={() => run()} disabled={running || !compIds.length}>{running ? "Rechne …" : "Backtest"}</button>
            <button className="secondary" onClick={save}>Speichern</button>
            {s.id && <button className="secondary" onClick={() => { setS({ ...s, id: undefined, name: `${s.name} (Kopie)` }); setResult(null); }}>Als neue Strategie kopieren</button>}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Alle Strategien – Ampel</h2>
          <button disabled={busy || !compIds.length} onClick={() => runSummary()}>
            {busy ? "Rechne …" : summary ? "Neu berechnen" : "Alle testen"}
          </button>
        </div>
        {summary ? (
          <StrategyRatings data={summary} markets={meta.data?.markets ?? {}} onPick={pick}
            testSeason={testSeason} onTestSeason={(x) => runSummary(x)} />
        ) : (
          <div className="small muted">
            Testet alle gespeicherten Strategien über die gewählten Spiele und gibt jeder eine Ampel:
            <span style={{ color: "var(--good)" }}> ● grün</span> = Gewinn auf Lern- und Prüf-Saison und sicher,
            <span style={{ color: "var(--warn)" }}> ● gelb</span> = Gewinn, aber noch nicht sicher,
            <span style={{ color: "var(--bad)" }}> ● rot</span> = kein Gewinn oder Verlust auf der Prüf-Saison,
            <span className="muted"> ○ grau</span> = zu wenige Wetten.
          </div>
        )}
      </div>

      {result && (
        <>
          <div className="panel" id="backtest-result">
            <h2>Backtest <span className="muted small">· {resultName?.name || resultName?.suggested}</span></h2>
            {resultName && resultName.name && resultName.name !== resultName.suggested && (
              <div className="small muted" style={{ marginTop: -6, marginBottom: 8 }}>Namensvorschlag: <b>{resultName.suggested}</b></div>
            )}
            <div className="kpis">
              <div className="kpi"><b>{result.bets}</b><span>Wetten</span></div>
              <div className="kpi"><b>{result.wins} / {result.losses} / {result.pushes}</b><span>Gewonnen / verloren / zurück</span></div>
              <div className="kpi"><b>{pct(result.hit_rate)}</b><span>Trefferquote</span></div>
              <div className="kpi"><b>{fmt(result.avg_odds, 2)}</b><span>Ø Quote</span></div>
              <div className="kpi"><b>{fmt(result.total_staked, 2)}</b><span>Gesamteinsatz</span></div>
              <div className="kpi"><b className={result.profit >= 0 ? "pos" : "neg"}>{fmt(result.profit, 2)}</b><span>Profit (Einsatz {fmt(result.stake, 2)} je Wette)</span></div>
              <div className="kpi"><b className={(result.roi ?? 0) >= 0 ? "pos" : "neg"}>{pct(result.roi)}</b><span>Rendite</span></div>
            </div>
            {result.bets === 0 && (
              <div className="note small">
                Keine auswertbaren Spiele. Over/Under und Handicap brauchen eingetragene Linien bei beendeten Spielen
                (Seite „Linien & Quoten“), 1/2 braucht Quoten.
              </div>
            )}
            <div className="small muted">
              Ohne eingetragene Over-/Under-Quote rechnet der Backtest mit 1,80 (wie deine alte Auswertung). Wenige Wetten = wenig Aussagekraft.
            </div>
            <h3 style={{ margin: "12px 0 6px" }}>Profit summiert über die Zeit</h3>
            <ProfitCurve points={(() => {
              let cum = 0;
              return [...result.details].sort((a, b) => a.start.localeCompare(b.start)).map((d) => {
                cum += d.profit;
                return { y: cum, label: new Date(d.start).toLocaleDateString("de-DE"),
                  detail: `${d.home.name} – ${d.away.name} ${d.home_score}:${d.away_score} · ${d.result === "win" ? "gewonnen" : d.result === "push" ? "zurück" : "verloren"} ${fmt(d.profit, 2)}` };
              });
            })()} />
          </div>

          <div className="tabs-row" id="analysis-tabs">
            <button className={analysis === "split" ? "" : "secondary"} onClick={() => setAnalysis("split")}>Aufteilung nach Linie und Quote</button>
            <button className={analysis === "impact" ? "" : "secondary"} onClick={() => setAnalysis("impact")}>Einfluss der Metriken</button>
            <span className="small muted">Beides rechnet mit genau den Spielen, auf die deine Strategie passt.</span>
          </div>
          {analysis === "split" ? (
            <StrategyBreakdown strategy={s} compIds={compIds} excludeErrors={excludeErrors}
              lineRanges={meta.data?.line_ranges} oddsRanges={meta.data?.odds_ranges} hdpRanges={meta.data?.hdp_ranges} onApply={applyRange} />
          ) : (
            <MetricImpact strategy={s} compIds={compIds} excludeErrors={excludeErrors} names={names}
              markets={meta.data?.markets ?? {}} legacyNames={meta.data?.legacy_names ?? []} onAdd={addMetricRange} />
          )}

          {result.open.length > 0 && (
            <div className="panel table-wrap">
              <h2>Passt auf {result.open.length} offene Spiele</h2>
              <table>
                <tbody>
                  {result.open.map((g) => (
                    <tr key={g.id}>
                      <td>{dateTime(g.start)}</td>
                      <td><Link to={`/spiele/${g.id}`}>{g.home.name} – {g.away.name}</Link></td>
                      <td className="num">Prognose {fmt(g.features?.pred_total)}</td>
                      <td className="num">Linie {fmt(g.line?.over_line)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {result.details.length > 0 && (
            <div className="panel table-wrap">
              <h2>Einzelne Wetten</h2>
              <table>
                <thead>
                  <tr>
                    <th>Datum</th><th>Spiel</th><th className="num">Ergebnis</th><th className="num">Prognose</th>
                    <th className="num">Linie</th><th className="num">Quote</th><th>Ausgang</th><th className="num">Gewinn</th>
                  </tr>
                </thead>
                <tbody>
                  {result.details.map((b) => (
                    <tr key={b.id}>
                      <td>{dateTime(b.start)}</td>
                      <td><Link to={`/spiele/${b.id}`}>{b.home.name} – {b.away.name}</Link></td>
                      <td className="num">{b.home_score}:{b.away_score}</td>
                      <td className="num">{fmt(b.features?.pred_total)}</td>
                      <td className="num">{fmt(b.line?.over_line)}</td>
                      <td className="num">{fmt(b.odds, 2)}</td>
                      <td><span className={`tag ${b.result === "win" ? "good" : b.result === "loss" ? "bad" : ""}`}>{b.result === "win" ? "gewonnen" : b.result === "loss" ? "verloren" : "zurück"}</span></td>
                      <td className={`num ${b.profit >= 0 ? "pos" : "neg"}`}>{fmt(b.profit, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
