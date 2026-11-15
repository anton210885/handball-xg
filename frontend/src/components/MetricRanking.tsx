import { useEffect, useMemo, useState } from "react";
import { api, MetricRankResult, MetricVsLine } from "../api";

const r2 = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const signed = (v: number | null | undefined) => (v === null || v === undefined ? "–" : (v > 0 ? "+" : "") + r2(v));
const STEP = 50;
const ALL = "Alle gewählten Spiele";
const SEP = { borderLeft: "1px solid var(--border)" };

type Props = { ids: number[]; excludeErrors: boolean; target: string; minGames: number; onPick: (formula: string) => void };

/** Zelle „Metrik gegen Linie“ auf denselben Spielen: r oben, darunter r der Linie und Spielzahl. */
function VsCell({ c, bm, title }: { c: MetricVsLine | undefined; bm: string; title: string }) {
  if (!c || c.r === null) return <td className="muted" style={SEP} title={c ? `${title}: nur ${c.games} Spiele – zu wenig` : undefined}>–</td>;
  const stronger = c.r_line !== null && Math.abs(c.r) > c.r_line;
  const sure = stronger && c.beats_line_sure;
  return <td title={`${title}: ${c.games} Spiele · r Metrik ${r2(c.r)}, r ${bm} ${r2(c.r_line)}` + (c.z_vs_line !== null ? ` · z = ${r2(c.z_vs_line)}, p = ${r2(c.p_vs_line)}` : "")
    + ` · Mehrwert ${r2(c.added)}${c.added_sure ? " (sicher)" : ""}`}
    style={{ ...SEP, background: stronger ? "var(--good-soft)" : undefined, color: sure ? "var(--good)" : undefined, fontWeight: sure ? 700 : undefined }}>
    {r2(c.r)}{sure ? " ▲" : stronger ? <span className="muted" style={{ fontWeight: 400 }}> △</span> : ""}
    <div className="small muted" style={{ fontWeight: 400, fontStyle: "italic", whiteSpace: "nowrap" }}>{r2(c.r_line)} · {c.games}</div></td>;
}

