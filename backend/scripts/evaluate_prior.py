"""Wie stark soll die Vorsaison in die Team-Merkmale einfließen?

Für jede Saison mit hinterlegter Vorsaison und mehrere Gewichte k wird die Prognose
der Gesamttore (xG- und tor-basiert) mit dem echten Ergebnis verglichen – getrennt
nach Saisonphase (wie viele Spiele das Team mit weniger Spielen schon hatte).

Aufruf im Ordner backend:  .venv\\Scripts\\python scripts\\evaluate_prior.py
"""
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import features  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Competition  # noqa: E402

WEIGHTS = [0, 1, 2, 3, 4, 6, 8, 12, 20]
PHASES = [(0, 0, "0 Spiele"), (1, 2, "1–2"), (3, 5, "3–5"), (6, 10, "6–10"), (11, 999, "11+")]
KEYS = ["pred_total", "pred_total_goals"]


def evaluate(session, comp_id):
    # Spiele mit Ergebnis; Phase = min(Spiele Heim, Spiele Gast) in der aktuellen Saison
    results = {}
    for k in WEIGHTS:
        rows = features.all_game_features(session, comp_id, prior_weight=k)
        for r in rows:
            g, f = r["game"], r["features"]
            if not g.finished or g.home_score is None:
                continue
            phase = min(f["home_games"], f["away_games"])
            for key in KEYS:
                if f.get(key) is not None:
                    results.setdefault((key, k), []).append((g.id, phase, abs(g.home_score + g.away_score - f[key])))
    return results


def main():
    with SessionLocal() as s:
        comps = [c for c in s.query(Competition).all() if c.previous_competition_id]
        for comp in comps:
            res = evaluate(s, comp.id)
            if not res:
                continue
            print(f"\n=== {comp.season} (Vorsaison {comp.previous_competition_id}) – Ø Abweichung Gesamttore ===")
            for key in KEYS:
                # Fairer Vergleich auf denselben Spielen: die, für die auch k=0 eine Prognose hat
                base_ids = {gid for gid, *_ in res.get((key, 0), [])}
                print(f"\n{key}")
                print(f"{'k':>4} | {'gleiche Spiele':>15} | " + " | ".join(f"{p[2]:>9}" for p in PHASES) + " | alle Spiele")
                for k in WEIGHTS:
                    errs = res.get((key, k), [])
                    same = [e for gid, _, e in errs if gid in base_ids]
                    cells = []
                    for lo, hi, _ in PHASES:
                        ph = [e for _, p, e in errs if lo <= p <= hi]
                        cells.append(f"{mean(ph):5.2f} ({len(ph):3d})" if ph else f"{'–':>9}")
                    print(f"{k:>4} | {mean(same):6.2f} ({len(same):3d})   | " + " | ".join(cells)
                          + f" | {mean(e for *_, e in errs):5.2f} ({len(errs)})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
