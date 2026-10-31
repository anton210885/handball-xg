"""Formeln und Herkunft aller erlaubten Vor-Spiel-Metriken."""
from .features import FEATURES
from .legacy import LEGACY_NAMES

BASE = {'pred_home': ('Erwartete Heimtore aus eigener bisheriger Chancenqualität und bisher zugelassenen Chancen des Gastes.',
               '(home_avg_xg + away_avg_xga) / 2'),
 'pred_away': ('Erwartete Gasttore aus eigener bisheriger Chancenqualität und bisher zugelassenen Chancen des '
               'Heimteams.',
               '(away_avg_xg + home_avg_xga) / 2'),
 'pred_total': ('Summe der erwarteten Tore beider Teams.', 'pred_home + pred_away'),
 'pred_margin': ('Erwarteter Vorsprung des Heimteams. Positive Werte sprechen für Heim.', 'pred_home − pred_away'),
 'pred_total_goals': ('Torprognose aus bisherigen tatsächlichen Toren und Gegentoren statt xG.',
                      '(home_avg_goals + away_avg_goals_against + away_avg_goals + home_avg_goals_against) / 2'),
 'power_rating': ('Verhältnis der erwarteten Heim- zu Gasttoren; größer als 1 bedeutet höherer Heimwert.',
                  'pred_home / pred_away'),
 'pred_home_gk': ('Heimprognose ergänzt um bisherigen eigenen Abschlussüberschuss und bisherige Torwartleistung des '
                  'Gegners.',
                  'pred_home + home_finishing − away_keeper'),
 'pred_away_gk': ('Gastprognose ergänzt um bisherigen eigenen Abschlussüberschuss und bisherige Torwartleistung des '
                  'Gegners.',
                  'pred_away + away_finishing − home_keeper'),
 'pred_total_gk': ('Summe der um Abschluss und Torwart korrigierten Prognosen.', 'pred_home_gk + pred_away_gk'),
 'pred_margin_gk': ('Heimvorsprung nach Abschluss-/Torwartkorrektur.', 'pred_home_gk − pred_away_gk'),
 'pred_total_minus_line': ('Abstand der Prognose zur Bookmaker-Torlinie. Positiv bedeutet Prognose oberhalb der Linie.',
                           'pred_total − over_line'),
 'pred_total_gk_minus_line': ('Abstand der korrigierten Gesamtprognose zur Torlinie.', 'pred_total_gk − over_line'),
 'pred_margin_plus_hdp': ('Erwarteter Heimvorsprung einschließlich Handicap aus Heimsicht.', 'pred_margin + hdp_line'),
 'pred_total_gk_last5': ('Formprognose: eigene xG plus eigener Abschlussüberschuss minus gegnerische Torwartleistung; '
                         'jeweils Mediane der letzten bis zu fünf Spiele.',
                         'home_last5_xg_median + home_last5_finishing_median − away_last5_keeper_median + '
                         'away_last5_xg_median + away_last5_finishing_median − home_last5_keeper_median'),
 'pred_total_gk_last5_minus_line': ('Formprognose der letzten bis zu fünf Spiele minus Bookmaker-Torlinie.',
                                    'pred_total_gk_last5 − over_line'),
 'avg_xg_sum_minus_line': ('Summe eigener durchschnittlicher xG beider Teams minus Torlinie; keine Mittelung mit '
                           'gegnerischen xG gegen.',
                           'home_avg_xg + away_avg_xg − over_line'),
 'last5_xg_sum_minus_line': ('Summe der eigenen xG-Mediane der letzten bis zu fünf Spiele minus Torlinie.',
                             'home_last5_xg_median + away_last5_xg_median − over_line')}
