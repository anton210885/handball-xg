"""Liest alle futuregamesstrategy_… aus dem alten Notebook (handball.ipynb).

Gibt je Strategie Name, Markt und die Bedingungen als Liste von Textausdrücken zurück –
mit eingesetzten Grenzwerten (overOddsW, underOddsW, overTB25, underTB25), die im
Notebook direkt vor der Strategie gesetzt wurden.
"""
import json
import re
from pathlib import Path

NOTEBOOK = Path(r"C:\Users\anton\OneDrive\Desktop\hANDBALL\handball.ipynb")
PARAMS = ("overOddsW", "underOddsW", "overTB25", "underTB25", "sex")
MARKETS = ("hdp_home", "hdp_away", "under", "over", "home", "away")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _split_top_level(expr: str, sep: str = "&") -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in expr:
        depth += ch == "("
        depth -= ch == ")"
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _unwrap(expr: str) -> str:
    """Äußere Klammern entfernen, solange sie den ganzen Ausdruck umschließen."""
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(expr) - 1:
                return expr
        expr = expr[1:-1].strip()
    return expr


def extract(notebook: Path = NOTEBOOK) -> list[dict]:
    nb = json.loads(notebook.read_text(encoding="utf-8"))
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    out = []
    for m in re.finditer(r"^(futuregamesstrategy(\w*?)_(?:" + "|".join(MARKETS) + r")_\d+)\s*=\s*df_future_games\.loc\[(.*?)\n\s*\]",
                         src, re.M | re.S):
        name, body = m.group(1), m.group(3)
        params = {}
        for p in PARAMS:
            found = re.findall(rf"^\s*{p}\s*=\s*['\"]?([\w.]+)['\"]?", src[: m.start()], re.M)
            if found:
                params[p] = found[-1]
        body = _strip_comments(body)
        # Spaltenzugriffe df[...]['spalte'] -> spalte (einige Strategien greifen versehentlich auf
        # df_finished_games zu – gemeint ist dieselbe Spalte)
        body = re.sub(r"df_(?:future|finished)_games\[['\"](\w+)['\"]\]", r"\1", body)
        # Grenzwert-Variablen einsetzen – nur freistehende Namen, keine Spaltennamen
        for p, v in params.items():
            if p == "sex":
                body = re.sub(r"==\s*sex\b", f"== {v!r}", body)
            else:
                body = re.sub(rf"\b{p}\b", v, body)
        body = " ".join(body.split())
        market = next(mk for mk in MARKETS if re.search(rf"_{mk}_\d+$", name))
        out.append({
            "name": name,
            "market": market,
            "conditions": [_unwrap(c) for c in _split_top_level(body)],
        })
    return out


if __name__ == "__main__":
    import sys
    from collections import Counter

    sys.stdout.reconfigure(encoding="utf-8")
    strategies = extract()
    print(len(strategies), "Strategien;", Counter(s["market"] for s in strategies))
    names = Counter(n for s in strategies for c in s["conditions"] for n in re.findall(r"[A-Za-z_]\w*", c))
    print(names.most_common())
    for s in strategies[:3] + [s for s in strategies if s["name"].endswith("over_5")]:
        print(s)
