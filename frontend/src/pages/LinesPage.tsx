import { useState } from "react";
import { api, Game, Line } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";
import CoverageTable from "../components/CoverageTable";
import PasteOddsDialog from "../components/PasteOddsDialog";
import OddsportalBookmarklet from "../components/OddsportalBookmarklet";
import StageTag, { STAGE_FILTER } from "../components/StageTag";

// Filter für fehlende Quoten
const MISSING: Record<string, { label: string; test: (g: Game) => boolean }> = {
  "": { label: "alle Spiele", test: () => true },
  line: { label: "ohne Torlinie", test: (g) => g.line?.over_line === null || g.line?.over_line === undefined },
  x12: { label: "ohne 1X2-Quoten", test: (g) => !(g.line?.odds_home && g.line?.odds_away) },
  hdp: { label: "ohne Handicap", test: (g) => g.line?.hdp_line === null || g.line?.hdp_line === undefined },
  any: {
    label: "ganz ohne Quoten",
    test: (g) => !g.line || (g.line.over_line == null && !g.line.odds_home && !g.line.odds_away && g.line.hdp_line == null),
  },
};

const FIELDS: [keyof Line, string][] = [
  ["over_line", "Over-Linie"],
  ["odds_over", "Quote Over"],
  ["odds_under", "Quote Under"],
  ["hdp_line", "Handicap Heim"],
  ["odds_home", "1"],
  ["odds_draw", "X"],
  ["odds_away", "2"],
];

function LineInput({ game, field, onSaved }: { game: Game; field: keyof Line; onSaved: () => void }) {
  const initial = game.line?.[field] ?? (field === "odds_over" || field === "odds_under" ? 1.8 : "");
  const [value, setValue] = useState(String(initial));
  const [state, setState] = useState<"" | "saving" | "ok" | "err">("");
  const save = async () => {
    const parsed = value.trim() === "" ? null : Number(value.replace(",", "."));
    if (parsed !== null && Number.isNaN(parsed)) return setState("err");
    if (String(parsed ?? "") === String(initial)) return;
    setState("saving");
    try {
      await api.setLine(game.id, { [field]: parsed });
      setState("ok");
      onSaved();
    } catch {
      setState("err");
    }
  };
  return (
    <input
      className="cell"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      style={{ borderColor: state === "ok" ? "var(--good)" : state === "err" ? "var(--bad)" : undefined }}
    />
  );
}

