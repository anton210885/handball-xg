"""Beendete Spiele mit allen Metriken als Excel-Datei – Stand jeweils vor Anpfiff, wie die Strategien ihn sehen."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from . import features as feat
from .legacy import LEGACY_NAMES

STAGE_LABEL = {"league": "Hauptrunde", "knockout": "KO-Spiel", "placement": "Platzierungsrunde"}
BASE = [
    ("Datum (MSK)", "date"), ("Phase", "stage"), ("Heim", "home"), ("Gast", "away"),
    ("Tore Heim", "home_score"), ("Tore Gast", "away_score"), ("Tore gesamt", "total"),
    ("HZ Heim", "home_ht"), ("HZ Gast", "away_ht"), ("xG Heim", "home_xg"), ("xG Gast", "away_xg"),
    ("Over-Linie", "over_line"), ("Over", "result_over"), ("Handicap Heim", "hdp_line"), ("Handicap Heim gewinnt", "result_hdp"),
    ("Würfe vorhanden", "shots"),
]


def finished_rows(session, competition_id: int | None, stage: str = "", xg_sums: dict | None = None) -> list[dict]:
    xg_sums = xg_sums or {}
    out = []
    for r in feat.all_game_features(session, competition_id):
        g, f = r["game"], r["features"]
        if not g.finished or g.home_score is None or g.away_score is None:
            continue
        if stage and (g.stage_type or "unknown") != stage:
            continue
        total = g.home_score + g.away_score
        line, hdp = g.line.over_line if g.line else None, g.line.hdp_line if g.line else None
        margin = g.home_score - g.away_score
        out.append({
            "id": g.id, "date": g.start_moscow, "stage": STAGE_LABEL.get(g.stage_type, ""),
            "home": g.home_team.name, "away": g.away_team.name,
            "home_score": g.home_score, "away_score": g.away_score, "total": total,
            "home_ht": g.home_ht, "away_ht": g.away_ht,
            "home_xg": xg_sums.get((g.id, True)), "away_xg": xg_sums.get((g.id, False)),
            "over_line": line, "result_over": None if line is None else ("Push" if total == line else "Ja" if total > line else "Nein"),
            "hdp_line": hdp,
            "result_hdp": None if hdp is None else ("Push" if margin + hdp == 0 else "Ja" if margin + hdp > 0 else "Nein"),
            "shots": "Ja" if g.shots_imported else "Nein",
            "features": f,
        })
    return out


def to_xlsx(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Spiele"
    metrics = list(feat.FEATURES) + [n for n in LEGACY_NAMES if n not in feat.FEATURES]
    ws.append([label for label, _ in BASE] + metrics)
    for row in rows:
        values = [row[key] for _, key in BASE] + [row["features"].get(m) for m in metrics]
        ws.append([round(v, 4) if isinstance(v, float) else v for v in values])
    # Zweite Kopfzeile wäre für Filter störend – Beschreibungen der Metriken stehen auf einem eigenen Blatt
    names = wb.create_sheet("Metriken")
    names.append(["Name", "Beschreibung"])
    for k, label in feat.FEATURES.items():
        names.append([k, label])
    for sheet in (ws, names):
        sheet.freeze_panes = "E2" if sheet is ws else "A2"
        sheet.auto_filter.ref = sheet.dimensions
    for i in range(1, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(i)].width = 18 if i in (3, 4) else 12
    for c in ws["A"][1:]:
        c.number_format = "DD.MM.YYYY HH:MM"
    names.column_dimensions["A"].width, names.column_dimensions["B"].width = 34, 70
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
