import { useEffect, useState } from "react";
import { api, MetricCompareResult } from "../api";

const r2 = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const FEW = 30;
const THRESHOLDS = [5, 10, 15, 20];

type Formulas = { name: string; formula: string }[];
type Props = { ids: number[]; excludeErrors: boolean; target: string; minGames: number; formulas: Formulas };

/** Lädt den Vergleich für eine Mindestspielzahl, sobald ``active`` ist. */
function useCompare(active: boolean, ids: number[], excludeErrors: boolean, target: string, minGames: number, formulas: Formulas, split: boolean) {
  const [data, setData] = useState<MetricCompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = JSON.stringify([ids, excludeErrors, target, minGames, formulas, split]);
  useEffect(() => {
    if (!active) return;
    if (!ids.length || !formulas.length) { setData(null); return; }
    let live = true;
    setBusy(true); setError("");
    api.goalCompare(ids, excludeErrors, target, minGames, formulas, split)
      .then(d => live && setData(d)).catch(e => live && setError(e.message)).finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [key, active]);
  return { data, busy, error };
}

/** Tabelle: Gruppen als Zeilen, Metriken und Linie als Spalten. */
function CompareTable({ data }: { data: MetricCompareResult }) {
  return <div className="table-wrap" style={{ marginTop: 8 }}><table>
    <thead><tr><th>Gruppe</th><th>Spiele</th>{data.columns.map((c, i) => <th key={i} title={data.formulas[i] ?? c}
      style={{ fontStyle: i === data.bookmaker_index ? "italic" : undefined, whiteSpace: "normal", minWidth: 90 }}>{c}</th>)}</tr></thead>
    <tbody>{data.rows.map(row => {
      const line = row.cells[data.bookmaker_index]?.r ?? null;
      const metricRs = row.cells.slice(0, data.bookmaker_index).map(c => c.r ?? -2);
      const best = Math.max(...metricRs);
      const indent = row.kind === "country_gender" ? 24 : row.kind === "all" ? 0 : 10;
      return <tr key={row.label} style={{ fontWeight: row.kind === "all" ? 600 : undefined }}>
        <td style={{ paddingLeft: indent }}>{row.label}</td>
        <td className={row.games < FEW ? "muted" : ""} title={row.games < FEW ? "Wenige Spiele – Werte schwanken stark" : undefined}>{row.games}{row.games < FEW ? " ⚠" : ""}</td>
        {row.cells.map((c, i) => {
          const range = `r = ${r2(c.r)} (Zufallsbereich ${r2(c.r_low)} bis ${r2(c.r_high)}) · Ø Abweichung ${r2(c.mae)} Tore`;
          if (i === data.bookmaker_index) return <td key={i} style={{ fontStyle: "italic" }} title={range}>{r2(c.r)}</td>;
          const isBest = c.r !== null && c.r === best;
          const higher = c.r !== null && line !== null && c.r > line;
          const sure = higher && !!c.beats_line_sure;
          const test = c.z_vs_line != null ? ` · Vergleich mit Linie: z = ${r2(c.z_vs_line)}, p = ${r2(c.p_vs_line)}${sure ? " → sicher besser" : higher ? " → nicht sicher (Zufall möglich)" : ""}` : "";
          return <td key={i} title={range + test}
            style={{ background: isBest ? "var(--good-soft)" : undefined, color: sure ? "var(--good)" : undefined, fontWeight: sure || isBest ? 700 : undefined }}>
            {r2(c.r)}{sure ? " ▲" : higher ? <span className="muted" style={{ fontWeight: 400 }}> △</span> : ""}</td>;
        })}
      </tr>;
    })}</tbody>
  </table></div>;
}

/** Ein- und ausklappbarer Abschnitt: derselbe Vergleich nur mit Spielen ab ``t`` gespielten Spielen beider Teams. */
function ThresholdSection({ t, ids, excludeErrors, target, formulas, split }: Omit<Props, "minGames"> & { t: number; split: boolean }) {
  const [open, setOpen] = useState(false);
  const { data, busy, error } = useCompare(open, ids, excludeErrors, target, t, formulas, split);
  const games = data?.rows[0]?.games;
  return <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
    <button onClick={() => setOpen(!open)} style={{ fontWeight: 600 }}>
      {open ? "▾" : "▸"} Ab {t} Spielen beider Teams{open && games !== undefined ? ` – ${games} Spiele` : ""}</button>
    {open && busy && <span className="small muted" style={{ marginLeft: 8 }}>rechne …</span>}
    {open && error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
    {open && data && <CompareTable data={data} />}
  </div>;
}

/** Metriken und Over-Linie nebeneinander (r zum Ergebnis, gleiche Spiele je Zeile); auf Wunsch nach Geschlecht und Land aufgeteilt
 *  und zusätzlich ab 5 / 10 / 15 / 20 gespielten Spielen (je Abschnitt ein- und ausklappbar). */
export default function MetricCompare({ ids, excludeErrors, target, minGames, formulas }: Props) {
  const [split, setSplit] = useState(false);
  const [openAll, setOpenAll] = useState(0);  // erhöhen = alle Abschnitte neu aufbauen (geschlossen)
  const { data, busy, error } = useCompare(true, ids, excludeErrors, target, minGames, formulas, split);
  const thresholds = THRESHOLDS.filter(t => t > minGames);
  const bm = target === "total" ? "Over-Linie" : target === "margin" ? "Handicap-Linie" : "Buchmacher-Erwartung";

  return <div className="panel">
    <h2>Metriken im Vergleich {data ? `– ${data.target_label}` : ""}</h2>
    <div className="small muted">
      Jede Zelle: Korrelation r mit den erzielten Toren. Je Zeile nur Spiele, bei denen alle Metriken und die {bm} vorhanden sind – so ist der Vergleich fair.
      <span style={{ background: "var(--good-soft)", padding: "0 6px", borderRadius: 4, marginLeft: 6 }}>grün</span> = beste Metrik der Zeile,
      <b style={{ color: "var(--good)" }}> ▲</b> = sicher besser als die {bm} (Vorsprung größer als der Zufall, 95 %),
      <span className="muted"> △ = höher, aber nicht sicher</span> (kann Zufall sein). Maus über eine Zelle zeigt den Zufallsbereich von r.
      Bei so vielen Vergleichen ist auch ein einzelnes ▲ in einer kleinen Gruppe noch kein Beweis – erst wenn es sich in anderen Saisons wiederholt.
      {minGames > 0 && ` Nur Spiele, vor denen beide Teams mindestens ${minGames} Spiele hatten.`}
      {thresholds.length > 0 && " Darunter derselbe Vergleich ab " + thresholds.join(" / ") + " Spielen – zum Ausklappen."}
    </div>
    {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
    {data && <CompareTable data={data} />}
    <div className="row" style={{ marginTop: 8 }}>
      <button onClick={() => setSplit(!split)}>{split ? "Aufteilung ausblenden" : "Aufteilen: Männer / Frauen und je Land"}</button>
      {thresholds.length > 0 && <button onClick={() => setOpenAll(openAll + 1)} title="Alle Abschnitte ab 5 / 10 / 15 / 20 Spielen zuklappen">Alle zuklappen</button>}
      {busy && <span className="small muted">rechne …</span>}
    </div>
    <div key={openAll}>
      {thresholds.map(t => <ThresholdSection key={t} t={t} ids={ids} excludeErrors={excludeErrors} target={target} formulas={formulas} split={split} />)}
    </div>
  </div>;
}