BASE["pred_total_goals_minus_line"] = ("Vor-Spiel-Torprognose aus früheren Toren und Gegentoren minus Torlinie; auch ohne Wurfstatistik nutzbar.", "pred_total_goals − over_line")
TEAM = {'avg_goals': ('Erzielte Tore je früherem Spiel.', 'gewichteter Mittelwert(Tore)'),
 'avg_goals_against': ('Kassierte Tore je früherem Spiel.', 'gewichteter Mittelwert(Gegentore)'),
 'avg_xg': ('Eigene Chancenqualität je früherem Spiel. xG pro Spiel = Summe der Wurf-Torwahrscheinlichkeiten.',
            'gewichteter Mittelwert(xG)'),
 'avg_xga': ('Zugelassene Chancenqualität je früherem Spiel.', 'gewichteter Mittelwert(xG des Gegners)'),
 'avg_total': ('Tore beider Teams zusammen je früherem Spiel.', 'gewichteter Mittelwert(Tore + Gegentore)'),
 'finishing': ('Abschlussüberschuss: mehr Tore als nach Chancenqualität erwartet. Positive Werte bedeuten bisher über '
               'Erwartung abgeschlossen.',
               'gewichteter Mittelwert(Tore − xG)'),
 'keeper': ('Torwart-/Defensivabwehr: positive Werte bedeuten weniger Gegentore als nach gegnerischen Chancen '
            'erwartet. Kein isolierter kausaler Torwart-Effekt.',
            'gewichteter Mittelwert(xG gegen − Gegentore)'),
 'avg_attacks': ('Angriffe pro früherem Spiel; nur Spiele mit vorhandener positiver Angriffszahl.',
                 '(Summe aktuelle Angriffe + k × Ø Vorsaison-Angriffe) / (Anzahl gültiger Spiele + k)'),
 'xg_per_attack': ('Chancenqualität je Angriff; Verhältnis der Summen, nicht Durchschnitt einzelner Quoten.',
                   '(Summe aktuelle xG + k × Ø Vorsaison-xG) / (Summe aktuelle Angriffe + k × Ø Vorsaison-Angriffe)'),
 'last5_xg_median': ('Median eigener xG aus den letzten bis zu fünf früheren Spielen.',
                     'Median(xG der letzten bis zu 5 Spiele)'),
 'last5_total_median': ('Median der Gesamttore aus den letzten bis zu fünf früheren Spielen.',
                        'Median(Tore + Gegentore der letzten bis zu 5 Spiele)'),
 'last5_finishing_median': ('Median des Abschlussüberschusses aus den letzten bis zu fünf früheren Spielen.',
                            'Median(Tore − xG der letzten bis zu 5 Spiele)'),
 'last5_keeper_median': ('Median der Torwart-/Defensivabweichung aus den letzten bis zu fünf früheren Spielen.',
                         'Median(xG gegen − Gegentore der letzten bis zu 5 Spiele)'),
 'over_hits_last5': ('Anzahl früherer Spiele über ihrer damaligen Torlinie, in den letzten bis zu fünf Spielen. Spiele '
                     'ohne Linie zählen nicht. Das ist eine Anzahl, keine Trefferquote.',
                     'Anzahl(Tore + Gegentore > damalige over_line)'),
 'prev_games': ('Anzahl berücksichtigter früherer Spiele der verknüpften Vorsaison.',
                'Anzahl gültiger Vorsaisonspiele vor dem Zielspiel)'),
 'weight_current': ('Anteil aktueller Saison an gewichteten Mittelwerten; 0 bis 1.',
                    'n / (n + k), n = bisherige Spiele, k = Vorsaisongewicht'),
 'games': ('Anzahl früherer Spiele derselben Saison mit importierten Würfen.',
           'Anzahl abgeschlossener Spiele an früheren Kalendertagen)')}
