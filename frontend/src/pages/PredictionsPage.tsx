import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Game, Line } from "../api";
import { useCompetition } from "../App";
import { leagueName } from "../analysisFilters";
import { fmt } from "../labels";
import { useLoad } from "../useLoad";
import StageTag from "../components/StageTag";
import StrategyPopup from "../components/StrategyPopup";

const SOURCE: Record<string, string> = {
  "oddspapi-pre": "OddsPapi (vor dem Spiel)",
  "oddspapi-close": "OddsPapi (Schlusskurs)",
  access: "Access",
  manual: "von Hand",
  handballapi: "HandballAPI",
};
const DAYS = 3;  // heute, morgen, übermorgen
const DAY_NAMES = ["Heute", "Morgen", "Übermorgen"];

type PredGame = Game & { strategies: { id: number; name: string; market: string }[] };

/** Quelle und Stand der Quoten als Tooltip. */
function lineTitle(line: Line | null) {
  if (!line) return "keine Quoten";
  const when = line.updated_at ? new Date(line.updated_at + "Z").toLocaleString("de-DE") : "";
  return `${SOURCE[line.source ?? ""] ?? line.source ?? ""}${when ? ` · Stand ${when}` : ""}`;
}

/** Datum „JJJJ-MM-TT“ in Moskauer Zeit, heute + offset Tage. */
function moscowDay(offset: number) {
  return new Date(Date.now() + 3 * 3600_000 + offset * 86400_000).toISOString().slice(0, 10);
}

function dayTitle(day: string, index: number) {
  const d = new Date(day + "T12:00:00");
  const date = d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  return `${DAY_NAMES[index] ?? date} · ${date}`;
}

export default function PredictionsPage() {
  const { competitions } = useCompetition();
  const { data, error, loading } = useLoad(() => api.predictions(undefined, DAYS), []);
  const [day, setDay] = useState<string | null>(null);
  const [strategyId, setStrategyId] = useState<number | null>(null);
  const days = Array.from({ length: DAYS }, (_, i) => moscowDay(i));
  const comp = Object.fromEntries(competitions.map((c) => [c.id, c]));
  const games = (data ?? []) as PredGame[];
  const byDay = days.map((d) => games.filter((g) => g.start.slice(0, 10) === d));
  const shownDays = days.map((d, i) => ({ d, i, list: byDay[i] })).filter((x) => !day || x.d === day);

  return (
    <>
      <div className="topbar">
        <h1>Prognosen</h1>
        <span className="muted small">
          Alle offenen Spiele von heute, morgen und übermorgen (Moskauer Zeit), alle Ligen · Werte aus den bisherigen Spielen beider Teams ·
          Maus über eine Quote zeigt Quelle und Stand
        </span>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className={day === null ? "" : "secondary"} onClick={() => setDay(null)}>Alle 3 Tage ({games.length})</button>
        {days.map((d, i) => (
          <button key={d} className={day === d ? "" : "secondary"} onClick={() => setDay(d)}>{DAY_NAMES[i]} ({byDay[i].length})</button>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <div className="muted">Lade …</div>}
      {!loading && !error && games.length === 0 && (
        <div className="note">Keine offenen Spiele in den nächsten drei Tagen. Spielpläne kommen über „Daten-Import“.</div>
      )}
      {!loading && shownDays.map(({ d, i, list }) => (
        <div key={d} className="panel table-wrap">
          <h2>{dayTitle(d, i)} <span className="muted small">– {list.length} {list.length === 1 ? "Spiel" : "Spiele"}</span></h2>
          {list.length === 0 ? <div className="small muted">Keine offenen Spiele.</div> : (
            <table>
              <thead>
                <tr>
                  <th className="hide-m">Zeit</th>
                  <th className="hide-m">Liga</th>
                  <th>Spiel</th>
                  <th className="num">erw. Heim</th>
                  <th className="num">erw. Gast</th>
                  <th className="num">erw. gesamt</th>
                  <th className="num">Over-Linie</th>
                  <th className="num">Differenz</th>
                  <th className="num">Over</th>
                  <th className="num">Under</th>
                  <th className="num">1</th>
                  <th className="num">X</th>
                  <th className="num">2</th>
                  <th className="num">Handicap</th>
                  <th>Strategien</th>
                </tr>
              </thead>
              <tbody>
                {list.map((g) => {
                  const diff = g.features?.pred_total_minus_line;
                  const line = g.line;
                  const c = comp[g.competition_id];
                  // Over/Under-Quote nur zusammen mit einer Linie zeigen (sonst ist es der Platzhalter 1,80)
                  const hasLine = line?.over_line !== null && line?.over_line !== undefined;
                  const odds = (v: number | null | undefined) => (
                    <td className="num" title={lineTitle(line)}>{v ? fmt(v, 2) : "–"}</td>
                  );
                  return (
                    <tr key={g.id}>
                      <td className="hide-m">{g.start.slice(11, 16)}</td>
                      <td className="small hide-m">{c ? <>{leagueName(c)}<div className="muted">{c.gender === "women" ? "Frauen" : "Männer"}</div></> : "–"}</td>
                      <td>
                        <Link to={`/spiele/${g.id}`}>{g.home.name} – {g.away.name}</Link>
                        <StageTag game={g} />
                        <div className="show-m muted tiny">{g.start.slice(11, 16)}{c ? ` · ${leagueName(c)} · ${c.gender === "women" ? "Frauen" : "Männer"}` : ""}</div>
                      </td>
                      <td className="num">{fmt(g.features?.pred_home)}</td>
                      <td className="num">{fmt(g.features?.pred_away)}</td>
                      <td className="num"><b>{fmt(g.features?.pred_total)}</b></td>
                      <td className="num">{fmt(g.line?.over_line)}</td>
                      <td className={`num ${diff && diff > 0 ? "pos" : diff && diff < 0 ? "neg" : ""}`}>
                        {diff !== undefined && diff !== null ? (diff > 0 ? "+" : "") + fmt(diff) : "–"}
                      </td>
                      {odds(hasLine ? line?.odds_over : null)}
                      {odds(hasLine ? line?.odds_under : null)}
                      {odds(line?.odds_home)}
                      {odds(line?.odds_draw)}
                      {odds(line?.odds_away)}
                      <td className="num" title={lineTitle(line)}>
                        {line?.hdp_line !== null && line?.hdp_line !== undefined ? (line.hdp_line > 0 ? "+" : "") + fmt(line.hdp_line) : "–"}
                      </td>
                      <td>
                        {g.strategies.map((s) => (
                          <button key={s.id} className="tag good tag-btn" title="Ergebnisse dieser Strategie anzeigen"
                            onClick={() => setStrategyId(s.id)}>{s.name || s.market}</button>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      ))}
      {strategyId !== null && <StrategyPopup id={strategyId} onClose={() => setStrategyId(null)} />}
    </>
  );
}
