import { useEffect, useRef, useState } from "react";
import { api, Game, PasteResult } from "../api";
import { dateTime, fmt } from "../labels";

/**
 * Quotentabelle einfügen: Text von einer Quotenseite (Over/Under, Handicap, 1X2) hineinkopieren,
 * Vorschau prüfen, übernehmen. Danach geht es direkt zum nächsten Spiel ohne Torlinie.
 */
export default function PasteOddsDialog({
  games,
  startId,
  onClose,
  onSaved,
}: {
  games: Game[];
  startId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [gameId, setGameId] = useState(startId);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<PasteResult | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<number[]>([]);
  const area = useRef<HTMLTextAreaElement>(null);
  const game = games.find((g) => g.id === gameId);

  useEffect(() => area.current?.focus(), [gameId]);

  // Vorschau kurz nach dem Einfügen/Tippen automatisch berechnen
  useEffect(() => {
    if (!text.trim()) return setPreview(null);
    const t = window.setTimeout(() => api.pasteOdds(gameId, text, false).then(setPreview).catch(() => {}), 300);
    return () => window.clearTimeout(t);
  }, [text, gameId]);

  const nextWithoutLine = (afterId: number, done: number[]) => {
    const i = games.findIndex((g) => g.id === afterId);
    return [...games.slice(i + 1), ...games.slice(0, i)].find(
      (g) => !done.includes(g.id) && (g.line?.over_line === null || g.line?.over_line === undefined),
    );
  };

  const save = async () => {
    const r = await api.pasteOdds(gameId, text, true);
    if (!r.saved) return setMessage("Nichts übernommen – es wurde keine Quote erkannt.");
    const done = [...savedIds, gameId];
    setSavedIds(done);
    onSaved();
    const next = nextWithoutLine(gameId, done);
    setMessage(`Gespeichert: ${game?.home.name} – ${game?.away.name}${next ? "" : ". Keine weiteren Spiele ohne Linie."}`);
    setText("");
    setPreview(null);
    if (next) setGameId(next.id);
  };

  if (!game) return null;
  const found = preview?.found ?? {};

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog panel" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>
            {game.home.name} – {game.away.name}
          </h2>
          <button className="secondary" onClick={onClose}>
            Schließen
          </button>
        </div>
        <div className="small muted" style={{ margin: "4px 0 10px" }}>
          {dateTime(game.start)} MSK
          {game.finished ? ` · Endstand ${game.home_score}:${game.away_score}` : ""}
          {game.line?.over_line ? ` · bisher Linie ${fmt(game.line.over_line)}` : " · noch keine Linie"}
          {savedIds.length ? ` · in diesem Fenster gespeichert: ${savedIds.length}` : ""}
        </div>
        <textarea
          ref={area}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"Tabelle hier einfügen (Strg+V): Over/Under, Asian Handicap und/oder 1X2 – auch alles zusammen.\nQuoten bitte als Dezimalquoten (z. B. 1.85)."}
          rows={8}
          style={{ width: "100%", fontFamily: "Consolas, monospace", fontSize: 12 }}
        />
        {message && <div className="note small">{message}</div>}

        {preview && (
          <div style={{ marginTop: 10 }}>
            <div className="kpis">
              <div className="kpi">
                <b>{fmt(found.over_line)}</b>
                <span>
                  Over-Linie {found.odds_over ? `(${fmt(found.odds_over, 2)} / ${fmt(found.odds_under, 2)})` : ""}
                </span>
              </div>
              <div className="kpi">
                <b>{found.hdp_line !== undefined ? (found.hdp_line > 0 ? "+" : "") + fmt(found.hdp_line) : "–"}</b>
                <span>Handicap Heim</span>
              </div>
              <div className="kpi">
                <b>
                  {found.odds_home ? `${fmt(found.odds_home, 2)} / ${fmt(found.odds_draw, 2)} / ${fmt(found.odds_away, 2)}` : "–"}
                </b>
                <span>1 / X / 2</span>
              </div>
            </div>
            {preview.warnings.map((w) => (
              <div key={w} className="error small">
                {w}
              </div>
            ))}
            {preview.lines.length > 0 && (
              <div className="small table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th className="num">Torlinie</th>
                      <th className="num">Over</th>
                      <th className="num">Under</th>
                      <th className="num" title="Wie viele Tabellenzeilen (Buchmacher oder Durchschnitt) zu dieser Linie gelesen wurden">
                        Zeilen
                      </th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.lines.map((l) => (
                      <tr key={l.line} style={l.line === found.over_line ? { fontWeight: 700 } : undefined}>
                        <td className="num">{fmt(l.line)}</td>
                        <td className="num">{fmt(l.a, 2)}</td>
                        <td className="num">{fmt(l.b, 2)}</td>
                        <td className="num">{l.count}</td>
                        <td>{l.line === found.over_line ? "← gewählt (1,70–2,00)" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        <div className="row" style={{ justifyContent: "flex-end", marginTop: 10 }}>
          <button disabled={!preview || Object.keys(found).length === 0} onClick={save}>
            Übernehmen und zum nächsten Spiel
          </button>
        </div>
      </div>
    </div>
  );
}
