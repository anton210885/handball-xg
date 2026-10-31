"""Einfügen von Quotentabellen: verschiedene Kopierformate, Regel 1,70–2,00."""
from app.odds_paste import parse

# Übersicht: eine Zeile je Linie mit Anzahl Buchmacher, Ø Over, Ø Under, Auszahlung
SUMMARY = """
Over/Under +55.5   12   1.42   2.75   93.5%
Over/Under +56.5   14   1.55   2.35   93.4%
Over/Under +57.5   18   1.80   1.95   93.6%
Over/Under +58.5   15   2.05   1.70   92.9%
Over/Under +59.5   10   2.40   1.52   93.1%
"""

# Aufgeklappt: jede Zelle in eigener Zeile, mehrere Buchmacher je Linie
EXPANDED = """
Over/Under +58.5
Bookmakers
Over
Under
Payout
bet365
1.83
1.91
93.6%
Pinnacle
1.87
1.95
95.4%
1xBet
1.85
1.93
94.8%
Over/Under +61.5
bet365
2.62
1.44
"""

HANDICAP = """
Asian Handicap -4.5   9   2.10   1.68   93.2%
Asian Handicap -3.5   11  1.86   1.90   93.9%
Asian Handicap -2.5   8   1.62   2.20   93.3%
"""

X12 = """
1X2  Bookmakers  1  X  2  Payout
bet365  1.25  9.00  6.50  93.1%
Pinnacle  1.27  9.50  6.80  95.6%
1xBet  1.26  9.20  6.60  94.5%
"""


def test_summary_rows_pick_line_in_range():
    r = parse(SUMMARY)
    assert r["over_line"] == 57.5 and (r["odds_over"], r["odds_under"]) == (1.80, 1.95)
    assert [x["line"] for x in r["lines"]] == [55.5, 56.5, 57.5, 58.5, 59.5]
    assert r["warnings"] == []


def test_expanded_cells_use_median_of_bookmakers():
    r = parse(EXPANDED)
    assert r["over_line"] == 58.5
    assert (r["odds_over"], r["odds_under"]) == (1.85, 1.93)
    assert next(x for x in r["lines"] if x["line"] == 58.5)["count"] == 3


def test_handicap_and_1x2_together_with_totals():
    r = parse(X12 + SUMMARY + HANDICAP)
    assert r["hdp_line"] == -3.5
    assert (r["odds_home"], r["odds_draw"], r["odds_away"]) == (1.26, 9.2, 6.6)
    assert r["over_line"] == 57.5


def test_comma_decimals():
    r = parse("O/U 58,5   1,84   1,92\nO/U 59,5   2,10   1,66")
    assert r["over_line"] == 58.5 and r["odds_over"] == 1.84


def test_nothing_recognised():
    r = parse("Akbuzat – Dinamo Astrakhan, 25 Oct 2025, 15:00, Endstand 28:30")
    assert "over_line" not in r and r["warnings"]


def test_no_line_in_range_warns():
    r = parse("Over/Under +50.5 1.20 4.10\nOver/Under +65.5 4.30 1.18")
    assert "over_line" not in r
    assert any("1,70 und 2,00" in w for w in r["warnings"])


# oddsportal-Übersicht mit jeder Zelle in eigener Zeile: Anzahl Buchmacher direkt nach der Linie
ODDSPORTAL_AH = """
Asian Handicap +6.25
3
1.99
1.59
88.4%
Asian Handicap +6.5
4
1.95
1.75
87.0%
Asian Handicap +7.25
3
1.74
1.79
88.2%
"""


def test_bookmaker_count_after_line_decides_tie():
    r = parse(ODDSPORTAL_AH)
    assert r["hdp_line"] == 6.5  # 4 Buchmacher schlagen die ausgeglichenere Linie mit 3
    assert [h["count"] for h in r["handicaps"]] == [3, 4, 3]
    assert r["handicaps"][1]["a"] == 1.95
