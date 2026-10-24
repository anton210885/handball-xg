import { useState } from "react";
import { api, Game, Line } from "../api";
import { useCompetition } from "../App";
import { dateTime, fmt } from "../labels";
import { useLoad } from "../useLoad";

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
  const initial = game.line?.[field] ?? "";
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
  const { competitionId, competitions } = useCompetition();
  const [status, setStatus] = useState("open");
  const { data, error, reload } = useLoad(() => api.games(competitionId, status || undefined), [competitionId, status]);
  const [oddsMsg, setOddsMsg] = useState<string | null>(null);
  const comp = competitions.find((c) => c.id === competitionId);

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

  return (
    <>
      <div className="topbar">
        <h1>Linien & Quoten</h1>
        <div className="row">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Offene Spiele</option>
            <option value="finished">Beendete Spiele (für Backtests)</option>
          </select>
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
      </div>
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
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
              <tr key={g.id}>
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
    </>
  );
}