LEGACY_FORMULAS = {'sex': 'gender',
 'tour': '40 bei KO-Spiel, sonst min(home_games, away_games) + 1',
 'home': 'odds_home',
 'Draw': 'odds_draw',
 'away': 'odds_away',
 'over': 'over_line',
 'hdp': 'hdp_line',
 'Home_avgXG': 'home_avg_xg',
 'Away_avgXG': 'away_avg_xg',
 'Home_avgXGA': 'home_avg_xga',
 'Away_avgXGA': 'away_avg_xga',
 'home_expGoal': 'pred_home',
 'away_expGoal': 'pred_away',
 'home_XGD': 'home_finishing',
 'away_XGD': 'away_finishing',
 'home_XGAD': '−home_keeper',
 'away_XGAD': '−away_keeper',
 'home_Last_5_XG_Median': 'home_last5_xg_median',
 'away_Last_5_XG_Median': 'away_last5_xg_median',
 'home_Last_5_XGD_Median': 'home_last5_finishing_median',
 'away_Last_5_XGD_Median': 'away_last5_finishing_median',
 'home_Last_5_XGAD_Median': '−home_last5_keeper_median',
 'away_Last_5_XGAD_Median': '−away_last5_keeper_median',
 'home_count_over_bet_0_8_last5': 'home_over_hits_last5',
 'away_count_over_bet_0_8_last5': 'away_over_hits_last5',
 'difference_avgXG': '(Home_avgXG + −Away_avgXG)',
 'differenceSum_avgXG': '(Home_avgXG + Away_avgXG)',
 'powerRaiting_avgXG': '(Home_avgXG / Away_avgXG)',
 'powerRaiting_avgXGA': '(Home_avgXGA / Away_avgXGA)',
 'powerRaiting_expGoals': '(home_expGoal / away_expGoal)',
 'differenceSum_expGoal': '(home_expGoal + away_expGoal)',
 'difference_expGoal': '(home_expGoal + −away_expGoal)',
 'homeExpGoal_with_GK': '(Home_avgXG + home_XGD + away_XGAD)',
 'awayExpGoal_with_GK': '(Away_avgXG + away_XGD + home_XGAD)',
 'Sum_expGoal_with_GK': '(homeExpGoal_with_GK + awayExpGoal_with_GK)',
 'powerRaiting_expGoals_with_GK': '(homeExpGoal_with_GK / awayExpGoal_with_GK)',
 'difference_expGoals_with_GK': '(homeExpGoal_with_GK + −awayExpGoal_with_GK)',
 'homeExpGoal_with_GK_power': '(home_expGoal + home_XGD + away_XGAD)',
 'awayExpGoal_with_GK_power': '(away_expGoal + away_XGD + home_XGAD)',
 'Sum_expGoal_with_GK_power': '(homeExpGoal_with_GK_power + awayExpGoal_with_GK_power)',
 'powerRaiting_expGoals_with_GK_power': '(homeExpGoal_with_GK_power / awayExpGoal_with_GK_power)',
 'difference_expGoals_with_GK_power': '(homeExpGoal_with_GK_power + −awayExpGoal_with_GK_power)',
 'differenceSum_expGoal_to_over': '(differenceSum_expGoal + −over)',
 'differenceSum_avgXG_to_over': '(differenceSum_avgXG + −over)',
 'differenceSum_expGoals_with_GK_to_over': '(Sum_expGoal_with_GK + −over)',
 'differenceSum_expGoals_with_GK_power_to_over': '(Sum_expGoal_with_GK_power + −over)',
 'last5_Games_difference_XG': '(home_Last_5_XG_Median + −away_Last_5_XG_Median)',
 'last5_Games_Sum_XG': '(home_Last_5_XG_Median + away_Last_5_XG_Median)',
 'last5_Games_powerRaiting_XG': '(home_Last_5_XG_Median / away_Last_5_XG_Median)',
 'last5_Games_powerRaiting_XGA': '(home_Last_5_XG_Median / away_Last_5_XG_Median)',
 'last5_Games_differenceSum_XG_to_over': '(last5_Games_Sum_XG + −over)',
 'last5_Games_homeExpGoal_with_GK': '(home_Last_5_XG_Median + home_Last_5_XGD_Median + away_Last_5_XGAD_Median)',
 'last5_Games_awayExpGoal_with_GK': '(away_Last_5_XG_Median + away_Last_5_XGD_Median + home_Last_5_XGAD_Median)',
 'last5_Games_Sum_expGoal_with_GK': '(last5_Games_homeExpGoal_with_GK + last5_Games_awayExpGoal_with_GK)',
 'last5_Games_powerRaiting_expGoals_with_GK': '(last5_Games_homeExpGoal_with_GK / last5_Games_awayExpGoal_with_GK)',
 'last5_Games_difference_expGoals_with_GK': '(last5_Games_homeExpGoal_with_GK + −last5_Games_awayExpGoal_with_GK)',
 'last5_Games_differenceSum_expGoals_with_GK_to_over': '(last5_Games_Sum_expGoal_with_GK + −over)',
 'Sum_count': '(home_count_over_bet_0_8_last5 + away_count_over_bet_0_8_last5)'}

