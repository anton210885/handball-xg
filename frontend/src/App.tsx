import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { api, Competition } from "./api";
import ImportPage from "./pages/ImportPage";
import GamesPage from "./pages/GamesPage";
import GameDetailPage from "./pages/GameDetailPage";
import TeamsPage from "./pages/TeamsPage";
import XgPage from "./pages/XgPage";
import LinesPage from "./pages/LinesPage";
import StrategiesPage from "./pages/StrategiesPage";
import PredictionsPage from "./pages/PredictionsPage";

type CompCtx = {
  competitions: Competition[];
  competitionId: number | undefined;
  setCompetitionId: (id: number) => void;
  reload: () => void;
};

const CompetitionContext = createContext<CompCtx>({
  competitions: [],
  competitionId: undefined,
  setCompetitionId: () => {},
  reload: () => {},
});
export const useCompetition = () => useContext(CompetitionContext);

function readStoredId(): number | undefined {
  try {
    const v = localStorage.getItem("competitionId");
    return v ? Number(v) : undefined;
  } catch {
    return undefined;
  }
}

export default function App() {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [competitionId, setId] = useState<number | undefined>(readStoredId);
  const [error, setError] = useState<string | null>(null);

  const reload = () =>
    api
      .competitions()
      .then((c) => {
        setCompetitions(c);
        setError(null);
        // Ohne gespeicherte Auswahl die neueste Saison mit den meisten Spielen nehmen
        const newest = [...c].sort((a, b) => b.season.localeCompare(a.season) || b.games - a.games)[0];
        if ((!competitionId || !c.some((x) => x.id === competitionId)) && newest) setId(newest.id);
      })
      .catch((e) => setError(`Backend nicht erreichbar: ${e.message}`));

  useEffect(() => {
    reload();
  }, []);

  const setCompetitionId = (id: number) => {
    setId(id);
    try {
      localStorage.setItem("competitionId", String(id));
    } catch {
      /* egal */
    }
  };

  const links = [
    ["/", "Prognosen"],
    ["/spiele", "Spiele"],
    ["/linien", "Linien & Quoten"],
    ["/strategien", "Strategien"],
    ["/teams", "Teams"],
    ["/xg", "xG-Modell"],
    ["/import", "Daten-Import"],
  ];

  return (
    <CompetitionContext.Provider value={{ competitions, competitionId, setCompetitionId, reload }}>
      <div className="layout">
        <aside className="sidebar">
          <div className="brand">
            Handball xG <small>Statistik · xG · Strategien</small>
          </div>
          <nav className="nav">
            {links.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div style={{ marginTop: 20, padding: "0 8px" }}>
            <div className="small muted" style={{ marginBottom: 4 }}>
              Wettbewerb
            </div>
            <select
              style={{ width: "100%" }}
              value={competitionId ?? ""}
              onChange={(e) => setCompetitionId(Number(e.target.value))}
            >
              {competitions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.season} · {c.name}
                </option>
              ))}
            </select>
          </div>
        </aside>
        <main className="main">
          {error && <div className="error">{error}</div>}
          <Routes>
            <Route path="/" element={<PredictionsPage />} />
            <Route path="/spiele" element={<GamesPage />} />
            <Route path="/spiele/:id" element={<GameDetailPage />} />
            <Route path="/linien" element={<LinesPage />} />
            <Route path="/strategien" element={<StrategiesPage />} />
            <Route path="/teams" element={<TeamsPage />} />
            <Route path="/xg" element={<XgPage />} />
            <Route path="/import" element={<ImportPage />} />
          </Routes>
        </main>
      </div>
    </CompetitionContext.Provider>
  );
}
