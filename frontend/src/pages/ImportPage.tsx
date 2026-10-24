import { useEffect, useState } from "react";
import { api } from "../api";
import { useCompetition } from "../App";

export default function ImportPage() {
  const { competitions, reload } = useCompetition();
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.importStatus>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ id: "", name: "", season: "", gender: "men" });

  // Fortschritt abfragen, solange ein Import läuft
  useEffect(() => {
    let timer: number | undefined;
    const poll = () =>
      api.importStatus().then((s) => {
        setStatus(s);
        if (s.running) timer = window.setTimeout(poll, 1000);
        else reload();
      });
    poll();
    return () => window.clearTimeout(timer);
  }, []);

  const start = async (id: number, reimport = false) => {
    setError(null);
    try {
      await api.startImport(id, reimport);
      const poll = () =>
        api.importStatus().then((s) => {
          setStatus(s);
          if (s.running) window.setTimeout(poll, 1000);
          else reload();
        });
      poll();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const add = async () => {
    setError(null);
    try {
      await api.addCompetition({ ...form, id: Number(form.id) });
      setForm({ id: "", name: "", season: "", gender: "men" });
      reload();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const patchHapi = (
    id: number,
    field: "handballapi_tournament_id" | "handballapi_season_id" | "previous_competition_id",
    value: string,
  ) =>
    api.patchCompetition(id, { [field]: value ? Number(value) : null }).then(reload);

  return (
    <>
      <div className="topbar">
        <h1>Daten-Import</h1>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="note">
        Quelle ist <a href="https://rushandball.ru/superleague_26-27" target="_blank">rushandball.ru</a>. Der Import lädt den
        Spielplan und für jedes beendete Spiel den Spielverlauf mit allen Würfen (Feldzone, Torzone, Angriffsart).
        Bereits geladene Spiele werden übersprungen; die Rohdaten liegen zusätzlich in <code>backend/data/raw</code>.
      </div>

      {status && (status.running || status.message) && (
        <div className="panel">
          <h2>{status.running ? "Import läuft …" : "Letzter Import"}</h2>
          <div className="muted">{status.message}</div>
          {status.total > 0 && (
            <>
              <div className="progress">
                <div style={{ width: `${(100 * status.done) / status.total}%` }} />
              </div>
              <div className="small muted">
                {status.done} / {status.total} Spiele
              </div>
            </>
          )}
          {status.errors?.length > 0 && <div className="error">{status.errors.join(" · ")}</div>}
        </div>
      )}

      <div className="panel table-wrap">
        <h2>Wettbewerbe</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Saison</th>
              <th>Name</th>
              <th className="num">Spiele</th>
              <th className="num">beendet</th>
              <th className="num">mit Würfen</th>
              <th>Letzter Import</th>
              <th title="Deren Spiele fließen gewichtet in die Team-Werte ein, solange ein Team erst wenige Spiele hat">
                Vorsaison-ID
              </th>
              <th>HandballAPI Turnier / Saison</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {competitions.map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.season}</td>
                <td>{c.name}</td>
                <td className="num">{c.games}</td>
                <td className="num">{c.finished}</td>
                <td className="num">{c.with_shots}</td>
                <td>{c.last_import ? new Date(c.last_import + "Z").toLocaleString("de-DE") : "–"}</td>
                <td>
                  <select
                    defaultValue={c.previous_competition_id ?? ""}
                    onChange={(e) => patchHapi(c.id, "previous_competition_id", e.target.value)}
                  >
                    <option value="">keine</option>
                    {competitions
                      .filter((o) => o.id !== c.id)
                      .map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.season} · {o.id}
                        </option>
                      ))}
                  </select>
                </td>
                <td>
                  <input
                    className="cell"
                    defaultValue={c.handballapi_tournament_id ?? ""}
                    onBlur={(e) => patchHapi(c.id, "handballapi_tournament_id", e.target.value)}
                  />{" "}
                  <input
                    className="cell"
                    style={{ width: 90 }}
                    defaultValue={c.handballapi_season_id ?? ""}
                    onBlur={(e) => patchHapi(c.id, "handballapi_season_id", e.target.value)}
                  />
                </td>
                <td className="row">
                  <button disabled={status?.running} onClick={() => start(c.id)}>
                    Importieren
                  </button>
                  <button className="secondary" disabled={status?.running} onClick={() => start(c.id, true)}>
                    Alles neu
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>Wettbewerb hinzufügen</h2>
        <p className="small muted">
          Die ID findest du auf rushandball.ru in den Netzwerkanfragen der Ligaseite (z. B. <code>GetCompGames/8070</code>).
        </p>
        <div className="row">
          <input placeholder="ID, z. B. 8070" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
          <input placeholder="Saison, z. B. 25/26" value={form.season} onChange={(e) => setForm({ ...form, season: e.target.value })} />
          <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
            <option value="men">Männer</option>
            <option value="women">Frauen</option>
          </select>
          <button disabled={!form.id || !form.name} onClick={add}>
            Hinzufügen
          </button>
        </div>
      </div>
    </>
  );
}
