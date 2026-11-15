import { useMemo, useState } from "react";
import { favoriteRank, isFavorite, isTotalMarket } from "../favorites";

/** Bedingungen einer Strategie als Auswahlfelder statt Formeltext.
 *  Gespeichert wird weiter die Formel (z. B. „(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) - 3 > over“);
 *  was sich nicht in Felder zerlegen lässt, bleibt als Text editierbar. */

export const OPS = [">", ">=", "<", "<=", "==", "!="] as const;
const OP_LABEL: Record<string, string> = { ">": "größer als", ">=": "mindestens", "<": "kleiner als", "<=": "höchstens", "==": "gleich", "!=": "ungleich" };
const OP_SIGN: Record<string, string> = { ">": ">", ">=": "≥", "<": "<", "<=": "≤", "==": "=", "!=": "≠" };

/** Verständliche Namen für die häufigsten alten Formelnamen (sonst Beschriftung aus den Metrik-Erklärungen). */
const FRIENDLY: Record<string, string> = {
  over: "Over-Linie", hdp: "Handicap Heim", home: "Quote Heimsieg", away: "Quote Auswärtssieg", draw: "Quote Remis",
  tour: "Spieltag (40 = KO-Spiel)", sex: "Geschlecht",
  homeExpGoal_with_GK_power: "Erw. Tore Heim mit Abschluss/Torwart (GK_power)",
  awayExpGoal_with_GK_power: "Erw. Tore Gast mit Abschluss/Torwart (GK_power)",
  homeExpGoal_with_GK: "Erw. Tore Heim mit Torwart", awayExpGoal_with_GK: "Erw. Tore Gast mit Torwart",
  home_expGoal: "Erw. Tore Heim (xG)", away_expGoal: "Erw. Tore Gast (xG)",
  Home_avgXG: "Ø xG Heim", Away_avgXG: "Ø xG Gast",
  home_Last_5_XG_Median: "xG-Median Heim, letzte 5", away_Last_5_XG_Median: "xG-Median Gast, letzte 5",
  last5_Games_homeExpGoal_with_GK: "Erw. Tore Heim mit Torwart, letzte 5", last5_Games_awayExpGoal_with_GK: "Erw. Tore Gast mit Torwart, letzte 5",
  difference_expGoals_with_GK_power: "Erw. Tordifferenz Heim − Gast (GK_power)",
  difference_expGoals_with_GK: "Erw. Tordifferenz Heim − Gast (mit Torwart)",
  difference_expGoal: "Erw. Tordifferenz Heim − Gast (xG)",
  last5_Games_difference_expGoals_with_GK: "Erw. Tordifferenz mit Torwart, letzte 5",
  Sum_expGoal_with_GK_power: "Erw. Tore gesamt (GK_power)",
};

export type NameInfo = { label: string; description?: string };
export type Names = Record<string, NameInfo>;

export function nameLabel(name: string, names: Names) {
  return FRIENDLY[name] ?? (names[name]?.label && names[name].label !== name ? names[name].label : name);
}

/** Gegenstück Heim ↔ Gast, z. B. homeExpGoal_with_GK_power → awayExpGoal_with_GK_power. */
export function counterpart(name: string): string | null {
  if (/home/.test(name)) return name.replace("home", "away");
  if (/Home/.test(name)) return name.replace("Home", "Away");
  return null;
}

/** Name ohne Heim/Gast, für die Anzeige als Paar. */
function pairLabel(name: string, names: Names) {
  return nameLabel(name, names).replace(/\b(Heim|Heimteam)\b,?\s*/g, "").replace(/\s{2,}/g, " ").trim() + " (Heim + Gast)";
}

export type Compare = { kind: "compare"; metric: string; pair: boolean; offset: number; op: string; right: { type: "name"; name: string } | { type: "number"; value: number } };
export type Gender = { kind: "gender"; value: "men" | "women"; op: "==" | "!=" };
export type Parsed = Compare | Gender;

// ---------- Formel ↔ Felder ----------

type Tok = { t: "name" | "num" | "str" | "op" | "sym"; v: string };

