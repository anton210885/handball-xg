import { useMemo, useState } from "react";
import { Competition } from "../api";
import { leagueName } from "../analysisFilters";

/** Filter für Auswertungen: Gruppe (Geschlecht), Liga, Saisons und Datenfehler. Liefert die gewählten Wettbewerbe. */
export function useGameFilter(competitions: Competition[], usable: (c: Competition) => boolean = c => c.finished > 0) {
  const [gender, setGender] = useState("all");
  const [league, setLeague] = useState("all");
  const [seasons, setSeasons] = useState<string[]>([]);
  const [excludeErrors, setExcludeErrors] = useState(true);

  const pool = competitions.filter(c => usable(c) && (gender === "all" || c.gender === gender));
  const leagues = useMemo(() => [...new Set(pool.map(leagueName))].sort(), [competitions, gender]);
  const allSeasons = useMemo(() => [...new Set(pool.filter(c => league === "all" || leagueName(c) === league).map(c => c.season))].sort(),
    [competitions, gender, league]);
  const included = pool.filter(c => (league === "all" || leagueName(c) === league) && (!seasons.length || seasons.includes(c.season)));
  const ids = included.map(c => c.id);
  const toggleSeason = (s: string) => setSeasons(seasons.includes(s) ? seasons.filter(x => x !== s) : [...seasons, s]);

  const ui = <div className="row">
    <label>Gruppe <select value={gender} onChange={e => { setGender(e.target.value); setLeague("all"); setSeasons([]); }}>
      <option value="all">Alle</option><option value="men">Männer</option><option value="women">Frauen</option></select></label>
    <label>Liga <select value={league} onChange={e => { setLeague(e.target.value); setSeasons([]); }}>
      <option value="all">Alle</option>{leagues.map(l => <option key={l} value={l}>{l}</option>)}</select></label>
    <span className="small muted">Saisons:</span>
    {allSeasons.map(s => <label key={s} className="small"><input type="checkbox" checked={seasons.includes(s)} onChange={() => toggleSeason(s)} /> {s}</label>)}
    {seasons.length > 0 && <button onClick={() => setSeasons([])}>alle Saisons</button>}
    <label className="small"><input type="checkbox" checked={excludeErrors} onChange={e => setExcludeErrors(e.target.checked)} /> Spiele mit Datenfehlern weglassen</label>
  </div>;

  return { ids, included, excludeErrors, gender, league, seasons, ui };
}
