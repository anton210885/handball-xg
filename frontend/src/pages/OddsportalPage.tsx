import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, OddsportalPage as PageData, OddsportalResult } from "../api";
import { dateTime, fmt } from "../labels";

const MARKET_LABEL: Record<string, string> = { "1X2": "1X2", "O/U": "Over/Under", AH: "Asian Handicap" };
const FIELD_LABEL: Record<string, string> = {
  over_line: "Torlinie", odds_over: "Over", odds_under: "Under", hdp_line: "Handicap Heim",
  odds_home: "1", odds_draw: "X", odds_away: "2",
};

// Gleicher Text wie im Tampermonkey-Skript (oddsportalScripts.ts)
const remainingText = (m: OddsportalResult["remaining"]) => {
  if (!m) return "";
  const parts = [m.line && `${m.line} Torlinien`, m.hdp && `${m.hdp} Handicaps`, m.x12 && `${m.x12}× 1X2`].filter(Boolean);
  return parts.length ? `Im Wettbewerb fehlen noch: ${parts.join(", ")}` : "Wettbewerb vollständig ✓";
};

// Empfängt die Seite vom Lesezeichen-Knopf (siehe OddsportalBookmarklet) und übernimmt die Quoten.
export default function OddsportalPage() {
  const [page, setPage] = useState<PageData | null>(null);
  const [result, setResult] = useState<OddsportalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const received = useRef(false);
  const openerOrigin = useRef<string | null>(null);

  // Rückmeldung als Kästchen auf der oddsportal-Seite; bei Erfolg schließt sich dieses Fenster
  const report = (ok: boolean, text: string) => {
    if (openerOrigin.current) window.opener?.postMessage({ type: "handball-xg-result", ok, text }, openerOrigin.current);
    if (ok) setTimeout(() => window.close(), 1200);
    else window.focus();
  };

  const run = async (data: PageData, gameId?: number) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.oddsportalImport(data, gameId);
      setResult(res);
      const l = res.game?.line;
      const n = (v: number | null | undefined) => (v == null ? "–" : String(v));
      if (res.saved && res.game) {
        report(true, [
          `✓ ${res.game.home.name} – ${res.game.away.name} (${dateTime(res.game.start)})`,
          `Linie ${n(l?.over_line)} (${n(l?.odds_over)}/${n(l?.odds_under)}) · HC ${n(l?.hdp_line)} · 1X2 ${n(l?.odds_home)}/${n(l?.odds_draw)}/${n(l?.odds_away)}`,
          ...res.warnings,
          remainingText(res.remaining),
        ].filter(Boolean).join("\n"));
      } else {
        report(false, ["Handball xG: Spiel nicht sicher erkannt – bitte im Tool-Fenster auswählen.", ...res.warnings].join("\n"));
      }
    } catch (e: any) {
      setError(e.message);
      report(false, `Handball xG: Fehler – ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const ok = /^https:\/\/([a-z0-9-]+\.)*oddsportal\.com$/.test(e.origin);
      if (!ok || received.current || e.data?.type !== "handball-xg-odds") return;
      received.current = true;
      openerOrigin.current = e.origin;
      const pages = Array.isArray(e.data.pages)
        ? e.data.pages.map((p: any) => ({ url: String(p.url ?? ""), text: String(p.text ?? ""), missing: p.missing ? String(p.missing) : undefined }))
        : undefined;
      const data: PageData = { text: String(e.data.text ?? ""), url: String(e.data.url ?? ""), pages,
        title: String(e.data.title ?? ""), tz_offset: Number(e.data.tz_offset) || 0 };
      setPage(data);
      run(data);
    };
    window.addEventListener("message", onMessage);
    // Nur ein Bereitschaftssignal ohne Daten – das Lesezeichen prüft die Herkunft dieses Fensters.
    // Wiederholt, bis Daten kommen: das Lesezeichen hört erst zu, wenn es alle Reiter gelesen hat.
    const ready = () => !received.current && window.opener?.postMessage("handball-xg-ready", "*");
    ready();
    const timer = window.setInterval(ready, 500);
    const stop = window.setTimeout(() => window.clearInterval(timer), 300000);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, []);

  const r = result;
  return (
    <>
      <div className="topbar">
        <h1>Quoten von oddsportal</h1>
        {window.opener && <button className="secondary" onClick={() => window.close()}>Fenster schließen</button>}
      </div>
      {!page && (
        <div className="note small">
          Diese Seite öffnet der Lesezeichen-Knopf von einer oddsportal-Spielseite aus. Den Knopf gibt es unter{" "}
          <Link to="/linien">Linien & Quoten</Link>.
        </div>
      )}
      {busy && <div className="note small">Lese Seite …</div>}
      {error && <div className="error">{error}</div>}
      {r && (
        <>
          <div className="panel">
            <h2>
              {r.home ?? "?"} – {r.away ?? "?"}
              {r.score ? ` ${r.score[0]}:${r.score[1]}` : ""}
            </h2>
            <div className="small muted">
              {r.league ?? "Liga unbekannt"} · {r.kickoff_local ? dateTime(r.kickoff_local) + " (deine Ortszeit)" : "Anstoß unbekannt"} ·
              Reiter {r.market ? r.market.split("+").map((m) => MARKET_LABEL[m] ?? m).join(", ") : "unbekannt"}
            </div>
            {Object.keys(r.found).length > 0 && (
              <div className="kpis" style={{ marginTop: 12 }}>
                {Object.entries(r.found).map(([k, v]) => (
                  <div className="kpi" key={k}>
                    <b>{k === "hdp_line" && v! > 0 ? "+" : ""}{fmt(v, 2)}</b>
                    <span>{FIELD_LABEL[k] ?? k}</span>
                  </div>
                ))}
              </div>
            )}
            {r.warnings.map((w) => (
              <div className="error small" key={w}>{w}</div>
            ))}
          </div>

          {r.game && (
            <div className={r.saved ? "note" : "panel"}>
              {r.saved ? "Gespeichert bei " : "Zugeordnet: "}
              <Link to={`/spiele/${r.game.id}`}>
                {r.game.home.name} – {r.game.away.name}
              </Link>{" "}
              <span className="small muted">
                {dateTime(r.game.start)} · {r.game.competition}
                {r.game.home_score !== null ? ` · ${r.game.home_score}:${r.game.away_score}` : ""}
              </span>
              {r.game.line && (
                <div className="small" style={{ marginTop: 6 }}>
                  Jetzt gespeichert: Torlinie {fmt(r.game.line.over_line, 2)} ({fmt(r.game.line.odds_over, 2)} /{" "}
                  {fmt(r.game.line.odds_under, 2)}) · Handicap {fmt(r.game.line.hdp_line, 2)} · 1X2{" "}
                  {fmt(r.game.line.odds_home, 2)} / {fmt(r.game.line.odds_draw, 2)} / {fmt(r.game.line.odds_away, 2)}
                </div>
              )}
              {r.saved && (() => {
                const l = r.game!.line;
                const missing = [
                  l?.over_line == null && "Over/Under",
                  l?.hdp_line == null && "Asian Handicap",
                  !(l?.odds_home && l?.odds_away) && "1X2",
                ].filter(Boolean);
                return (
                  <div className="small" style={{ marginTop: 6 }}>
                    {missing.length
                      ? <>Es wird nur der offene Reiter übernommen. Noch fehlt: <b>{missing.join(", ")}</b> – diesen Reiter auf oddsportal öffnen und den Knopf erneut drücken.</>
                      : "Alle Märkte gespeichert."}
                  </div>
                );
              })()}
            </div>
          )}

          {page && (
            <details className="panel table-wrap" open={!r.saved}>
              <summary style={{ cursor: "pointer", fontWeight: 600, marginBottom: 8 }}>
                {r.saved ? "Falsches Spiel? Anderes wählen" : r.candidates.length ? "Welches Spiel ist es?" : "Kein Spiel um diese Zeit gefunden"}
              </summary>
              {r.candidates.length > 0 && (
                <table>
                  <thead>
                    <tr>
                      <th>Anstoß</th><th>Spiel</th><th>Wettbewerb</th><th className="num">Ergebnis</th><th>Hinweise</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {r.candidates.map((c) => (
                      <tr key={c.id}>
                        <td>{dateTime(c.start)}</td>
                        <td>{c.home.name} – {c.away.name}</td>
                        <td className="small">{c.competition}</td>
                        <td className="num">{c.home_score !== null ? `${c.home_score}:${c.away_score}` : "–"}</td>
                        <td className="small muted">{c.reasons.join(", ")}</td>
                        <td>
                          <button disabled={busy || !Object.keys(r.found).length} onClick={() => run(page, c.id)}>
                            Dieses Spiel
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </details>
          )}
        </>
      )}
    </>
  );
}
