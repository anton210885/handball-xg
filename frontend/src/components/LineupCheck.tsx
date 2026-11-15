import { useMemo, useState } from "react";
import { api, LineupPlayer, LineupTeam } from "../api";
import { fmt, pct } from "../labels";
import { useLoad } from "../useLoad";

type Side = "home" | "away";
const signed = (v: number | null | undefined, d = 1) => (v === null || v === undefined || !isFinite(v) ? "–" : (v > 0 ? "+" : "") + fmt(v, d));

function lastLabel(p: LineupPlayer) {
  if (p.last_game === 0) return "letztes Spiel";
  return `vor ${-p.last_game + 1} Spielen`;
}

function TeamTable({ team, name, missing, toggle, showOld }: {
  team: LineupTeam; name: string; missing: Set<string>; toggle: (n: string) => void; showOld: boolean;
}) {
  const list = team.players.filter((p) => showOld || p.recent || missing.has(p.name));
  const lost = team.players.filter((p) => missing.has(p.name));
  return (
    <div className="panel table-wrap" style={{ margin: 0 }}>
      <h2>{name} <span className="muted small">– {team.games} Spiele{team.with_previous ? " (mit Vorsaison)" : ""}</span></h2>
      <div className="small muted" style={{ marginBottom: 6 }}>
        Summe Ø xG aller gezeigten Spieler {fmt(list.reduce((a, p) => a + p.xg_per_game, 0))} ·
        ohne die fehlenden {fmt(list.filter((p) => !missing.has(p.name)).reduce((a, p) => a + p.xg_per_game, 0))}
        {lost.length > 0 && <> · fehlender Anteil am Team-xG <b className="neg">{pct(lost.reduce((a, p) => a + p.share, 0))}</b></>}
      </div>
      <table>
        <thead>
          <tr>
            <th title="Abhaken, wer in diesem Spiel nicht dabei ist">fehlt</th>
            <th>Spieler</th>
            <th className="num" title="Spiele mit mindestens einem Wurf">Einsätze</th>
            <th className="num">Ø xG</th>
            <th className="num">Ø Tore</th>
            <th className="num" title="Ø Tore − Ø xG je Einsatz („Power_Ranking“ im Notebook)">Abschluss</th>
            <th className="num" title="Anteil am xG des Teams in den berücksichtigten Spielen">Anteil Team-xG</th>
            <th className="num" title="Spiele mit Wurf in den letzten 5 Teamspielen">letzte 5</th>
            <th>zuletzt geworfen</th>
          </tr>
        </thead>
        <tbody>
          {list.map((p) => {
            const off = missing.has(p.name);
            return (
              <tr key={p.name} className={off ? "lineup-off" : ""} onClick={() => toggle(p.name)} style={{ cursor: "pointer" }}>
                <td><input type="checkbox" checked={off} onChange={() => toggle(p.name)} onClick={(e) => e.stopPropagation()} /></td>
                <td>{p.name} {p.regular && <span className="tag good" title="in mindestens 3 der letzten 5 Spiele mit Wurf">Stamm</span>}</td>
                <td className="num">{p.games}</td>
                <td className="num">{fmt(p.xg_per_game, 2)}</td>
                <td className="num">{fmt(p.goals_per_game, 2)}</td>
                <td className={`num ${p.finishing > 0 ? "pos" : p.finishing < 0 ? "neg" : ""}`}>{signed(p.finishing, 2)}</td>
                <td className="num">{pct(p.share)}</td>
                <td className="num">{p.last5}/5</td>
                <td className="small muted">{lastLabel(p)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {list.length === 0 && <div className="small muted">Keine Würfe mit Spielernamen in früheren Spielen.</div>}
    </div>
  );
}

/** „Aufstellung prüfen“: fehlende Spieler abhaken → erwartete Tore ohne ihren Anteil am Team-xG. */
export default function LineupCheck({ gameId, f, overLine, hdpLine, homeName, awayName }: {
  gameId: number; f: Record<string, any>; overLine?: number | null; hdpLine?: number | null; homeName: string; awayName: string;
}) {
  const { data, error, loading } = useLoad(() => api.gameLineup(gameId), [gameId]);
  const [missing, setMissing] = useState<Record<Side, Set<string>>>({ home: new Set(), away: new Set() });
  const [replace, setReplace] = useState(50);
  const [showOld, setShowOld] = useState(false);
  const toggle = (side: Side) => (n: string) =>
    setMissing((m) => { const x = new Set(m[side]); x.has(n) ? x.delete(n) : x.add(n); return { ...m, [side]: x }; });

  const calc = useMemo(() => {
    if (!data || f.home_avg_xg == null || f.away_avg_xg == null || f.home_avg_xga == null || f.away_avg_xga == null) return null;
    const lostShare = (side: Side) => data[side].players.filter((p) => missing[side].has(p.name)).reduce((a, p) => a + p.share, 0);
    const keep = 1 - replace / 100;
    const attH = f.home_avg_xg * (1 - lostShare("home") * keep);
    const attA = f.away_avg_xg * (1 - lostShare("away") * keep);
    const home = (attH + f.away_avg_xga) / 2, away = (attA + f.home_avg_xga) / 2;
    return { home, away, total: home + away, attH, attA, lostH: f.home_avg_xg - attH, lostA: f.away_avg_xg - attA };
  }, [data, f, missing, replace]);

  const anyMissing = missing.home.size + missing.away.size > 0;
  return (
    <div className="panel">
      <h2>Aufstellung prüfen</h2>
      <div className="small muted" style={{ marginBottom: 8 }}>
        Spieler beider Teams aus früheren Spielen (Würfe mit Namen). Hake ab, wer heute fehlt – z. B. laut Aufstellung im PDF-Protokoll.
        Der Angriff des Teams (Ø xG) sinkt um den Anteil der Fehlenden; ein Teil davon fangen die anderen auf.
        Torhüter werfen nicht und stehen deshalb nicht in der Liste.
      </div>
      <div className="row" style={{ gap: 14, alignItems: "center", marginBottom: 10 }}>
        <label title="Wie viel vom xG der Fehlenden die anderen Spieler übernehmen">
          Ersatz fängt auf <input type="range" min={0} max={100} step={10} value={replace} onChange={(e) => setReplace(Number(e.target.value))} /> <b>{replace} %</b>
        </label>
        <label className="small"><input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} /> auch Spieler, die länger nicht geworfen haben</label>
        {anyMissing && <button className="secondary" onClick={() => setMissing({ home: new Set(), away: new Set() })}>Auswahl zurücksetzen</button>}
      </div>
      {calc && (
        <div className="kpis" style={{ marginBottom: 10 }}>
          <div className="kpi"><b>{fmt(calc.home)}</b><span>erw. Tore Heim {anyMissing && <>({signed(calc.home - f.pred_home)})</>}</span></div>
          <div className="kpi"><b>{fmt(calc.away)}</b><span>erw. Tore Gast {anyMissing && <>({signed(calc.away - f.pred_away)})</>}</span></div>
          <div className="kpi"><b>{fmt(calc.total)}</b><span>erw. Tore gesamt {anyMissing && <>({signed(calc.total - f.pred_total)})</>}</span></div>
          {overLine != null && <div className="kpi"><b className={calc.total - overLine > 0 ? "pos" : "neg"}>{signed(calc.total - overLine)}</b><span>gegen Over-Linie {fmt(overLine)}</span></div>}
          {hdpLine != null && <div className="kpi"><b>{signed(calc.home - calc.away + hdpLine)}</b><span>Heim − Gast + Handicap {signed(hdpLine)}</span></div>}
          <div className="kpi"><b>{fmt(calc.attH)} / {fmt(calc.attA)}</b><span>Angriff Ø xG Heim / Gast (ohne Fehlende)</span></div>
        </div>
      )}
      {calc && <div className="small muted" style={{ marginBottom: 10 }}>
        Rechnung wie „Vor dem Spiel“: erw. Tore Heim = (Angriff Heim + Ø xG gegen Gast) / 2. Angriff Heim = Ø xG × (1 − Anteil der Fehlenden × {100 - replace} %).
      </div>}
      {error && <div className="error">{error}</div>}
      {loading && <div className="muted small">Lade Spieler …</div>}
      {data && (
        <div style={{ display: "grid", gap: 12 }}>
          <TeamTable team={data.home} name={homeName} missing={missing.home} toggle={toggle("home")} showOld={showOld} />
          <TeamTable team={data.away} name={awayName} missing={missing.away} toggle={toggle("away")} showOld={showOld} />
        </div>
      )}
    </div>
  );
}