export default function LinesPage() {
  const { competitionId, competitions, setCompetitionId } = useCompetition();
  // „Alle Spiele“: eine abgeschlossene Saison hat keine offenen Spiele, die Liste wäre sonst leer
  const [status, setStatus] = useState("");
  const { data, error, reload } = useLoad(() => api.games(competitionId, status || undefined), [competitionId, status]);
  const [oddsMsg, setOddsMsg] = useState<string | null>(null);
  const comp = competitions.find((c) => c.id === competitionId);

  const papi = useLoad(() => api.oddspapiStatus(), []);
  const [papiMsg, setPapiMsg] = useState<string | null>(null);
  const syncOddsPapi = async () => {
    setPapiMsg("Hole Quoten von OddsPapi … (kann einige Minuten dauern)");
    try {
      const r = await api.oddspapiSync(competitionId);
      if (r.error) return setPapiMsg(r.error);
      const sum = (k: string) => (r.reports ?? []).reduce((a, x) => a + (x[k] ?? 0), 0);
      setPapiMsg(
        `${sum("closing")} Spiele mit Schlusskursen, ${sum("prematch")} mit Vorab-Quoten, ` +
          `${sum("no_data")} ohne Daten bei OddsPapi, ${sum("unmatched")} nicht zuordenbar. ` +
          `${r.calls} Abfragen, Monat: ${r.used_this_month} von ${r.budget}. ${r.message === "fertig" ? "" : r.message ?? ""}`,
      );
      papi.reload();
      reload();
    } catch (e: any) {
      setPapiMsg(`Fehler: ${e.message}`);
    }
  };

  const fetchOdds = async () => {
    if (!competitionId) return;
    setOddsMsg("Frage HandballAPI ab …");
    try {
      const r = await api.fetchOdds(competitionId);
      const withOdds = r.results.filter((x) => x.odds).length;
      setOddsMsg(
        `${r.results.length} Spiele geprüft, ${withOdds} mit Quoten. Rest-Kontingent: ${r.remaining ?? "?"} von ${r.limit ?? "?"}.`,
      );
      reload();
    } catch (e: any) {
      setOddsMsg(`Fehler: ${e.message}`);
    }
  };

  const [missing, setMissing] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [deleteMsg, setDeleteMsg] = useState<string | null>(null);
  const all = status === "finished" ? [...(data ?? [])].reverse() : data ?? [];
  const [stage, setStage] = useState("");
  const games = all.filter(MISSING[missing].test).filter(STAGE_FILTER[stage].test);
  const [pasteFor, setPasteFor] = useState<number | null>(null);

  const toggle = (id: number) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const allSelected = games.length > 0 && games.every((g) => selected.includes(g.id));
  const remove = async (ids: number[]) => {
    const names = games.filter((g) => ids.includes(g.id)).map((g) => `${g.home.name} – ${g.away.name}`);
    const what = ids.length === 1 ? `das Spiel „${names[0]}“` : `${ids.length} Spiele`;
    if (!window.confirm(`Wirklich ${what} endgültig löschen? Würfe und Quoten werden mitgelöscht. Ein späterer Import kann das Spiel wieder anlegen.`)) return;
    try {
      const r = await api.deleteGames(ids);
      setDeleteMsg(`${r.deleted} ${r.deleted === 1 ? "Spiel" : "Spiele"} gelöscht.`);
      setSelected(selected.filter((x) => !ids.includes(x)));
      reload();
    } catch (e: any) {
      setDeleteMsg(`Fehler beim Löschen: ${e.message}`);
    }
  };

  return (
    <>
      <div className="topbar">
        <h1>Linien & Quoten</h1>
        <div className="row">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Offene Spiele</option>
            <option value="finished">Beendete Spiele (für Backtests)</option>
            <option value="">Alle Spiele</option>
          </select>
          <select value={missing} onChange={(e) => { setMissing(e.target.value); setSelected([]); }} title="Nur Spiele mit fehlenden Quoten zeigen">
            {Object.entries(MISSING).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          <select value={stage} onChange={(e) => { setStage(e.target.value); setSelected([]); }} title="Nach Spielphase filtern">
            {Object.entries(STAGE_FILTER).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          <button
            disabled={!papi.data?.configured || papi.data?.running}
            title="Holt Torlinien (Regel 1,70–2,00), 1X2 und Handicap für diesen Wettbewerb von OddsPapi"
            onClick={syncOddsPapi}
          >
            Quoten von OddsPapi holen
          </button>
          <button className="secondary" disabled={!comp?.handballapi_tournament_id} onClick={fetchOdds}>
            Quoten von HandballAPI
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="note small">
        Werte eintippen, mit Enter oder Klick daneben wird gespeichert. Für die russische Superliga liefert die HandballAPI
        keine Quoten – hier also von Hand eintragen. Für Backtests braucht ein beendetes Spiel mindestens eine Over-Linie.
        {oddsMsg && <div style={{ marginTop: 6 }}>{oddsMsg}</div>}
        {papi.data?.configured && (
          <div style={{ marginTop: 6 }}>
            OddsPapi: {papi.data.used_this_month} von {papi.data.budget} Abfragen diesen Monat verbraucht · automatischer
            Abgleich alle {papi.data.every_hours} Stunden
            {papi.data.last_run ? ` · zuletzt ${new Date(papi.data.last_run + "Z").toLocaleString("de-DE")}` : ""}
          </div>
        )}
        {papiMsg && <div style={{ marginTop: 6 }}>{papiMsg}</div>}
      </div>
      <OddsportalBookmarklet />
      <CoverageTable
        onPick={(id, st) => {
          setCompetitionId(id);
          setStatus(st);
          setMissing("line");
          setSelected([]);
        }}
      />
      <div className="panel table-wrap">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
          <span className="small muted">
            {games.length} von {all.length} Spielen{missing ? ` · Filter: ${MISSING[missing].label}` : ""}
            {stage ? ` · ${STAGE_FILTER[stage].label}` : ""}
            {deleteMsg ? ` · ${deleteMsg}` : ""}
            {games.length === 0 && (status || missing || stage) && (
              <>
                {" · "}
                {all.length === 0 && status === "open" ? "keine offenen Spiele in diesem Wettbewerb " : "kein Spiel passt zu den Filtern "}
                <button className="secondary" onClick={() => { setStatus(""); setMissing(""); setStage(""); }}>
                  Filter zurücksetzen
                </button>
              </>
            )}
          </span>
          <button className="danger" disabled={!selected.length} onClick={() => remove(selected)}>
            Ausgewählte löschen ({selected.length})
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  title="Alle angezeigten Spiele auswählen"
                  checked={allSelected}
                  onChange={() => setSelected(allSelected ? [] : games.map((g) => g.id))}
                />
              </th>
              <th></th>
              <th>Datum (MSK)</th>
              <th>Spiel</th>
              <th className="num">Prognose</th>
              {status === "finished" && <th className="num">Tore</th>}
              {FIELDS.map(([, label]) => (
                <th key={label} className="num">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {games.map((g) => (
              // Schlüssel mit Stand der Linie: nach dem Einfügen zeigen die Felder die neuen Werte
              <tr key={`${g.id}-${g.line?.updated_at ?? ""}`}>
                <td>
                  <input type="checkbox" checked={selected.includes(g.id)} onChange={() => toggle(g.id)} />
                </td>
                <td className="row" style={{ flexWrap: "nowrap" }}>
                  <button className="secondary" title="Quotentabelle einfügen" onClick={() => setPasteFor(g.id)}>
                    Einfügen
                  </button>
                  <button className="secondary" title="Spiel löschen" onClick={() => remove([g.id])}>
                    ✕
                  </button>
                </td>
                <td>{dateTime(g.start)}</td>
                <td>
                  {g.home.name} – {g.away.name}
                  <StageTag game={g} />
                </td>
                <td className="num">{fmt(g.features?.pred_total)}</td>
                {status === "finished" && <td className="num">{(g.home_score ?? 0) + (g.away_score ?? 0)}</td>}
                {FIELDS.map(([field]) => (
                  <td key={field} className="num">
                    <LineInput game={g} field={field} onSaved={() => {}} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pasteFor !== null && (
        <PasteOddsDialog games={games} startId={pasteFor} onClose={() => setPasteFor(null)} onSaved={reload} />
      )}
    </>
  );
}