TIMING = "Nur frühere Kalendertage; aktuelles Spiel, spätere Spiele und Spiele desselben Tages sind ausgeschlossen."
HISTORY = "Teamhistorie desselben Wettbewerbs, optional verknüpfte Vorsaison derselben Liga/Geschlechtsgruppe. Mittelwerte: (Summe aktuell + k × Ø Vorsaison) / (n + k); k standardmäßig 3. Ohne Vorsaison k = 0. Letzte 5: aktuelle Historie, am Saisonanfang ergänzt aus der Vorsaison."
XG = "Wurfmodell: Zone × Angriffsgruppe (Position/Umschalten), hierarchische Glättung k = 30. Pro historischem Spiel nur Lerndaten früherer Tage derselben Liga und Geschlechtsgruppe; ohne Lerndaten neutrale Wurfchance 0,5. Gespeicherte, nachträglich neu geschätzte Shot.xg werden für Strategien nicht verwendet. Bei aggregierten Statistiken ohne verlässliche Kategorie-Tore gilt ein getrenntes gröberes Modell: Gesamtwürfe × geglättete Torquote ausschließlich früherer Spiele derselben Liga/Geschlechtsgruppe. Ergebnisse ohne Wurfzahlen liefern keine xG; xG-Mittelwerte berücksichtigen nur vorhandene Werte."
BOOK = "Eingegebene Bookmaker-Pre-Match-Quote bzw. -Linie. Der ursprüngliche Erfassungszeitpunkt ist historisch nicht versioniert; die Eingabe muss tatsächlich vor dem Spiel verfügbar gewesen sein. Keine Ergebnis-Ableitung."


def metric_docs():
    docs = {}
    for key, label in FEATURES.items():
        if key in BASE:
            description, formula = BASE[key]
            source = HISTORY + " " + XG
        elif key in ("is_knockout", "is_league"):
            description = ("1, wenn das Spiel laut Quelle ein KO-Spiel ist (Viertel-/Halbfinale, Finale, Spiele um Plätze), sonst 0."
                           if key == "is_knockout" else "1, wenn das Spiel zur Hauptrunde gehört, sonst 0 (KO-Spiel oder Platzierungsrunde 9–12).")
            description += " Leer, wenn die Quelle keine Phase kennt (Bundesliga, EHF)."
            formula, source = "Spielphase: " + key, "rushandball-Spielplan (Russland), koreahandball (Korea), Access-Spalte tour (40 = Playoff)."
        elif key in ("over_line", "hdp_line") or key.startswith("odds_"):
            description = "Bookmaker-Gesamttorlinie für Over/Under." if key == "over_line" else "Handicap aus Sicht des Heimteams." if key == "hdp_line" else "Dezimalquote für " + label.replace("Quote ", "") + "."
            formula, source = "Direkte Eingabe: " + key, BOOK
        else:
            side = "home" if key.startswith("home_") else "away"
            suffix = key[len(side)+1:]
            description, formula = TEAM[suffix]
            description = ("Heimteam: " if side == "home" else "Gastteam: ") + description
            source = HISTORY + (" " + XG if "xg" in suffix or "finishing" in suffix or "keeper" in suffix else "")
        docs[key] = {"label":label, "description":description, "formula":formula, "source":source,
                     "timing": BOOK if key.startswith("odds_") or key in ("over_line", "hdp_line") else TIMING}
    for key in LEGACY_NAMES:
        formula = LEGACY_FORMULAS[key]
        description = "Alter Formelname; Berechnung aus den oben dokumentierten Vor-Spiel-Werten. Fehlende Eingaben oder Division durch 0 ergeben keinen Wert."
        if key == "tour": description = "Wie in der Access-Datenbank: 40 bei einem KO-Spiel, sonst Näherung für den Spieltag: min(home_games, away_games) + 1."
        if key == "sex": description = "Bekannte Geschlechtsgruppe des Wettbewerbs (men/women); keine numerische Korrelationsmetrik."
        if key == "last5_Games_powerRaiting_XGA": description = "Historischer Kompatibilitätsname: berechnet tatsächlich den Quotienten eigener xG-Mediane, nicht xG gegen."
        if formula in docs:
            description = "Alias von " + formula + ": " + docs[formula]["description"]
        source, timing = HISTORY + " " + XG, TIMING
        if formula in docs:
            source, timing = docs[formula]["source"], docs[formula]["timing"]
        if key == "sex":
            source, timing = "Stammdaten des Wettbewerbs.", "Vor dem Spiel bekannte Wettbewerbszuordnung."
        if key == "tour":
            source = "Anzahl früherer Spiele beider Teams; Näherung, kein offizieller Spieltag."
        docs[key] = {"label":key, "description":description, "formula":formula, "source":source, "timing":timing}
    return docs
