from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from app import strategies
from app.analysis import analyze, correlation


def row(i, value, win=True, odds=1.8):
    return {'game': SimpleNamespace(id=i, start_moscow=datetime(2025, 1, 1)+timedelta(days=i),
            finished=True, home_score=31 if win else 28, away_score=29),
            'features': {'metric':value, 'constant':1, 'over_line':59.5, 'odds_over':odds}}


def strategy():
    return SimpleNamespace(market='over', rules=[], min_games=0, stake=10, min_odds=None, max_odds=None)


def test_draw_and_five_markets():
    assert set(strategies.MARKETS) == {'home','draw','away','over','under'}
    g=SimpleNamespace(finished=True, home_score=30, away_score=30)
    assert strategies.settle('draw',g,{'odds_draw':8}) == ('win',8)
    assert strategies.settle('home',g,{'odds_home':2}) == ('loss',2)
    assert strategies.settle('away',g,{'odds_away':2}) == ('loss',2)
    g.away_score=29
    assert strategies.settle('draw',g,{'odds_draw':8}) == ('loss',8)
    assert strategies.settle('draw',g,{}) == (None,0)
    g.away_score=None
    assert strategies.settle('draw',g,{'odds_draw':8}) == (None,0)


def test_correlation_and_degenerate_samples():
    assert correlation([(1,1),(2,2),(3,3)]) == pytest.approx(1)
    assert correlation([(1,3),(2,2),(3,1)]) == pytest.approx(-1)
    assert correlation([(1,3)]*5) is None
    assert correlation([(1,1),(2,2)]) is None


def test_bins_partition_all_bets_and_reuse_training_boundaries():
    rows=[row(i,i,i%2==0) for i in range(10)]
    result=analyze(strategy(),rows,{'metric':'Metric','constant':'Constant'})
    metric=next(m for m in result['metrics'] if m['key']=='metric')
    assert result['train']['bets']==7
    assert result['test']['bets']==3
    assert sum(b['train']['bets'] for b in metric['bins'])==7
    assert sum(b['test']['bets'] for b in metric['bins'])==3
    assert sum(b['train']['profit']+b['test']['profit'] for b in metric['bins'])==pytest.approx(result['overall']['profit'])
    assert result['overall']['roi']==pytest.approx(result['overall']['profit']/100)
    original=[(b['lower'],b['upper']) for b in metric['bins']]
    for r in rows[7:]: r['features']['metric']=10000
    revised=analyze(strategy(),rows,{'metric':'Metric'})
    assert [(b['lower'],b['upper']) for b in revised['metrics'][0]['bins']]==original
    assert next(m for m in result['metrics'] if m['key']=='constant')['correlation'] is None


def test_missing_and_empty_data():
    assert analyze(strategy(),[],{'metric':'Metric'})['metrics']==[]
    rows=[row(i,i) for i in range(10)]
    rows[0]['features']['metric']=None
    result=analyze(strategy(),rows,{'metric':'Metric'})
    assert result['metrics'][0]['missing']==1
    assert result['metrics'][0]['coverage']==6

def test_fixed_odds_and_inclusive_bookmaker_line_range():
    rows=[row(i,i,True,odds=4.0) for i in range(5)]
    for r,line in zip(rows,[50,50.5,52.5,54.5,55]):
        r['features']['over_line']=line
    s=strategy()
    s.rules=[{'feature':'over_line','op':'>=','value':50.5}, {'feature':'over_line','op':'<=','value':54.5}]
    result=analyze(s,rows,{'metric':'Metric'},fixed_odds=1.8)
    assert result['overall']['bets']==3
    assert result['overall']['avg_odds']==pytest.approx(1.8)
    assert result['overall']['profit']==pytest.approx(24)
    assert all(r['features']['odds_over']==4.0 for r in rows)

@pytest.mark.parametrize('market', ['home','draw','away','over','under'])
def test_analysis_market_quote_filter_uses_actual_odds(market):
    s=strategy()
    s.market=market
    s.min_odds=1.8
    s.max_odds=2.0
    rows=[row(i,i) for i in range(4)]
    for r,odds in zip(rows,[1.79,1.8,2.0,2.01]):
        r['features'][f'odds_{market}']=odds
    result=analyze(s,rows,{'metric':'Metric'})
    assert result['overall']['bets']==2
    assert result['overall']['avg_odds']==pytest.approx(1.9)

def test_combined_home_away_and_metric_filters_apply_to_correlation_and_bins():
    rows=[row(i,i,win=i%2==0) for i in range(20)]
    for i,r in enumerate(rows):
        r['features'].update(odds_home=1.8 if i != 6 else 2.5, odds_away=2.2 if i != 8 else None)
    s=strategy()
    s.min_odds=1.8
    s.max_odds=1.8
    s.rules=[{'feature':'odds_home','op':'>=','value':1.7},
             {'feature':'odds_home','op':'<=','value':2.0},
             {'feature':'odds_away','op':'>=','value':2.0},
             {'feature':'metric','op':'>=','value':4},
             {'formula':'metric < 16'}]
    result=analyze(s,rows,{'metric':'Metric'})
    expected=[r for r in rows if 4 <= r['features']['metric'] < 16 and r['game'].id not in (6,8)]
    assert result['overall']['bets']==len(expected)==10
    assert result['overall']['profit']==pytest.approx(sum(8 if r['game'].id%2==0 else -10 for r in expected))
    filtered=analyze(strategy(),expected,{'metric':'Metric'})
    assert result['metrics']==filtered['metrics']
    assert result['train']==filtered['train']
    assert result['test']==filtered['test']


def test_no_optional_quote_filters_allow_missing_unrelated_quotes():
    rows=[row(i,i) for i in range(10)]
    for r in rows: r['features'].update(odds_home=None,odds_away=None)
    result=analyze(strategy(),rows,{'metric':'Metric'})
    assert result['overall']['bets']==10

def test_correlations_sorted_numerically_descending_with_missing_last():
    rows=[row(i,1 if i%2==0 else 0,win=i%2==0) for i in range(10)]
    for r in rows:
        r['features']['negative']=-r['features']['metric']
        r['features']['constant']=1
    result=analyze(strategy(),rows,{'negative':'Negative','constant':'Constant','metric':'Positive'})
    assert [m['key'] for m in result['metrics']]==['metric','negative','constant']
    assert result['metrics'][0]['correlation']==pytest.approx(1)
    assert result['metrics'][1]['correlation']==pytest.approx(-1)
    assert result['metrics'][2]['correlation'] is None
