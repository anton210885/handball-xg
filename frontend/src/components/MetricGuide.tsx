import { useState } from "react";
import { Meta, MetricDetails } from "../api";

export function MetricInfo({ info }: { info?: MetricDetails }) {
  if (!info) return null;
  return <div className="note small" style={{ marginBottom: 12 }}>
    <b>{info.label}</b><p>{info.description}</p>
    <div><b>Berechnung:</b> <code>{info.formula}</code></div>
    <p><b>Datengrundlage:</b> {info.source}</p>
    <div><b>Zeitpunkt:</b> {info.timing}</div>
  </div>;
}

export default function MetricGuide({ meta }: { meta?: Meta | null }) {
  const [search, setSearch] = useState("");
  const docs = meta?.feature_details;
  if (!docs) return <div className="note small">Für die Metrikbeschreibungen und die neue Vor-Spiel-Berechnung bitte den Server über stop.vbs und start.vbs neu starten.</div>;
  const q = search.toLowerCase();
  const rows = Object.entries(docs).filter(([key,d]) => `${key} ${d.label} ${d.description} ${d.formula}`.toLowerCase().includes(q));
  return <details className="panel" style={{ marginBottom: 16 }}>
    <summary style={{ cursor: "pointer" }}><b>Metriken erklärt: Formeln, Herkunft und Zeitpunkt</b></summary>
    <p className="small">Heim/Gast bezeichnet die Rolle im betrachteten Spiel. Die Teamhistorie enthält alle früheren Heim- und Auswärtsspiele des Teams. Das aktuelle Ergebnis, Halbzeitstand und Würfe des Zielspiels sind keine Filtermerkmale; sie dienen erst später zur Bewertung der Wette.</p>
    <p className="small">Nur frühere Kalendertage zählen. Auch xG wird zeitlich fortlaufend und getrennt nach Liga und Geschlecht gelernt. Ohne Historie bleiben Teamprognosen leer. Quoten und Linien müssen als Pre-Match-Werte eingegeben sein; ihr ursprünglicher Erfassungszeitpunkt ist nicht historisch versioniert.</p>
    <input style={{ width: "100%", marginBottom: 10 }} placeholder="Metrik, alten Formelnamen oder Berechnung suchen …" value={search} onChange={e => setSearch(e.target.value)} />
    <div className="small muted">{rows.length} Metriken und historische Formelnamen</div>
    <div className="table-wrap" style={{ maxHeight: 520, overflowY: "auto" }}><table>
      <thead><tr><th>Metrik</th><th>Bedeutung und Berechnung</th><th>Herkunft / vor dem Spiel</th></tr></thead>
      <tbody>{rows.map(([key,d]) => <tr key={key}><td><b>{d.label}</b><br /><code>{key}</code></td><td>{d.description}<p><code>{d.formula}</code></p></td><td className="small">{d.source}<p>{d.timing}</p></td></tr>)}</tbody>
    </table></div>
  </details>;
}
