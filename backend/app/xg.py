"""xG-Modell (Expected Goals) für Handball.

Idee: Die Torwahrscheinlichkeit eines Wurfs hängt vor allem davon ab, *wo* und
*wie* geworfen wird. Wir schätzen für jede Kombination aus Feldzone und
Angriffsart die Trefferquote aus allen Würfen der Datenbank.

Damit seltene Kombinationen (z. B. Gegenstoß von Rückraum rechts mit 3 Würfen)
nicht zu extremen Werten führen, wird jede Quote zur übergeordneten Ebene hin
„geschrumpft“ (empirischer Bayes / Beta-Binomial):

    Liga-Quote  →  Zonen-Quote  →  Zone × Angriffsart

    p = (Tore + k · p_eltern) / (Würfe + k)

k („shrinkage“) ist die Zahl der Würfe, ab der die eigene Quote mehr zählt als die
der Elternebene. Kleines k = datennäher, großes k = vorsichtiger.

xG eines Teams in einem Spiel = Summe der xG seiner Würfe.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import Shot

TRANSITION = {"fastbreak", "breakaway", "fast_center"}


def attack_group(attack_type: str | None) -> str:
    if attack_type in TRANSITION:
        return "transition"
    return "positional"


@dataclass
class Cell:
    shots: int = 0
    goals: int = 0
    rate: float = 0.0


@dataclass
class XgModel:
    shrinkage: float
    league: Cell
    zones: dict[str, Cell]
    cells: dict[tuple[str, str], Cell]  # (Zone, Angriffsgruppe)

    def predict(self, court_zone: str | None, attack_type: str | None) -> float:
        if court_zone is None:
            return self.league.rate
        if court_zone == "7m":
            return self.zones.get("7m", self.league).rate
        cell = self.cells.get((court_zone, attack_group(attack_type)))
        if cell:
            return cell.rate
        zone = self.zones.get(court_zone)
        return zone.rate if zone else self.league.rate

    def as_table(self) -> list[dict]:
        rows = []
        for (zone, group), c in sorted(self.cells.items()):
            z = self.zones[zone]
            rows.append({
                "zone": zone, "attack": group, "shots": c.shots, "goals": c.goals,
                "raw_rate": c.goals / c.shots if c.shots else None, "xg": c.rate,
                "zone_shots": z.shots, "zone_rate": z.rate,
            })
        return rows


def fit(shots: list[tuple[str | None, str | None, bool]], shrinkage: float = 30.0) -> XgModel:
    """shots: Liste von (Feldzone, Angriffsart, Tor ja/nein)."""
    return fit_counts(Counter(shots), shrinkage)


def fit_counts(counts: dict[tuple[str | None, str | None, bool], int], shrinkage: float = 30.0) -> XgModel:
    """Wie fit, mit aggregierten Wurfzahlen für zeitlich fortlaufendes Lernen."""
    league = Cell()
    zones: dict[str, Cell] = defaultdict(Cell)
    cells: dict[tuple[str, str], Cell] = defaultdict(Cell)
    for (zone, attack, is_goal), count in counts.items():
        league.shots += count
        league.goals += count if is_goal else 0
        if zone is None:
            continue
        zones[zone].shots += count
        zones[zone].goals += count if is_goal else 0
        if zone != "7m":
            key = (zone, attack_group(attack))
            cells[key].shots += count
            cells[key].goals += count if is_goal else 0

    league.rate = league.goals / league.shots if league.shots else 0.5
    for z in zones.values():
        z.rate = (z.goals + shrinkage * league.rate) / (z.shots + shrinkage)
    for (zone, _), c in cells.items():
        parent = zones[zone].rate
        c.rate = (c.goals + shrinkage * parent) / (c.shots + shrinkage)
    return XgModel(shrinkage, league, dict(zones), dict(cells))


def fit_from_db(session: Session, shrinkage: float = 30.0) -> XgModel:
    rows = session.execute(select(Shot.court_zone, Shot.attack_type, Shot.outcome)).all()
    return fit([(z, a, o == "goal") for z, a, o in rows], shrinkage)


def recompute_all(session: Session, shrinkage: float = 30.0) -> XgModel:
    """Modell neu schätzen und xG für jeden Wurf in der DB speichern."""
    model = fit_from_db(session, shrinkage)
    rows = session.execute(select(Shot.id, Shot.court_zone, Shot.attack_type)).all()
    session.execute(
        update(Shot),
        [{"id": sid, "xg": model.predict(z, a)} for sid, z, a in rows],
    )
    session.commit()
    return model
