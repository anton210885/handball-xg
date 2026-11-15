import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, Competition } from "./api";
import ImportPage from "./pages/ImportPage";
import GamesPage from "./pages/GamesPage";
import GameDetailPage from "./pages/GameDetailPage";
import TeamsPage from "./pages/TeamsPage";
import XgPage from "./pages/XgPage";
import LinesPage from "./pages/LinesPage";
import StrategiesPage from "./pages/StrategiesPage";
import GoalCorrelationPage from "./pages/GoalCorrelationPage";
import AnalysisPage from "./pages/AnalysisPage";
import PredictionsPage from "./pages/PredictionsPage";
import OddsportalPage from "./pages/OddsportalPage";
import VerifyPage from "./pages/VerifyPage";
import DataCheckPage from "./pages/DataCheckPage";
import { useAuth } from "./AuthGate";

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
  const [version, setVersion] = useState<string | null>(null);
  const auth = useAuth();

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
    fetch("/api/version")
      .then((r) => r.json())
      .then((v) => setVersion(v.version))
      .catch(() => {});
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
    ["/verifikator", "Verifikator"],
    ["/analyse", "Metriken & Profit"],
    ["/korrelation", "Korrelation Tore"],
    ["/teams", "Teams"],
    ["/datenpruefung", "Datenprüfung"],
    ["/xg", "xG-Modell"],
    ["/import", "Daten-Import"],
  ];

  // Handy: Menü einklappbar, schließt nach jedem Seitenwechsel
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);
  const current = links.find(([to]) => (to === "/" ? location.pathname === "/" : location.pathname.startsWith(to)))?.[1] ?? "";
  const comp = competitions.find((c) => c.id === competitionId);

  return (
    <CompetitionContext.Provider value={{ competitions, competitionId, setCompetitionId, reload }}>
      <div className="layout">
        <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
          <div className="mobile-bar">
            <button className="menu-btn" aria-label="Menü" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
              {menuOpen ? "✕" : "☰"}
            </button>
            <div className="mobile-title">
              <b>{current || "Handball xG"}</b>
              {comp && <span className="muted">{comp.season} · {comp.name}</span>}
            </div>
          </div>
          <div className="sidebar-body">
          <div className="brand">
            Handball xG <small>Statistik · xG · Strategien{version ? ` · v${version}` : ""}</small>
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
          {auth.required && (
            <div style={{ marginTop: 16, padding: "0 8px" }}>
              <button className="secondary" style={{ width: "100%" }} onClick={auth.logout}>Abmelden</button>
            </div>
          )}
          </div>
        </aside>
        {menuOpen && <div className="menu-backdrop" onClick={() => setMenuOpen(false)} />}
        <main className="main">
          {error && <div className="error">{error}</div>}
          <Routes>
            <Route path="/" element={<PredictionsPage />} />
            <Route path="/spiele" element={<GamesPage />} />
            <Route path="/spiele/:id" element={<GameDetailPage />} />
            <Route path="/linien" element={<LinesPage />} />
            <Route path="/strategien" element={<StrategiesPage />} />
            <Route path="/verifikator" element={<VerifyPage />} />
            <Route path="/analyse" element={<AnalysisPage />} />
            <Route path="/korrelation" element={<GoalCorrelationPage />} />
            <Route path="/teams" element={<TeamsPage />} />
            <Route path="/datenpruefung" element={<DataCheckPage />} />
            <Route path="/xg" element={<XgPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/oddsportal" element={<OddsportalPage />} />
          </Routes>
        </main>
      </div>
    </CompetitionContext.Provider>
  );
}
