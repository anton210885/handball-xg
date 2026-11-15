"""Test-Metrik: ML-Korrektur der fairen Tordifferenz (LightGBM).

Ein Gradient-Boosting-Modell lernt, wo ``fair_margin`` systematisch danebenliegt (Ziel: echte Differenz − fair_margin),
aus allen Vor-Spiel-Metriken ohne Linien und Quoten. Ergebnis:

* ``ml_margin`` = fair_margin + Korrektur
* ``ml_margin_plus_hdp`` = ml_margin + Handicap Heim

**Ohne Blick in die Zukunft:** Für jeden Kalendermonat gibt es ein eigenes Modell, gelernt nur aus Spielen vor dem
Monatsersten. Das Modell eines Monats wird einmal gelernt und unter ``data/ml/`` abgelegt; für spätere Monate gilt das
neueste vorhandene Modell, bis deren Monat begonnen hat. Im Vorwärtstest (März 2025 bis Nov. 2026, rund 3000 Spiele)
lag der mittlere Fehler bei 5.13 statt 5.21 Toren (fair_margin), gegen die echte Handicap-Linie aber klar schlechter
als der Markt – darum nur zum Beobachten gedacht.

Fehlt LightGBM, bleiben die Metriken einfach leer.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import defaultdict
from datetime import date

from .config import DATA_DIR

log = logging.getLogger(__name__)

VERSION = 1  # erhöhen, wenn sich Merkmale oder Einstellungen ändern -> alle Monatsmodelle neu lernen
MODEL_DIR = DATA_DIR / "ml"
MIN_TRAIN = 500  # so viele beendete Spiele mit fair_margin braucht ein Monatsmodell mindestens
ROUNDS = 300
PARAMS = dict(objective="regression", learning_rate=0.02, num_leaves=7, min_data_in_leaf=80, feature_fraction=0.7,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=20.0, seed=7, deterministic=True, num_threads=2,
              verbose=-1)
# Keine Linien, Quoten oder daraus abgeleiteten Werte als Eingabe; fair_margin kommt gezielt dazu.
_EXCLUDE = re.compile(r"(_minus_line|_to_over|_plus_hdp|^p_|^ev_|^kelly_|^mkt_p_|^model_p_|^odds_|^over_line$|"
                      r"^hdp_line$|^home$|^away$|^Draw$|^over$|^hdp$|over_bet|over_hits|over_loss|^Sum_count|^fair_|"
                      r"^sd_|^ml_|_alt$)")


def _month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _feature_names(rows: list[dict]) -> list[str]:
    names: set[str] = set()
    for r in rows:
        for k, v in r["features"].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and not _EXCLUDE.search(k):
                names.add(k)
    return sorted(names) + ["fair_margin", "women", "league_code"]


def _vector(f: dict, names: list[str], leagues: dict[str, int]) -> list[float]:
    out = []
    for n in names:
        if n == "women":
            v = 1.0 if f.get("sex") == "women" else 0.0
        elif n == "league_code":
            v = leagues.get(f.get("league"))
        else:
            v = f.get(n)
        out.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else math.nan)
    return out


def _path(month: str):
    return MODEL_DIR / f"margin_v{VERSION}_{month}.txt"


def _load(month: str):
    import lightgbm as lgb
    p = _path(month)
    meta = p.with_suffix(".json")
    if not p.exists() or not meta.exists():
        return None
    info = json.loads(meta.read_text(encoding="utf-8"))
    return lgb.Booster(model_file=str(p)), info["features"], info["leagues"]


def _train(month: str, rows: list[dict]):
    """Modell für ``month``: nur beendete Spiele vor dem Monatsersten."""
    import lightgbm as lgb
    import numpy as np
    cutoff = date.fromisoformat(month + "-01")
    train = [r for r in rows if r["game"].finished and r["game"].start_moscow.date() < cutoff
             and r["game"].home_score is not None and r["game"].away_score is not None
             and r["features"].get("fair_margin") is not None]
    if len(train) < MIN_TRAIN:
        return None
    names = _feature_names(train)
    leagues = {lg: i for i, lg in enumerate(sorted({r["features"].get("league") for r in train if r["features"].get("league")}))}
    x = np.array([_vector(r["features"], names, leagues) for r in train], dtype=float)
    y = np.array([(r["game"].home_score - r["game"].away_score) - r["features"]["fair_margin"] for r in train], dtype=float)
    ds = lgb.Dataset(x, y, feature_name=names, categorical_feature=["league_code"], free_raw_data=True)
    booster = lgb.train(PARAMS, ds, ROUNDS)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(_path(month)))
    _path(month).with_suffix(".json").write_text(json.dumps({"features": names, "leagues": leagues, "train_games": len(train)}),
                                                 encoding="utf-8")
    log.info("ML-Differenzmodell %s gelernt aus %s Spielen", month, len(train))
    return booster, names, leagues


def add_ml_margin(rows: list[dict], allow_training: bool = True, today: date | None = None) -> None:
    """Ergänzt ``ml_margin`` und ``ml_margin_plus_hdp`` in ``row["features"]``.

    ``allow_training=False`` (Auswahl einzelner Wettbewerbe): nur vorhandene Monatsmodelle nutzen.
    """
    try:
        import lightgbm  # noqa: F401
        import numpy as np
    except ImportError:
        return
    today = today or date.today()
    current = _month(today)
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["features"].get("fair_margin") is not None:
            # Spiele künftiger Monate nutzen das Modell des laufenden Monats
            by_month[min(_month(r["game"].start_moscow.date()), current)].append(r)
    for month in sorted(by_month):
        try:
            model = _load(month) or (_train(month, rows) if allow_training else None)
        except Exception:
            log.exception("ML-Differenzmodell %s fehlgeschlagen", month)
            model = None
        if model is None:
            continue
        booster, names, leagues = model
        group = by_month[month]
        preds = booster.predict(np.array([_vector(r["features"], names, leagues) for r in group], dtype=float))
        for r, p in zip(group, preds):
            f = r["features"]
            f["ml_margin"] = f["fair_margin"] + float(p)
            if f.get("hdp_line") is not None:
                f["ml_margin_plus_hdp"] = f["ml_margin"] + f["hdp_line"]
