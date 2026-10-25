import { useState } from "react";
import { api, Game, Line } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";
import CoverageTable from "../components/CoverageTable";
import PasteOddsDialog from "../components/PasteOddsDialog";

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
  const [status, setStatus] = useState("open");
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

  const games = status === "finished" ? [...(data ?? [])].reverse() : data ?? [];
  const [pasteFor, setPasteFor] = useState<number | null>(null);

  return (
    <>
      <div className="topbar">
        <h1>Linien & Quoten</h1>
        <div className="row">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Offene Spiele</option>
            <option value="finished">Beendete Spiele (für Backtests)</option>
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
      <CoverageTable
        onPick={(id, st) => {
          setCompetitionId(id);
          setStatus(st);
        }}
      />
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
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
                  <button className="secondary" title="Quotentabelle einfügen" onClick={() => setPasteFor(g.id)}>
                    Einfügen
                  </button>
                </td>
                <td>{dateTime(g.start)}</td>
                <td>
                  {g.home.name} – {g.away.name}
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
