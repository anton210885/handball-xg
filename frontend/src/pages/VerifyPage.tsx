import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, MetricDetails, VerifyRow, VerifyStats } from "../api";
import ProfitCurve, { Sparkline } from "../components/ProfitCurve";
import VerifyGames, { GameMetrics } from "../components/VerifyGames";
import { dateTime, fmt, pct } from "../labels";
import { useLoad } from "../useLoad";

type SortKey = "profit" | "roi" | "hit_rate" | "settled" | "current_loss" | "max_loss" | "name";

/** Hintergrund nach Wert: bester Gewinn = kräftig grün, größter Verlust = kräftig rot, dazwischen abgestuft. */
function heat(v: number | null | undefined, maxPos: number, minNeg: number): React.CSSProperties {
  if (v === null || v === undefined || v === 0) return {};
  const share = v > 0 ? (maxPos > 0 ? v / maxPos : 0) : (minNeg < 0 ? v / minNeg : 0);
  const pctMix = Math.round(12 + 63 * Math.min(1, Math.max(0, share)));
  const color = v > 0 ? "var(--heat-pos)" : "var(--heat-neg)";
  return { background: `color-mix(in srgb, ${color} ${pctMix}%, var(--panel))`, color: pctMix > 50 ? "#fff" : undefined, fontWeight: 600 };
}

function Streak({ s }: { s: VerifyStats }) {
  if (!s.current_kind) return <span className="muted">–</span>;
  return s.current_kind === "loss"
    ? <span className="neg">{s.current} ohne Gewinn</span>
    : <span className="pos">{s.current} {s.current === 1 ? "Gewinn" : "Gewinne"}</span>;
}