function tokenize(text: string): Tok[] | null {
  const out: Tok[] = [];
  const re = /\s*(?:([A-Za-z_]\w*)|(\d+(?:\.\d+)?)|'([^']*)'|"([^"]*)"|(>=|<=|==|!=|>|<)|([()+\-]))/y;
  let i = 0;
  while (i < text.length) {
    if (/^\s*$/.test(text.slice(i))) break;
    re.lastIndex = i;
    const m = re.exec(text);
    if (!m) return null;
    i = re.lastIndex;
    if (m[1]) out.push({ t: "name", v: m[1] });
    else if (m[2]) out.push({ t: "num", v: m[2] });
    else if (m[3] !== undefined || m[4] !== undefined) out.push({ t: "str", v: (m[3] ?? m[4]) as string });
    else if (m[5]) out.push({ t: "op", v: m[5] });
    else out.push({ t: "sym", v: m[6] });
  }
  return out;
}

/** Zerlegt die häufigen Formen: „sex == 'men'“, „Name op Zahl“, „(Heim + Gast) ± Zahl op Name/Zahl“. Sonst null. */
export function parseFormula(text: string): Parsed | null {
  const toks = tokenize(text);
  if (!toks || !toks.length) return null;
  const opAt = toks.findIndex((x) => x.t === "op");
  if (opAt < 1 || toks.filter((x) => x.t === "op").length !== 1) return null;
  const left = toks.slice(0, opAt), rightToks = toks.slice(opAt + 1), op = toks[opAt].v;

  if (left.length === 1 && left[0].v === "sex" && rightToks.length === 1 && rightToks[0].t === "str"
      && (op === "==" || op === "!=") && (rightToks[0].v === "men" || rightToks[0].v === "women")) {
    return { kind: "gender", value: rightToks[0].v as "men" | "women", op };
  }

  // rechte Seite: Name oder (negative) Zahl
  let right: Compare["right"];
  if (rightToks.length === 1 && rightToks[0].t === "name") right = { type: "name", name: rightToks[0].v };
  else if (rightToks.length === 1 && rightToks[0].t === "num") right = { type: "number", value: Number(rightToks[0].v) };
  else if (rightToks.length === 2 && rightToks[0].v === "-" && rightToks[1].t === "num") right = { type: "number", value: -Number(rightToks[1].v) };
  else return null;

  // linke Seite: [ ( ] a [ + b ] [ ) ] [ ± Zahl ]
  let rest = [...left];
  let offset = 0;
  const n = rest.length;
  if (n >= 2 && rest[n - 1].t === "num" && (rest[n - 2].v === "+" || rest[n - 2].v === "-")) {
    offset = (rest[n - 2].v === "-" ? -1 : 1) * Number(rest[n - 1].v);
    rest = rest.slice(0, n - 2);
  }
  if (rest.length >= 2 && rest[0].v === "(" && rest[rest.length - 1].v === ")") rest = rest.slice(1, -1);
  if (rest.length === 1 && rest[0].t === "name") return { kind: "compare", metric: rest[0].v, pair: false, offset, op, right };
  if (rest.length === 3 && rest[0].t === "name" && rest[1].v === "+" && rest[2].t === "name" && counterpart(rest[0].v) === rest[2].v) {
    return { kind: "compare", metric: rest[0].v, pair: true, offset, op, right };
  }
  return null;
}

const num = (v: number) => String(Math.round(v * 10000) / 10000);

export function toFormula(p: Parsed): string {
  if (p.kind === "gender") return `sex ${p.op} '${p.value}'`;
  const other = counterpart(p.metric);
  let left = p.pair && other ? `(${p.metric} + ${other})` : p.metric;
  if (p.offset) left += ` ${p.offset > 0 ? "+" : "-"} ${num(Math.abs(p.offset))}`;
  const right = p.right.type === "name" ? p.right.name : num(p.right.value);
  return `${left} ${p.op} ${right}`;
}

/** Ein Satz zum Lesen, z. B. „Erw. Tore mit GK_power (Heim + Gast) − 3 > Over-Linie“. */
export function describe(text: string, names: Names): string {
  const p = parseFormula(text);
  if (!p) return text;
  if (p.kind === "gender") return `${p.op === "!=" ? "nicht " : ""}${p.value === "men" ? "Männer" : "Frauen"}`;
  const left = (p.pair ? pairLabel(p.metric, names) : nameLabel(p.metric, names)) + (p.offset ? ` ${p.offset > 0 ? "+" : "−"} ${num(Math.abs(p.offset))}` : "");
  const right = p.right.type === "name" ? nameLabel(p.right.name, names) : num(p.right.value).replace(".", ",");
  return `${left} ${OP_SIGN[p.op]} ${right}`;
}

