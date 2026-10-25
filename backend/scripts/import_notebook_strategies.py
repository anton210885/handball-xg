"""Übernimmt alle selbst gebauten Strategien aus handball.ipynb (futuregamesstrategy_…).

Jede Bedingung wird wörtlich als Formel übernommen, z. B.
``(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power) -3 > over`` – die alten
Spaltennamen liefert app/legacy.py. Die Strategien heißen danach „NB: over_1“,
„NB: Men_over_5“ usw. Bei doppelt definierten Namen gilt die letzte Definition im Notebook.

Aufruf im Ordner backend:  .venv\\Scripts\\python scripts\\import_notebook_strategies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_notebook_strategies import extract  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import KNOWN_NAMES  # noqa: E402
from app.models import Strategy  # noqa: E402
from app.strategies import FormulaError, validate_rules  # noqa: E402

PREFIX = "NB: "


def display_name(nb_name: str) -> str:
    return PREFIX + nb_name.removeprefix("futuregamesstrategy").lstrip("_")


def main():
    init_db()
    found = {s["name"]: s for s in extract()}  # letzte Definition gewinnt
    ok, failed = [], []
    with SessionLocal() as session:
        # Die früheren Hand-Übersetzungen „Alt: …“ ersetzt dieser Import
        session.query(Strategy).filter(Strategy.name.like("Alt:%")).delete(synchronize_session=False)
        for nb_name, s in found.items():
            rules = [{"formula": c} for c in s["conditions"]]
            try:
                validate_rules(rules, KNOWN_NAMES)
            except FormulaError as ex:
                failed.append(f"{nb_name}: {ex}")
                continue
            name = display_name(nb_name)
            st = session.query(Strategy).filter(Strategy.name == name).first() or Strategy(name=name)
            st.market, st.rules, st.min_games = s["market"], rules, 0
            st.notes = f"Aus handball.ipynb ({nb_name})"
            session.add(st)
            ok.append(name)
        session.commit()
    print(f"{len(found)} Strategien im Notebook, {len(ok)} übernommen, {len(failed)} nicht übersetzbar")
    for f in failed:
        print("  ", f)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
