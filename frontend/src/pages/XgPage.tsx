import { useState } from "react";
import { api } from "../api";
import { ATTACK_LABEL, fmt, pct, ZONE_LABEL } from "../labels";
import { useLoad } from "../useLoad";

export default function XgPage() {
  const [shrinkage, setShrinkage] = useState(30);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const { data, error } = useLoad(() => api.xgModel(shrinkage), [shrinkage]);

  const apply = async () => {
    setBusy(true);
    try {
      await api.xgRecompute(shrinkage);
      setMsg(`xG mit k = ${shrinkage} für alle Würfe neu berechnet.`);
    } finally {
      setBusy(false);
    }
  };

  const zones = data ? Object.entries(data.zones as Record<string, any>).sort((a, b) => b[1].rate - a[1].rate) : [];

  return (
    <>
      <div className="topbar">
        <h1>xG-Modell</h1>
        <div className="row">
          <label className="small muted">Glättung k</label>
          <input type="range" min={0} max={150} step={5} value={shrinkage} onChange={(e) => setShrinkage(Number(e.target.value))} />
          <b style={{ width: 30 }}>{shrinkage}</b>
          <button disabled={busy} onClick={apply}>
            Übernehmen
          </button>
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {msg && <div className="note">{msg}</div>}

      <div className="panel small">
        <h2>So wird xG berechnet</h2>
        <p>
          Jeder Wurf bekommt die Torwahrscheinlichkeit seiner Kombination aus <b>Feldzone</b> und <b>Angriffsart</b>{" "}
          (Positionsangriff oder Umschalten: Gegenstoß, Durchbruch, schnelle Mitte), geschätzt aus allen Würfen der
          Datenbank. Seltene Kombinationen werden zur Zonen-Quote „geschrumpft“:
        </p>
        <p>
          <code>xG = (Tore + k · Zonen-Quote) / (Würfe + k)</code>
        </p>
        <p className="muted">
          Mit k = 0 zählt nur die rohe Quote, mit großem k fast nur die Zone. Liga-Schnitt: {data && pct(data.league.rate)} bei{" "}
          {data?.league.shots} Würfen. Die Vorschau unten ändert sich sofort; gespeichert wird erst mit „Übernehmen“.
        </p>
      </div>

      <div className="grid2">
        <div className="panel table-wrap">
          <h2>Zonen</h2>
          <table>
            <thead>
              <tr>
                <th>Zone</th>
                <th className="num">Würfe</th>
                <th className="num">Tore</th>
                <th className="num">Quote</th>
              </tr>
            </thead>
            <tbody>
              {zones.map(([z, c]) => (
                <tr key={z}>
                  <td>{ZONE_LABEL[z] ?? z}</td>
                  <td className="num">{c.shots}</td>
                  <td className="num">{c.goals}</td>
                  <td className="num">{pct(c.rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel table-wrap">
          <h2>Zone × Angriffsart</h2>
          <table>
            <thead>
              <tr>
                <th>Zone</th>
                <th>Angriff</th>
                <th className="num">Würfe</th>
                <th className="num">roh</th>
                <th className="num">xG</th>
              </tr>
            </thead>
            <tbody>
              {(data?.cells ?? []).map((c: any) => (
                <tr key={c.zone + c.attack}>
                  <td>{ZONE_LABEL[c.zone]}</td>
                  <td>{ATTACK_LABEL[c.attack]}</td>
                  <td className="num">{c.shots}</td>
                  <td className="num">{pct(c.raw_rate)}</td>
                  <td className="num">
                    <b>{fmt(c.xg, 3)}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