// ---------- Editor ----------

/** Metrik als lesbarer Name; Klick öffnet das Suchfeld (Namen werden beim Tippen vorgeschlagen). */
/** Auswahlliste: zuerst die Notebook-Metriken passend zum Markt (★), dann weitere Notebook-Metriken (☆), dann alle anderen. */
function MetricPicker({ value, names, onChange, pair = false, market = "over" }: {
  value: string; names: Names; listId?: string; onChange: (m: string) => void; pair?: boolean; market?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const info = names[value];
  const groups = useMemo(() => {
    const query = q.trim().toLowerCase();
    const all = Object.keys(names).filter((n) => !n.endsWith("_alt") || query.includes("alt"))
      .filter((n) => !query || n.toLowerCase().includes(query) || nameLabel(n, names).toLowerCase().includes(query));
    const by = (r: number) => all.filter((n) => favoriteRank(n, market) === r).sort((x, y) => x.localeCompare(y));
    return [
      { title: `★ Deine Metriken für ${isTotalMarket(market) ? "Over/Under (Summe beider Teams, …_to_over)" : "Sieger/Handicap (Unterschied der Teams)"}`, items: by(0), cls: "fav" },
      { title: "☆ Weitere Notebook-Metriken", items: by(1), cls: "fav2" },
      { title: "Alle anderen Metriken", items: by(2).sort((x, y) => nameLabel(x, names).localeCompare(nameLabel(y, names))), cls: "" },
    ].filter((g) => g.items.length);
  }, [names, q, market]);
  const pick = (m: string) => { onChange(m); setOpen(false); setQ(""); };
  const custom = q.trim();
  return (
    <div style={{ flex: 1, minWidth: 160, position: "relative" }}>
      <button className="secondary" onClick={() => setOpen(!open)} title={`${value}${info?.description ? ` – ${info.description}` : ""}
Klicken zum Ändern`}
        style={{ width: "100%", textAlign: "left", fontWeight: 600, whiteSpace: "normal" }}>
        {isFavorite(value) && <span className="fav-star">{favoriteRank(value, market) === 0 ? "★ " : "☆ "}</span>}
        {pair ? pairLabel(value, names) : nameLabel(value, names)}
        {nameLabel(value, names) !== value && <span className="small muted" style={{ fontWeight: 400, marginLeft: 6, fontFamily: "Consolas, monospace" }}>{value}</span>}
      </button>
      {open && (
        <div className="metric-menu" onMouseDown={(e) => e.preventDefault()}>
          <input autoFocus placeholder="Metrik suchen … (Name oder Beschriftung)" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
              if (e.key === "Enter") { const first = groups[0]?.items[0]; if (first) pick(first); else if (/^[A-Za-z_]\w*$/.test(custom)) pick(custom); }
            }}
            onBlur={() => setTimeout(() => setOpen(false), 150)} style={{ width: "100%", marginBottom: 6 }} />
          <div className="metric-menu-list">
            {groups.map((g) => (
              <div key={g.title}>
                <div className="metric-menu-title">{g.title} <span className="muted">({g.items.length})</span></div>
                {g.items.slice(0, g.cls ? 100 : 150).map((n) => (
                  <button key={n} className={`metric-menu-item ${g.cls}${n === value ? " sel" : ""}`} onClick={() => pick(n)} title={names[n]?.description}>
                    <span>{nameLabel(n, names)}</span>
                    {nameLabel(n, names) !== n && <code className="small muted">{n}</code>}
                  </button>
                ))}
              </div>
            ))}
            {!groups.length && <div className="small muted">Keine Metrik gefunden.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

type Props = { formula: string; names: Names; listId: string; onChange: (formula: string) => void; onRemove: () => void; market?: string };

/** Eine Bedingung: Auswahlfelder, wenn die Formel zerlegbar ist, sonst Text. „Als Text“ schaltet jederzeit um. */
export default function ConditionEditor({ formula, names, listId, onChange, onRemove, market }: Props) {
  const parsed = parseFormula(formula);
  const [asText, setAsText] = useState(!parsed);
  const textMode = asText || !parsed;
  const set = (patch: Partial<Compare>) => parsed?.kind === "compare" && onChange(toFormula({ ...parsed, ...patch } as Compare));

  const tail = <>
    <button className="secondary" title={textMode ? "Als Auswahlfelder bearbeiten" : "Als Formeltext bearbeiten"} disabled={textMode && !parsed}
      onClick={() => setAsText(!textMode)} style={{ fontSize: 12 }}>{textMode ? "Felder" : "Text"}</button>
    <button className="secondary" onClick={onRemove} title="Bedingung löschen">✕</button>
  </>;

  if (textMode) {
    return <div className="cond">
      <div className="row" style={{ gap: 6 }}>
        <span className="tag">Formel</span>
        <input list={listId} value={formula} onChange={(e) => onChange(e.target.value)}
          style={{ flex: 1, minWidth: 220, fontFamily: "Consolas, monospace" }} />
        {tail}
      </div>
      {!parsed && <div className="small muted" style={{ marginTop: 2 }}>Freie Formel – lässt sich nicht in Felder zerlegen.</div>}
    </div>;
  }

  if (parsed.kind === "gender") {
    return <div className="cond row" style={{ gap: 6 }}>
      <b style={{ minWidth: 110 }}>Geschlecht</b>
      <select value={`${parsed.op}${parsed.value}`} onChange={(e) => {
        const op = e.target.value.startsWith("!=") ? "!=" : "==";
        onChange(toFormula({ kind: "gender", op, value: e.target.value.slice(2) as "men" | "women" }));
      }}>
        <option value="==men">nur Männer</option><option value="==women">nur Frauen</option>
        <option value="!=men">nicht Männer</option><option value="!=women">nicht Frauen</option>
      </select>
      <span style={{ flex: 1 }} />{tail}
    </div>;
  }

  const p = parsed;
  const other = counterpart(p.metric);
  const info = names[p.metric];
  // Zuschlag nur zeigen, wo er üblich ist: Metrik gegen Linie/Metrik oder schon gesetzt
  const showOffset = p.offset !== 0 || p.right.type === "name" || p.pair;
  return <div className="cond">
    <div className="row" style={{ gap: 6, alignItems: "center" }}>
      <MetricPicker value={p.metric} names={names} listId={listId} pair={p.pair} market={market}
        onChange={(m) => set({ metric: m, pair: p.pair && !!counterpart(m) })} />
      {other && <label className="small" title={`Summe aus ${p.metric} und ${other}`}>
        <input type="checkbox" checked={p.pair} onChange={(e) => set({ pair: e.target.checked })} /> Heim + Gast</label>}
      {showOffset ? <>
        <select value={p.offset >= 0 ? "+" : "-"} onChange={(e) => set({ offset: (e.target.value === "-" ? -1 : 1) * Math.abs(p.offset) })}
          title="Zuschlag oder Abzug" style={{ width: 44 }}><option value="+">+</option><option value="-">−</option></select>
        <input className="cell" type="number" step="0.5" value={Math.abs(p.offset)} title="Zuschlag/Abzug in derselben Einheit wie die Metrik"
          onChange={(e) => set({ offset: (p.offset < 0 ? -1 : 1) * Math.abs(Number(e.target.value) || 0) })} style={{ width: 60 }} />
      </> : null}
      <select value={p.op} onChange={(e) => set({ op: e.target.value })}>
        {OPS.map((o) => <option key={o} value={o}>{OP_SIGN[o]} {OP_LABEL[o]}</option>)}
      </select>
      <select value={p.right.type === "number" ? "#" : p.right.name} onChange={(e) => {
        const v = e.target.value;
        set({ right: v === "#" ? { type: "number", value: p.right.type === "number" ? p.right.value : 0 } : { type: "name", name: v } });
      }}>
        <option value="over">Over-Linie</option><option value="hdp">Handicap Heim</option>
        <option value="#">Zahl …</option>
        {p.right.type === "name" && !["over", "hdp"].includes(p.right.name) && <option value={p.right.name}>{nameLabel(p.right.name, names)}</option>}
      </select>
      {p.right.type === "number" && <input className="cell" type="number" step="0.5" value={p.right.value}
        onChange={(e) => set({ right: { type: "number", value: Number(e.target.value) || 0 } })} style={{ width: 72 }} />}
      {tail}
    </div>
    <div className="small muted" style={{ marginTop: 2 }}>{describe(formula, names)}{info?.description ? <span title={info.description}> · ⓘ</span> : ""}</div>
  </div>;
}