export default function VerifyPage() {
  const data = useLoad(() => api.verifyOverview(), []);
  const meta = useLoad(() => api.meta(), []);
  const markets = meta.data?.markets ?? {};
  const details = meta.data?.feature_details ?? {};
  const [sort, setSort] = useState<SortKey>("profit");
  const [onlyWithPicks, setOnlyWithPicks] = useState(false);
  const location = useLocation();
  // Aus dem Strategie-Fenster der Prognosen: diese Strategie gleich aufklappen
  const [picked, setPicked] = useState<number | null>((location.state as any)?.strategyId ?? null);
  useEffect(() => {
    if (data.data && (location.state as any)?.strategyId) {
      setTimeout(() => document.querySelector("tr.selected")?.scrollIntoView({ block: "center" }), 50);
    }
  }, [data.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const rows = useMemo(() => {
    const list = (data.data?.strategies ?? []).filter((r) => !onlyWithPicks || r.picks > 0);
    const val = (r: VerifyRow): number => (sort === "name" ? 0 : (r[sort] as number | null) ?? -1e9);
    return [...list].sort((a, b) => (sort === "name" ? a.name.localeCompare(b.name) : val(b) - val(a) || a.name.localeCompare(b.name)));
  }, [data.data, sort, onlyWithPicks]);
  const maxPos = Math.max(0, ...rows.map((r) => r.profit));
  const minNeg = Math.min(0, ...rows.map((r) => r.profit));
  const roiPos = Math.max(0, ...rows.map((r) => r.roi ?? 0));
  const roiNeg = Math.min(0, ...rows.map((r) => r.roi ?? 0));
  const total = rows.reduce((a, r) => ({ picks: a.picks + r.picks, open: a.open + r.open, profit: a.profit + r.profit }), { picks: 0, open: 0, profit: 0 });

  const refresh = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.verifyRefresh();
      setMsg(`${r.added} neue Tipps, ${r.updated} aktualisiert, ${r.removed} entfernt`);
      await data.reload();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  const head = (key: SortKey, label: string, title?: string, num = true) => (
    <th className={`${num ? "num " : ""}sortable${sort === key ? " sorted" : ""}`} title={title} onClick={() => setSort(key)}>{label}{sort === key ? " ▾" : ""}</th>
  );

  return (
    <>
      <div className="panel">
        <h2>Verifikator</h2>
        <div className="small muted" style={{ marginBottom: 8 }}>
          Ab jetzt läuft jede gespeicherte Strategie mit, ohne Rückblick: Vor Anpfiff werden alle Spiele, auf die sie passt, als Tipp
          festgehalten – mit Linie und Quote von diesem Moment (alle 20 Minuten im Hintergrund, solange Handball xG läuft).
          Bis zum Anpfiff folgt der Tipp den aktuellen Linien; danach ist er eingefroren und wird nach dem Spiel abgerechnet.
          Serien: <b>ohne Gewinn</b> = verlorene Tipps in Folge, <b>Gewinne</b> = gewonnene in Folge; „zurück“ (Push) zählt nicht und unterbricht nicht.
        </div>
        <div className="row" style={{ gap: 12, alignItems: "center" }}>
          <button onClick={refresh} disabled={busy}>{busy ? "Suche …" : "Jetzt Tipps festhalten"}</button>
          <label className="small"><input type="checkbox" checked={onlyWithPicks} onChange={(e) => setOnlyWithPicks(e.target.checked)} /> nur Strategien mit Tipps</label>
          <span className="small muted">
            {msg ?? (data.data?.status.last_run ? `Zuletzt gesucht ${dateTime(data.data.status.last_run + "Z")}: ${data.data.status.message}` : "Noch nicht gesucht seit dem Start")}
          </span>
        </div>
      </div>

      <div className="panel table-wrap">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
          <h2 style={{ margin: 0 }}>Übersicht</h2>
          <span className="small muted">{total.picks} Tipps · {total.open} offen · Profit gesamt <b className={total.profit >= 0 ? "pos" : "neg"}>{fmt(total.profit, 2)}</b></span>
        </div>
        {data.error && <div className="error">{data.error}</div>}
        {data.loading && !data.data && <div className="muted small">Lade …</div>}
        <table className="verify-table">
          <thead>
            <tr>
              {head("name", "Strategie", undefined, false)}
              <th>Markt</th>
              {head("settled", "Tipps", "abgerechnet (offen)")}
              <th className="num">G / V / Z</th>
              {head("hit_rate", "Treffer")}
              <th className="num">Ø Quote</th>
              {head("profit", "Profit", "Einsatz der Strategie je Tipp")}
              {head("roi", "Rendite")}
              {head("current_loss", "aktuelle Serie", "laufende Serie ohne Gewinn bzw. mit Gewinn")}
              {head("max_loss", "max. ohne Gewinn")}
              <th className="num" title="Median der Serien ohne Gewinn">Median ohne Gewinn</th>
              <th className="num">max. Gewinne</th>
              <th className="num" title="Median der Gewinnserien">Median Gewinne</th>
              <th>Verlauf</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={picked === r.id ? "selected" : ""} onClick={() => setPicked(picked === r.id ? null : r.id)} style={{ cursor: "pointer" }}>
                <td>{r.name || <span className="muted">(ohne Namen)</span>}</td>
                <td className="small">{markets[r.market] ?? r.market}</td>
                <td className="num">{r.settled}{r.open ? <span className="muted"> ({r.open})</span> : null}</td>
                <td className="num">{r.wins} / {r.losses} / {r.pushes}</td>
                <td className="num">{pct(r.hit_rate)}</td>
                <td className="num">{fmt(r.avg_odds, 2)}</td>
                <td className="num" style={heat(r.profit, maxPos, minNeg)}>{r.settled ? fmt(r.profit, 2) : "–"}</td>
                <td className="num" style={heat(r.roi, roiPos, roiNeg)}>{pct(r.roi)}</td>
                <td className="num"><Streak s={r} /></td>
                <td className="num">{r.settled ? r.max_loss : "–"}</td>
                <td className="num">{fmt(r.median_loss, 1)}</td>
                <td className="num">{r.settled ? r.max_win : "–"}</td>
                <td className="num">{fmt(r.median_win, 1)}</td>
                <td><Sparkline values={r.curve} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.loading && rows.length === 0 && <div className="small muted">Keine Strategien gespeichert.</div>}
        <div className="small muted" style={{ marginTop: 6 }}>Zeile anklicken für den Verlauf und alle Tipps der Strategie. Spalten anklicken zum Sortieren.</div>
      </div>

      {picked !== null && <VerifyDetailPanel id={picked} markets={markets} details={details} />}

      <VerifyGames markets={markets} details={details} />
    </>
  );
}

function VerifyDetailPanel({ id, markets, details }: { id: number; markets: Record<string, string>; details: Record<string, MetricDetails> }) {
  const d = useLoad(() => api.verifyDetail(id), [id]);
  const [open, setOpen] = useState<number | null>(null);
  const x = d.data;
  const settled = (x?.picks ?? []).filter((p) => p.result);
  const points = settled.map((p) => ({
    y: p.cum ?? 0, label: dateTime(p.start),
    detail: `${p.home} – ${p.away} ${p.home_score}:${p.away_score} · ${p.result === "win" ? "gewonnen" : p.result === "push" ? "zurück" : "verloren"} ${fmt(p.profit, 2)}`,
  }));
  return (
    <div className="panel" id="verify-detail">
      <h2>{x?.name ?? "…"} <span className="muted small">· {x ? markets[x.market] ?? x.market : ""}</span></h2>
      {d.error && <div className="error">{d.error}</div>}
      {x && (
        <>
          <div className="kpis" style={{ marginBottom: 10 }}>
            <div className="kpi"><b>{x.settled}</b><span>abgerechnet{x.open ? ` · ${x.open} offen` : ""}</span></div>
            <div className="kpi"><b>{pct(x.hit_rate)}</b><span>Trefferquote</span></div>
            <div className="kpi"><b className={x.profit >= 0 ? "pos" : "neg"}>{fmt(x.profit, 2)}</b><span>Profit</span></div>
            <div className="kpi"><b className={(x.roi ?? 0) >= 0 ? "pos" : "neg"}>{pct(x.roi)}</b><span>Rendite</span></div>
            <div className="kpi"><b><Streak s={x} /></b><span>aktuelle Serie</span></div>
            <div className="kpi"><b>{x.max_loss} / {fmt(x.median_loss, 1)}</b><span>ohne Gewinn: max. / Median</span></div>
            <div className="kpi"><b>{x.max_win} / {fmt(x.median_win, 1)}</b><span>Gewinne: max. / Median</span></div>
          </div>
          <h3 style={{ margin: "6px 0" }}>Profit summiert</h3>
          <ProfitCurve points={points} />
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr><th>Spiel</th><th>Anpfiff</th><th className="num">Linie</th><th className="num">Quote</th><th className="num">Einsatz</th>
                  <th>Ergebnis</th><th className="num">Profit</th><th className="num">summiert</th><th>festgehalten</th></tr>
              </thead>
              <tbody>
                {[...x.picks].reverse().map((p) => (
                  <Fragment key={p.game_id}>
                  <tr className={open === p.game_id ? "selected" : ""} onClick={() => setOpen(open === p.game_id ? null : p.game_id)} style={{ cursor: "pointer" }}>
                    <td><Link to={`/spiele/${p.game_id}`} onClick={(e) => e.stopPropagation()}>{p.home} – {p.away}</Link></td>
                    <td className="small">{dateTime(p.start)}</td>
                    <td className="num">{fmt(p.line, 1)}</td>
                    <td className="num">{fmt(p.odds, 2)}</td>
                    <td className="num">{fmt(p.stake, 2)}</td>
                    <td>{p.result ? <>{p.home_score}:{p.away_score} <span className={p.result === "win" ? "tag good" : p.result === "loss" ? "tag bad" : "tag"}>
                      {p.result === "win" ? "gewonnen" : p.result === "loss" ? "verloren" : "zurück"}</span></> : <span className="muted">offen</span>}</td>
                    <td className={`num ${p.profit && p.profit > 0 ? "pos" : p.profit && p.profit < 0 ? "neg" : ""}`}>{fmt(p.profit, 2)}</td>
                    <td className="num">{fmt(p.cum, 2)}</td>
                    <td className="small muted">{dateTime(p.created_at + "Z")}</td>
                  </tr>
                  {open === p.game_id && <tr className="expanded"><td colSpan={9}><GameMetrics gameId={p.game_id} details={details} markets={markets} /></td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {x.picks.length === 0 && <div className="small muted">Noch keine Tipps – sobald ein kommendes Spiel passt, erscheint es hier.</div>}
            {x.picks.length > 0 && <div className="small muted" style={{ marginTop: 6 }}>Tipp anklicken für alle Metriken und Quoten des Spiels.</div>}
          </div>
        </>
      )}
    </div>
  );
}