/** Alle Metriken nach Korrelation mit dem Ergebnis, jede fair gegen die Over-Linie auf denselben Spielen. */
export default function MetricRanking({ ids, excludeErrors, target, minGames, onPick }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<MetricRankResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [onlyBetter, setOnlyBetter] = useState(false);
  const [shown, setShown] = useState(STEP);
  const [steps, setSteps] = useState(false);
  const [byLeague, setByLeague] = useState(false);
  const [group, setGroup] = useState(ALL);
  const [testSeason, setTestSeason] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"added" | "r">("added");
  const [onlyHolds, setOnlyHolds] = useState(false);
  const key = JSON.stringify([ids, excludeErrors, target, minGames, steps, byLeague, group, testSeason]);

  useEffect(() => {
    if (!open || !ids.length) return;
    let live = true;
    setBusy(true); setError("");
    api.goalRank(ids, excludeErrors, target, minGames, steps, group, byLeague, testSeason)
      .then(d => {
        if (!live) return;
        // Gruppe gibt es mit den neuen Filtern nicht mehr: zurück auf alle Spiele
        if (group !== ALL && !d.groups.some(g => g.label === group)) setGroup(ALL); else setData(d);
      })
      .catch(e => live && setError(e.message)).finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [key, open]);

  const list = useMemo(() => {
    if (!data) return [];
    const words = search.toLowerCase().split(/\s+/).filter(Boolean);
    // Mehrwert: ausgesucht wird nur nach den Lern-Saisons – die Prüf-Saison bleibt unberührt
    const addedKey = (m: typeof data.metrics[number]) => Math.abs((data.test_season ? m.added_train : m.added) ?? -1);
    const sorted = sortBy === "added" ? [...data.metrics].sort((a, b) => addedKey(b) - addedKey(a)) : data.metrics;
    return sorted.map((m, i) => ({ ...m, rank: i + 1 })).filter(m =>
      words.every(w => m.name.toLowerCase().includes(w) || m.label.toLowerCase().includes(w)) &&
      (!onlyBetter || (m.r !== null && m.r_line !== null && Math.abs(m.r) > m.r_line)) &&
      (!onlyHolds || !!m.holds));
  }, [data, search, onlyBetter, onlyHolds, sortBy]);

  const showSteps = steps && !!data && data.thresholds.length > 0 && data.metrics.some(m => m.by_min_games);
  const showLeagues = byLeague && !!data && data.leagues.length > 0 && data.metrics.some(m => m.by_league);
  const bm = data?.bookmaker_label ?? (target === "total" ? "Over-Linie" : target === "margin" ? "Handicap-Linie" : "Buchmacher");
  const groupLabel = (g: { label: string; games: number }) => {
    const depth = g.label === ALL ? 0 : g.label.split(" · ").length;
    return `${"  ".repeat(Math.max(0, depth - 1))}${g.label} (${g.games})`;
  };
  return <div className="panel">
    <h2>Alle Metriken im Vergleich {data && open ? `– ${data.target_label}${group !== ALL ? ` · ${group}` : ""}` : ""}</h2>
    {!open ? <div className="row">
      <button onClick={() => setOpen(true)}>Alle Metriken vergleichen</button>
      <span className="small muted">Rangliste aller Werte vor dem Spiel (auch _alt) nach Korrelation mit den Toren.</span>
    </div> : <>
      <div className="small muted" style={{ marginBottom: 6 }}>
        <b>Mehrwert</b> = weiß die Metrik etwas, das die {bm} noch nicht weiß? Gemessen als Korrelation der Metrik mit dem Teil des Ergebnisses,
        den die {bm} nicht erklärt (partielles r). 0 = nichts Neues; ab etwa ±0,05 bis ±0,10 wäre es für Wetten interessant.
        Ausgesucht wird nur nach den <b>Lern-Saisons</b>; die <b>Prüf-Saison</b> bleibt unberührt. <b>✓ hält</b> = auf der Prüf-Saison
        in dieselbe Richtung und dort selbst sicher – erst das ist ein echtes Zeichen.
      </div>
      <div className="small muted">
        r Metrik und r {bm}: Stärke des Zusammenhangs auf den Spielen, für die es auch die {bm} gibt.
        Negatives r heißt: hoher Wert = weniger Tore – genauso nützlich, nur umgekehrt.
        <b style={{ color: "var(--good)" }}> ▲</b> = sicher stärker als die {bm} (95 %), <span className="muted">△ = stärker, aber nicht sicher</span>.
        In den ausgeklappten Spalten oben r der Metrik, darunter r der {bm} und die Zahl der Spiele.
        Bei mehreren hundert Metriken und vielen Ligen sind einige △ und sogar ▲ reiner Zufall – erst glauben, wenn es in anderen Saisons hält.
        Klick auf einen Namen übernimmt ihn oben als Metrik.
        {minGames > 0 && ` Nur Spiele, vor denen beide Teams mindestens ${minGames} Spiele hatten.`}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label>Gruppe <select value={group} onChange={e => { setGroup(e.target.value); setShown(STEP); }}>
          {(data?.groups ?? [{ label: ALL, games: 0 }]).map(g => <option key={g.label} value={g.label}>{groupLabel(g)}</option>)}
        </select></label>
        <input placeholder="Suchen, z. B. expGoal oder _alt" value={search} onChange={e => { setSearch(e.target.value); setShown(STEP); }} style={{ minWidth: 220 }} />
        <label className="small"><input type="checkbox" checked={onlyBetter} onChange={e => { setOnlyBetter(e.target.checked); setShown(STEP); }} /> nur stärker als {bm}</label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label>Sortieren nach <select value={sortBy} onChange={e => { setSortBy(e.target.value as "added" | "r"); setShown(STEP); }}>
          <option value="added">Mehrwert (Lern-Saisons)</option><option value="r">Stärke r</option></select></label>
        {data && data.seasons.length > 1 && <label>Prüf-Saison <select value={data.test_season ?? ""} onChange={e => setTestSeason(e.target.value)}>
          {data.seasons.map(s => <option key={s} value={s}>{s}</option>)}</select></label>}
        {data?.test_season && <label className="small"><input type="checkbox" checked={onlyHolds} onChange={e => { setOnlyHolds(e.target.checked); setShown(STEP); }} /> nur „hält“</label>}
        {data && data.seasons.length < 2 && <span className="small muted">Für eine Prüf-Saison oben mindestens zwei Saisons wählen.</span>}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={() => setSteps(!steps)} title="Gleicher Vergleich nur mit Spielen, vor denen beide Teams mindestens so viele Spiele hatten">
          {steps ? "▾ Ab 5 / 10 / 15 / 20 Spielen zuklappen" : "▸ Ab 5 / 10 / 15 / 20 Spielen ausklappen"}</button>
        <button onClick={() => setByLeague(!byLeague)} title="Gleicher Vergleich je Liga und Geschlecht (innerhalb der gewählten Gruppe)">
          {byLeague ? "▾ Pro Liga und Geschlecht zuklappen" : "▸ Pro Liga und Geschlecht ausklappen"}</button>
        <button onClick={() => setOpen(false)}>Ausblenden</button>
        {busy && <span className="small muted">rechne …</span>}
        {data && <span className="small muted">{list.length} von {data.metrics.length} Metriken · {data.games} Spiele</span>}
      </div>
      {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
      {data && <div className="table-wrap" style={{ marginTop: 8 }}><table>
        <thead><tr><th>#</th><th>Metrik</th>
          {data.test_season && <><th style={SEP} title={`Mehrwert auf allen Saisons außer ${data.test_season} – danach wird sortiert`}>Mehrwert Lern-Saisons</th>
            <th title={`Mehrwert nur auf ${data.test_season} – war bei der Auswahl nicht dabei`}>Mehrwert {data.test_season}</th></>}
          <th style={data.test_season ? undefined : SEP} title="Mehrwert auf allen gewählten Saisons zusammen">Mehrwert alle</th>
          <th style={SEP}>Spiele mit {bm}</th><th>r Metrik</th><th>r {bm}</th><th>Unterschied</th>
          <th title="Korrelation auf allen Spielen mit diesem Wert, auch ohne Linie">r alle Spiele</th><th>Spiele</th>
          {showSteps && data.thresholds.map(t => <th key={t} style={SEP}
            title={`Nur Spiele, vor denen beide Teams mindestens ${t} Spiele hatten. Oben Metrik, darunter ${bm}.`}>ab {t} Sp.<div className="small muted">Metrik / {bm}</div></th>)}
          {showLeagues && data.leagues.map(lg => <th key={lg} style={{ ...SEP, whiteSpace: "normal", minWidth: 90 }}
            title={`${lg}: Oben Metrik, darunter ${bm}.`}>{lg}</th>)}</tr></thead>
        <tbody>{list.slice(0, shown).map(m => {
          const stronger = m.r !== null && m.r_line !== null && Math.abs(m.r) > m.r_line;
          const sure = stronger && m.beats_line_sure;
          const diff = m.r !== null && m.r_line !== null ? Math.abs(m.r) - m.r_line : null;
          const test = m.z_vs_line !== null ? `Vergleich mit ${bm}: z = ${r2(m.z_vs_line)}, p = ${r2(m.p_vs_line)}` : "";
          return <tr key={m.name}>
            <td className="muted">{m.rank}</td>
            <td title={m.label !== m.name ? m.label : undefined}>
              <a href="#" onClick={e => { e.preventDefault(); onPick(m.name); window.scrollTo({ top: 0, behavior: "smooth" }); }}>{m.name}</a>
              {m.label !== m.name && <div className="small muted">{m.label}</div>}</td>
            {data.test_season && <>
              <td style={{ ...SEP, fontWeight: m.added_train_sure ? 700 : undefined }}
                title={`${m.added_train_games ?? 0} Spiele${m.added_train_sure ? " · sicher ungleich 0" : " · kann Zufall sein"}`}>{signed(m.added_train)}{m.added_train_sure ? " ●" : ""}</td>
              <td title={`${m.added_test_games ?? 0} Spiele · p = ${r2(m.added_test_p)}`}
                style={{ background: m.holds ? "var(--good-soft)" : undefined, color: m.holds ? "var(--good)" : undefined, fontWeight: m.holds ? 700 : undefined }}>
                {signed(m.added_test)}{m.holds ? " ✓ hält" : ""}<div className="small muted" style={{ fontWeight: 400 }}>{m.added_test_games ?? 0} Sp.</div></td></>}
            <td style={{ ...(data.test_season ? {} : SEP), fontWeight: m.added_sure ? 700 : undefined }}
              title={`${m.added_games} Spiele · p = ${r2(m.added_p)}${m.added_sure ? " · sicher ungleich 0" : ""}`}>{signed(m.added)}{m.added_sure ? " ●" : ""}</td>
            <td style={SEP}>{m.games}</td>
            <td title={test} style={{ background: stronger ? "var(--good-soft)" : undefined, color: sure ? "var(--good)" : undefined, fontWeight: sure ? 700 : undefined }}>
              {r2(m.r)}{sure ? " ▲" : stronger ? <span className="muted" style={{ fontWeight: 400 }}> △</span> : ""}</td>
            <td style={{ fontStyle: "italic" }}>{r2(m.r_line)}</td>
            <td className={diff === null ? "" : diff > 0 ? "good" : "bad"}>{diff === null ? "–" : (diff > 0 ? "+" : "") + r2(diff)}</td>
            <td>{r2(m.r_all)}</td><td>{m.games_all}</td>
            {showSteps && data.thresholds.map(t => <VsCell key={t} bm={bm} title={`ab ${t} Spielen`} c={m.by_min_games?.find(x => x.min_games === t)} />)}
            {showLeagues && data.leagues.map(lg => <VsCell key={lg} bm={bm} title={lg} c={m.by_league?.find(x => x.league === lg)} />)}
          </tr>;
        })}</tbody>
      </table></div>}
      {list.length > shown && <div className="row" style={{ marginTop: 8 }}>
        <button onClick={() => setShown(shown + STEP)}>{Math.min(STEP, list.length - shown)} weitere zeigen</button>
        <button onClick={() => setShown(list.length)}>alle {list.length} zeigen</button></div>}
    </>}
  </div>;
}
