"""Quoten aus eingefügtem Text lesen (z. B. Tabelle von einer Quotenseite, mit Strg+A/Strg+C kopiert).

Der Text wird nicht nach festem Layout gelesen, sondern nach Mustern – egal ob eine
Tabellenzeile in einer Textzeile steht oder jede Zelle in einer eigenen:

* **Linie**: Zahl mit Vorzeichen oder einer Nachkommastelle, z. B. „+57.5“, „-3.5“, „58“ nach „O/U“.
  Ab 30 ist es eine Torlinie (Over/Under), bis 25 ein Handicap (aus Sicht des Heimteams).
* **Quote**: Dezimalquote mit zwei Nachkommastellen, z. B. „1.85“ oder „1,85“.
* Prozentwerte (Auszahlung) und ganze Zahlen (Anzahl Buchmacher) werden übergangen.

Die Quoten nach einer Linie gehören paarweise zu ihr (Over/Under bzw. Heim/Gast). Quoten vor
der ersten Linie werden als 1X2 gelesen (je drei). Paare und Dreier mit unplausibler Marge
(Summe der Kehrwerte nicht zwischen 1,00 und 1,20) fallen weg. Hauptlinie: wie bei OddsPapi
die Linie, bei der beide Seiten (Median) zwischen 1,70 und 2,00 liegen.
"""
from __future__ import annotations

import re
import statistics

from .sources.oddspapi import _main_line

_TOKEN = re.compile(r"[+-]?\d+(?:[.,]\d+)?%?|[A-Za-z/]+")
_ODDS = re.compile(r"^\d{1,3}[.,]\d{2}$")
_LINE = re.compile(r"^[+-]?\d{1,3}(?:[.,](?:5|0|25|75))?$")
_LINE_WORDS = {"o/u", "ou", "over/under", "total", "totals", "ah", "handicap", "asian"}


def _num(tok: str) -> float:
    return float(tok.replace(",", "."))


def _plausible(odds: list[float]) -> bool:
    return 1.0 <= sum(1 / o for o in odds) <= 1.20


def parse(text: str) -> dict:
    tokens = _TOKEN.findall(text or "")
    segments: list[tuple[float | None, list[float]]] = [(None, [])]
    prev_word = False
    for tok in tokens:
        if tok[0].isalpha():
            prev_word = tok.lower() in _LINE_WORDS
            continue
        if tok.endswith("%"):
            prev_word = False
            continue
        if _ODDS.match(tok) and not tok.startswith(("+", "-")):
            segments[-1][1].append(_num(tok))
        elif _LINE.match(tok) and (tok[0] in "+-" or "." in tok or "," in tok or prev_word):
            segments.append((_num(tok), []))
        prev_word = False

    prices: dict = {}
    x12: list[tuple[float, float, float]] = []
    for line, odds in segments:
        if line is None:
            x12 += [t for t in zip(odds[0::3], odds[1::3], odds[2::3]) if _plausible(list(t))]
            continue
        kind = "totals" if abs(line) >= 30 else "spreads" if abs(line) <= 25 else None
        if kind is None:
            continue
        sides = ("Over", "Under") if kind == "totals" else ("1", "2")
        line = abs(line) if kind == "totals" else line
        for a, b in zip(odds[0::2], odds[1::2]):
            if _plausible([a, b]):
                prices.setdefault((kind, line, sides[0]), []).append(a)
                prices.setdefault((kind, line, sides[1]), []).append(b)

    result: dict = {"lines": [], "handicaps": [], "warnings": []}
    for kind, key, a_name, b_name in (("totals", "lines", "Over", "Under"), ("spreads", "handicaps", "1", "2")):
        for line in sorted({h for (t, h, _) in prices if t == kind}):
            a, b = prices.get((kind, line, a_name), []), prices.get((kind, line, b_name), [])
            if a and b:
                result[key].append({"line": line, "a": round(statistics.median(a), 3),
                                    "b": round(statistics.median(b), 3), "count": min(len(a), len(b))})
    total = _main_line(prices, "totals", "Over", "Under")
    if total:
        result["over_line"], result["odds_over"], result["odds_under"] = total
    elif result["lines"]:
        result["warnings"].append("Torlinien gefunden, aber keine mit beiden Quoten zwischen 1,70 und 2,00.")
    spread = _main_line(prices, "spreads", "1", "2")
    if spread:
        result["hdp_line"] = spread[0]
    elif result["handicaps"]:
        result["warnings"].append("Handicaps gefunden, aber keines mit beiden Quoten zwischen 1,70 und 2,00.")
    if x12:
        result["odds_home"], result["odds_draw"], result["odds_away"] = (
            round(statistics.median(t[i] for t in x12), 3) for i in range(3))
        result["x12_count"] = len(x12)
    if not (result["lines"] or result["handicaps"] or x12):
        result["warnings"].append("Keine Quoten erkannt. Bitte Dezimalquoten (z. B. 1.85) einstellen und die Tabelle kopieren.")
    return result
