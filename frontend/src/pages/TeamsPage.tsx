import { api } from "../api";
import { useCompetition } from "../App";
import { fmt } from "../labels";
import { useLoad } from "../useLoad";

const signed = (v: number | null | undefined) => (
  <span className={v && v > 0 ? "pos" : v && v < 0 ? "neg" : ""}>{v && v > 0 ? "+" : ""}{fmt(v)}</span>
);

export default function TeamsPage() {
  const { competitionId } = useCompetition();
  const { data, error } = useLoad(() => api.teams(competitionId), [competitionId]);

  return (
    <>
      <div className="topbar">
        <h1>Teams</h1>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="note small">
        Werte pro Spiel. <b>Abschluss</b> = Tore − xG (positiv: trifft besser als erwartet).{" "}
        <b>Torwart</b> = xG gegen − Gegentore (positiv: Torhüter halten mehr als erwartet). Beides schwankt stark und
        gleicht sich oft wieder aus – ein Hinweis für Strategien.
      </div>
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Team</th>
              <th className="num">Spiele</th>
              <th className="num">Tore</th>
              <th className="num">Gegentore</th>
              <th className="num">xG</th>
              <th className="num">xG gegen</th>
              <th className="num">xG-Diff.</th>
              <th className="num">Abschluss</th>
              <th className="num">Torwart</th>
              <th className="num">Ø Tore gesamt</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td className="num">{t.games}</td>
                <td className="num">{fmt(t.goals)}</td>
                <td className="num">{fmt(t.goals_against)}</td>
                <td className="num">{fmt(t.xg)}</td>
                <td className="num">{fmt(t.xga)}</td>
                <td className="num">{signed(t.xg - t.xga)}</td>
                <td className="num">{signed(t.finishing)}</td>
                <td className="num">{signed(t.keeper)}</td>
                <td className="num">{fmt(t.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
