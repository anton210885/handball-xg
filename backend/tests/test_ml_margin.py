import json
import random
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

lgb = pytest.importorskip("lightgbm")

from app import ml_margin


def _rows(n=400, start=datetime(2025, 1, 1), future=10):
    rnd = random.Random(1)
    rows = []
    for i in range(n + future):
        strength = rnd.uniform(-5, 5)
        finished = i < n
        fair = strength * 0.5
        margin = round(strength + rnd.gauss(0, 3))
        g = SimpleNamespace(id=i, start_moscow=start + timedelta(days=i // 4), finished=finished,
                            home_score=30 + margin if finished else None, away_score=30 if finished else None)
        f = {"fair_margin": fair, "power_rating": strength, "home_games": 10, "odds_home": 1.5, "hdp_line": -2.5,
             "league": "A" if i % 2 else "B", "sex": "men"}
        rows.append({"game": g, "features": f})
    return rows


@pytest.fixture
def tmp_models(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_margin, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml_margin, "MIN_TRAIN", 100)
    monkeypatch.setattr(ml_margin, "ROUNDS", 30)
    return tmp_path


def test_monthly_models_use_only_earlier_games(tmp_models):
    rows = _rows()
    last = max(r["game"].start_moscow for r in rows)
    ml_margin.add_ml_margin(rows, today=last.date())
    files = sorted(p.stem for p in tmp_models.glob("*.json"))
    assert files, "mindestens ein Monatsmodell"
    for stem in files:
        month = stem.rsplit("_", 1)[1]
        cutoff = date.fromisoformat(month + "-01")
        info = json.loads((tmp_models / f"{stem}.json").read_text())
        expected = sum(1 for r in rows if r["game"].finished and r["game"].start_moscow.date() < cutoff)
        assert info["train_games"] == expected
        # Linien und Quoten sind keine Eingabe
        assert "odds_home" not in info["features"] and "hdp_line" not in info["features"]
        assert "power_rating" in info["features"] and "fair_margin" in info["features"]
    with_ml = [r for r in rows if "ml_margin" in r["features"]]
    assert with_ml and all(r["features"]["ml_margin_plus_hdp"] == pytest.approx(r["features"]["ml_margin"] - 2.5) for r in with_ml)
    # Die ersten Monate haben zu wenige frühere Spiele -> leer
    assert "ml_margin" not in rows[0]["features"]


def test_future_months_use_current_model_and_no_training_without_permission(tmp_models):
    rows = _rows()
    today = date(2025, 3, 15)
    ml_margin.add_ml_margin(rows, allow_training=False, today=today)
    assert not list(tmp_models.glob("*.txt"))
    assert not any("ml_margin" in r["features"] for r in rows)
    ml_margin.add_ml_margin(rows, today=today)
    months = {p.stem.rsplit("_", 1)[1] for p in tmp_models.glob("*.txt")}
    assert max(months) == "2025-03"  # kein Modell für künftige Monate
    later = [r for r in rows if r["game"].start_moscow.date() >= date(2025, 4, 1)]
    assert later and all("ml_margin" in r["features"] for r in later)
