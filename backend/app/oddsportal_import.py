"""Quoten einer oddsportal-Spielseite übernehmen, die der Nutzer im eigenen Browser offen hat.

Der Lesezeichen-Knopf schickt den sichtbaren Seitentext, die Adresse, den Seitentitel und die
Zeitzone des Browsers. Das Tool ruft oddsportal selbst nie ab.

* **Reiter** aus der Adresse: ``#<id>:1X2;2``, ``#<id>:O/U;2``, ``#<id>:AH;2`` (h2h-Seite) bzw.
  ``#1X2;2``, ``#over-under;2``, ``#ah;2`` (Spielseite); ohne Anker ist es 1X2.
  Die Zahl hinter dem Semikolon ist der Spielabschnitt: 2 = ganzes Spiel, 3/4 = Halbzeiten.
  Übernommen wird nur das ganze Spiel und nur der Markt des angezeigten Reiters.
* **Spiel** aus Titel („Heim - Gast Odds, …“), Anstoß („15 Dec 2025, 17:30“ in Browserzeit) und
  Endstand („Final result 31:41“). Die Zuordnung vergleicht Datum, Uhrzeit, Ergebnis und Namen;
  einmal sicher zugeordnete Namen merkt sich das Tool (``TeamAlias``).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import odds_paste
from .models import Competition, Game, GameLine, SourceRecord, Team, TeamAlias

SOURCE = "oddsportal"
# h2h-Seite: „#<id>:O/U;2“, Spielseite: „#over-under;2“
MARKETS = {"1x2": "1X2", "o/u": "O/U", "over-under": "O/U", "ah": "AH"}
MARKET_FIELDS = {
    "1X2": ("odds_home", "odds_draw", "odds_away"),
    "O/U": ("over_line", "odds_over", "odds_under"),
    "AH": ("hdp_line",),
}
MARKET_LABELS = {"1X2": "1X2", "O/U": "Over/Under", "AH": "Asian Handicap"}
# Ortszeit der gespeicherten Anstoßzeiten je Land (Stunden gegenüber UTC)
LOCAL_OFFSET_HOURS = {"Russia": 3, "Korea": 9}
AUTO_MIN_SCORE, AUTO_MIN_MARGIN = 8, 3

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_KICKOFF = re.compile(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4}),?\s+(\d{1,2}):(\d{2})")
_RESULT = re.compile(r"Final result\s*(\d{1,3})\s*:\s*(\d{1,3})")
_ANCHOR = re.compile(r"#(?:[^:;]*:)?([^;:]+);(\d+)")
# Danach folgen Tipps der Nutzer und frühere Begegnungen mit eigenen Quoten
_CUT = ("User Predictions", "Odds, Predictions and H2H")
_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "j", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "ju", "ja"]))


def event_id(url: str | None) -> str | None:
    """oddsportal-Spiel-ID: im Anker der h2h-Seite („#GtS5vtTh:AH;2“) oder am Ende der Spieladresse."""
    m = re.search(r"#([A-Za-z0-9]{8})(?::|$)", url or "") or re.search(r"-([A-Za-z0-9]{8})/?(?:#|$)", url or "")
    return m.group(1) if m else None


def norm(name: str | None) -> str:
    s = "".join(_CYR.get(ch, ch) for ch in (name or "").lower())
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def parse_page(text: str, url: str = "", title: str = "", tz_offset_min: int = 0) -> dict:
    """Spielkopf und Quoten des angezeigten Reiters lesen."""
    text = text or ""
    warnings: list[str] = []
    m = _ANCHOR.search(url or "")
    market = MARKETS.get(m.group(1).lower()) if m else "1X2"
    period = m.group(2) if m else "2"

    home = away = None
    t = re.match(r"\s*(.+?)\s+-\s+(.+?)\s+(?:Odds|Betting|Live|Prediction)\b", title or "")
    title_teams = {t.group(1).strip(), t.group(2).strip()} if t else set()
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    # Heim/Gast aus dem Spielkopf („Heim / [Tore] / - / Gast“). Der Seitentitel einer h2h-Seite
    # nennt die Teams in Adress-Reihenfolge, nicht als Heim – Gast; er dient nur zur Kontrolle.
    head = None
    for i in range(len(lines) - 2):
        j = i + 2 if lines[i + 1].isdigit() else i + 1
        if j + 1 < len(lines) and lines[j] in ("-", "–") and lines[i] != lines[j + 1]:
            if not title_teams or {lines[i], lines[j + 1]} == title_teams:
                home, away, head = lines[i], lines[j + 1], i
                break
    if home is None and t:
        warnings.append("Heim und Gast nur aus dem Seitentitel gelesen – bitte Zuordnung prüfen.")
        home, away = t.group(1).strip(), t.group(2).strip()
    league = None
    # Spielseite: /handball/<land>/<liga>/<heim-gast-id>/ – Liga steht in der Adresse
    path = [p for p in re.sub(r"^https?://[^/]+", "", (url or "").split("#")[0]).split("/") if p]
    if len(path) >= 4 and path[0] == "handball" and path[1] != "h2h":
        league = f"{path[1]} {path[2]}".replace("-", " ").title()
    elif head:
        # davor: Brotkrumen „… > Liga > Heim - Gast“ oder direkt die Liga
        prev = [x for x in lines[max(0, head - 4):head] if x not in ("<", ">", f"{home} - {away}")]
        league = prev[-1] if prev else None

    kickoff_local = kickoff_utc = None
    k = _KICKOFF.search(text)
    if k and k.group(2).lower() in _MONTHS:
        kickoff_local = datetime(int(k.group(3)), _MONTHS[k.group(2).lower()], int(k.group(1)),
                                 int(k.group(4)), int(k.group(5)))
        # getTimezoneOffset(): Minuten, die zur Ortszeit addiert UTC ergeben
        kickoff_utc = kickoff_local + timedelta(minutes=tz_offset_min or 0)
    r = _RESULT.search(text)
    if not r and home and away:
        # Spielkopf: Heim, Tore, „-“, Gast, Tore – jeweils in eigener Zeile
        r = re.search(rf"^{re.escape(home)}\s*\n\s*(\d{{1,3}})\s*\n\s*[-–:]\s*\n\s*{re.escape(away)}\s*\n\s*(\d{{1,3}})\s*$",
                      text, re.M)
    score = (int(r.group(1)), int(r.group(2))) if r else None

    found: dict = {}
    parsed: dict = {"lines": [], "handicaps": []}
    if market is None:
        warnings.append("Dieser Reiter wird nicht übernommen. Bitte 1X2, Over/Under oder Asian Handicap öffnen.")
    elif period != "2":
        warnings.append("Es ist eine Halbzeit gewählt. Bitte „Full Time“ anklicken und den Knopf erneut drücken.")
    else:
        body = text
        for marker in _CUT:
            body = body.split(marker, 1)[0]
        parsed = odds_paste.parse(body)
        found = {f: parsed[f] for f in MARKET_FIELDS[market] if parsed.get(f) is not None}
        warnings += parsed["warnings"] if not found else []
        if not found and not parsed["warnings"]:
            warnings.append(f"Keine {MARKET_LABELS[market]}-Quoten gefunden.")
    if not home:
        warnings.append("Mannschaften nicht erkannt (Seitentitel unbekannt).")
    if not kickoff_local:
        warnings.append("Anstoßzeit nicht erkannt.")
    women = bool(re.search(r"\bwomen\b", league or "", re.I) or any(
        re.search(r"(\bW|\(W\)|\bwomen)$", n or "", re.I) for n in (home, away)))
    return {
        "event_id": event_id(url), "home": home, "away": away, "league": league, "market": market, "period": period,
        "kickoff_local": kickoff_local, "kickoff_utc": kickoff_utc, "score": score, "women": women,
        "found": found, "lines": parsed["lines"], "handicaps": parsed["handicaps"], "warnings": warnings,
    }


def parse_pages(pages: list[dict], title: str = "", tz_offset_min: int = 0) -> dict:
    """Mehrere Reiter derselben Spielseite (der Knopf klickt 1X2, Over/Under und Handicap durch)."""
    infos = [parse_page(p.get("text", ""), p.get("url", ""), title, tz_offset_min) for p in pages if p.get("text")]
    if not infos:
        return parse_page("", "", title, tz_offset_min)
    merged = dict(next((i for i in infos if i["kickoff_local"]), infos[0]))
    merged["found"], merged["lines"], merged["handicaps"], merged["warnings"] = {}, [], [], []
    for i in infos:
        merged["found"].update(i["found"])
        merged["lines"] += i["lines"]
        merged["handicaps"] += i["handicaps"]
        merged["warnings"] += [f"{MARKET_LABELS.get(i['market'], 'Reiter')}: {w}" for w in i["warnings"]]
    merged["market"] = "+".join(i["market"] for i in infos if i["found"]) or merged["market"]
    merged["read"] = sorted({i["market"] for i in infos if i["market"] and i["period"] == "2"})
    for p in pages:
        if not p.get("text"):
            merged["warnings"].append(f"{p.get('missing') or 'Ein Reiter'} wurde nicht geladen.")
    return merged


def _aliases(session: Session, names) -> dict[str, int]:
    names = [n for n in names if n]
    rows = session.scalars(select(TeamAlias).where(TeamAlias.source == SOURCE, TeamAlias.name.in_(names)))
    return {a.name: a.team_id for a in rows}


def _name_points(page_name: str | None, team: Team, alias_team: int | None) -> tuple[int, str | None]:
    if not page_name:
        return 0, None
    if alias_team is not None:
        return (5, "Name bekannt") if alias_team == team.id else (-3, None)
    page = norm(page_name)
    best = 0.0
    for n in (team.name, team.name_en, team.handballapi_name):
        n = norm(n)
        if not n:
            continue
        best = max(best, difflib.SequenceMatcher(None, page, n).ratio())
        if {w for w in page.split() if len(w) >= 4} & {w for w in n.split() if len(w) >= 4}:
            best = max(best, 0.8)
    return (3, "Name ähnlich") if best >= 0.8 else (1, None) if best >= 0.6 else (0, None)


def candidates(session: Session, info: dict, limit: int = 6) -> list[dict]:
    """Spiele rund um den Anstoß, nach Übereinstimmung sortiert."""
    if not info.get("kickoff_utc"):
        return []
    utc = info["kickoff_utc"]
    games = session.scalars(select(Game).where(Game.start_moscow >= utc - timedelta(hours=14),
                                               Game.start_moscow <= utc + timedelta(hours=14))).unique().all()
    comps = {c.id: c for c in session.scalars(select(Competition).where(
        Competition.id.in_({g.competition_id for g in games})))}
    alias = _aliases(session, [info.get("home"), info.get("away")])
    known = session.get(SourceRecord, f"{SOURCE}:{info['event_id']}") if info.get("event_id") else None
    out = []
    for g in games:
        comp = comps.get(g.competition_id)
        points, reasons, conflict = 0, [], False
        if known and known.game_id == g.id:
            points += 20
            reasons.append("schon einmal zugeordnet")
        expected = LOCAL_OFFSET_HOURS.get(comp.country if comp else None)
        delta = (g.start_moscow - utc).total_seconds() / 60
        if expected is not None and abs(delta - expected * 60) <= 20:
            points += 4
            reasons.append("Anstoß passt")
        elif expected is None and abs(delta - round(delta / 60) * 60) <= 5 and -60 <= delta <= 600:
            points += 2
            reasons.append("Uhrzeit passt (Zeitzone unbekannt)")
        if info.get("score") and g.home_score is not None:
            if (g.home_score, g.away_score) == info["score"]:
                points += 6
                reasons.append("Ergebnis passt")
            else:
                # Anderes Ergebnis = anderes Spiel: nie automatisch speichern
                points -= 4
                conflict = True
                reasons.append("Ergebnis vertauscht (Heim/Gast?)" if (g.away_score, g.home_score) == info["score"]
                               else "Ergebnis passt nicht")
        for page_name, team in ((info.get("home"), g.home_team), (info.get("away"), g.away_team)):
            p, why = _name_points(page_name, team, alias.get(page_name))
            points += p
            conflict |= p < 0
            if why:
                reasons.append(why)
        if comp:
            if (comp.gender == "women") == info.get("women"):
                points += 1
            else:
                points -= 4
        out.append({"game": g, "competition": comp, "score": points, "reasons": reasons, "conflict": conflict})
    out.sort(key=lambda c: (-c["score"], abs((c["game"].start_moscow - utc).total_seconds())))
    return out[:limit]


def pick(cands: list[dict]) -> Game | None:
    cands = [c for c in cands if not c["conflict"]]
    if not cands or cands[0]["score"] < AUTO_MIN_SCORE:
        return None
    if len(cands) > 1 and cands[0]["score"] - cands[1]["score"] < AUTO_MIN_MARGIN:
        return None
    return cands[0]["game"]


def remember_names(session: Session, info: dict, game: Game) -> None:
    for name, team_id in ((info.get("home"), game.home_team_id), (info.get("away"), game.away_team_id)):
        if not name:
            continue
        a = session.get(TeamAlias, (SOURCE, name))
        if a:
            a.team_id = team_id
        else:
            session.add(TeamAlias(source=SOURCE, name=name, team_id=team_id))


def save(session: Session, info: dict, game: Game) -> None:
    """Nur die Werte des angezeigten Reiters setzen; die anderen bleiben, wie sie sind."""
    line = game.line or GameLine(game_id=game.id)
    for k, v in info["found"].items():
        setattr(line, k, v)
    # Von Hand übernommene Werte: der automatische Abgleich überschreibt sie nicht
    line.source, line.updated_at = "manual", datetime.utcnow()
    session.add(line)
    remember_names(session, info, game)
    if info.get("event_id"):
        key = f"{SOURCE}:{info['event_id']}"
        rec = session.get(SourceRecord, key) or SourceRecord(key=key, payload={}, status="imported")
        rec.game_id = game.id
        old = rec.payload or {}
        read = set(old.get("read", [])) | set(info.get("read") or [])
        if "read" not in info and info.get("market") and info.get("period") == "2":
            read.add(info["market"])  # einzelner Reiter (alter Lesezeichen-Knopf)
        read = sorted(read)
        rec.payload = {**old, "home": info.get("home"), "away": info.get("away"),
                       "score": info.get("score"), "read": read, **{k: v for k, v in info["found"].items()}}
        session.add(rec)
    session.commit()


def remaining(session: Session, competition_id: int) -> dict:
    """Beendete Spiele des Wettbewerbs, denen noch Quoten fehlen – für die Rückmeldung auf oddsportal."""
    games = session.scalars(select(Game).where(Game.competition_id == competition_id, Game.finished.is_(True))).unique().all()
    lines = [g.line for g in games]
    return {
        "finished": len(games),
        "line": sum(1 for l in lines if l is None or l.over_line is None),
        "hdp": sum(1 for l in lines if l is None or l.hdp_line is None),
        "x12": sum(1 for l in lines if l is None or not (l.odds_home and l.odds_away)),
    }


# Spielseite „/handball/<land>/<liga>/heim-gast-<id>/“ oder h2h „/handball/h2h/heim-<tid>/gast-<tid>/#<id>“
_ROW_GAME = re.compile(r"/handball/(?!h2h/)[^#?]*/([a-z0-9-]+)-[A-Za-z0-9]{8}/?$")
_ROW_H2H = re.compile(r"/handball/h2h/([a-z0-9-]+)-[A-Za-z0-9]{8}/([a-z0-9-]+)-[A-Za-z0-9]{8}/?(?:#|$)")


def missing_markets(game: Game, rec: SourceRecord | None = None) -> list[str]:
    """Was einem Spiel noch fehlt. Ein Handicap gilt als erledigt, wenn oddsportal gelesen wurde und keins im
    Bereich 1,70–2,00 hatte."""
    l, read = game.line, set(((rec.payload or {}) if rec else {}).get("read", []))
    out = []
    if l is None or l.over_line is None:
        out.append("Linie")
    if l is None or l.hdp_line is None and "AH" not in read:
        out.append("HC")
    if l is None or not (l.odds_home and l.odds_away):
        out.append("1X2")
    return out


def _team_phrases(session: Session) -> dict[str, set[int]]:
    """Normalisierte Namen → Teams: gemerkte oddsportal-Namen und eigene Namen (auch transliteriert)."""
    out: dict[str, set[int]] = {}
    for a in session.scalars(select(TeamAlias).where(TeamAlias.source == SOURCE)):
        out.setdefault(norm(a.name), set()).add(a.team_id)
    for t in session.scalars(select(Team)):
        for n in (t.name, t.name_en, t.handballapi_name):
            if norm(n):
                out.setdefault(norm(n), set()).add(t.id)
    return out


def _teams(phrases: dict[str, set[int]], words: list[str]) -> set[int]:
    """Teams zu einem Adressteil wie „cska-moscow“: genauer Name, sonst einer enthält den anderen ganz
    („cska“ ⊂ „cska moscow“, „adyif“ ⊂ „agu adyif“). Das Ergebnis entscheidet später."""
    words = [w for w in words if w != "w"]  # Frauen-Kennung
    exact = phrases.get(" ".join(words))
    if exact:
        return exact
    out: set[int] = set()
    for phrase, ids in phrases.items():
        p = phrase.split()
        short, long_ = (p, words) if len(p) <= len(words) else (words, p)
        if len("".join(short)) >= 4 and set(short) <= set(long_):
            out |= ids
    return out


def _slug_pairs(href: str, phrases: dict[str, set[int]]) -> list[tuple[set[int], set[int]]]:
    """Mögliche (Heim, Gast)-Teams aus der Adresse. h2h-Adressen nennen die Teams nicht als Heim – Gast."""
    path = (href or "").split("?")[0]
    m = _ROW_H2H.search(path)
    if m:
        a, b = _teams(phrases, m.group(1).split("-")), _teams(phrases, m.group(2).split("-"))
        return [(a, b), (b, a)] if a and b else []
    m = _ROW_GAME.search(path.split("#")[0])
    if not m:
        return []
    words = m.group(1).split("-")
    pairs = [(phrases.get(" ".join(words[:k])), phrases.get(" ".join(words[k:]))) for k in range(1, len(words))]
    return [(h, a) for h, a in pairs if h and a]


def list_status(session: Session, rows: list[dict]) -> list[dict]:
    """Zeilen einer oddsportal-Ergebnisliste (Spieladresse + Zeilentext) den Spielen im Tool zuordnen.

    Zuerst über die gemerkte Spiel-ID, sonst über die Teamnamen in der Adresse und das Ergebnis im Zeilentext
    (in Heim-Gast-Reihenfolge wie auf der Liste).
    Mehrdeutiges bleibt unbekannt („?“) – nach dem Öffnen des Spiels ist die ID gemerkt."""
    phrases = None
    out = []
    for row in rows:
        eid = row.get("id") or event_id(row.get("href"))
        rec = session.get(SourceRecord, f"{SOURCE}:{eid}") if eid else None
        game = session.get(Game, rec.game_id) if rec and rec.game_id else None
        if game is None:
            phrases = phrases if phrases is not None else _team_phrases(session)
            pairs = _slug_pairs(row.get("href"), phrases)
            nums = [int(x) for x in re.findall(r"(?<![\d.])\d{1,3}(?![\d.])", row.get("text") or "")]
            found = []
            for h, a in pairs:
                for g in session.scalars(select(Game).where(Game.home_team_id.in_(h), Game.away_team_id.in_(a),
                                                            Game.finished.is_(True))).unique():
                    if any(nums[i:i + 2] == [g.home_score, g.away_score] for i in range(len(nums) - 1)):
                        found.append(g)
            game = found[0] if len({g.id for g in found}) == 1 else None
        if game is None:
            out.append({"id": eid, "status": "unknown"})
        elif not game.finished:
            out.append({"id": eid, "status": "open", "game_id": game.id})
        else:
            miss = missing_markets(game, rec)
            out.append({"id": eid, "status": "missing" if miss else "ok", "missing": miss, "game_id": game.id})
    return out
