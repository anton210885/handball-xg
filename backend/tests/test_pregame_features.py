from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Competition, Game, Shot, Team
from app.features import all_game_features, FEATURES
from app.metric_docs import metric_docs
from app.legacy import LEGACY_NAMES
from app.main import KNOWN_NAMES
from app.strategies import validate_rules, FormulaError


@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([Team(id=1,name='A'),Team(id=2,name='B'),Team(id=3,name='C'),Team(id=4,name='D')])
        s.add(Competition(id=1,name='League Männer – Vorrunde',season='24/25',gender='men'))
        s.flush()
        yield s
    engine.dispose()


def game(s, gid, day, comp=1, home=1, away=2, score=(2,1), hour=12, goal=True):
    g=Game(id=gid,competition_id=comp,start_moscow=datetime(2025,1,1)+timedelta(days=day,hours=hour),
           home_team_id=home,away_team_id=away,home_score=score[0],away_score=score[1],finished=True,shots_imported=True)
    s.add(g);s.flush()
    for side in [True,False]:
        s.add(Shot(id=gid*10+int(side),game_id=gid,team_id=home if side else away,is_home=side,
                   period=1,minute=5,outcome='goal' if goal else 'save',court_zone='line',attack_type='positional',xg=.999))
    s.flush()
    return g


def features(s,gid,comp=1,prior_weight=None):
    return next(r['features'] for r in all_game_features(s,comp,prior_weight) if r['game'].id==gid)


def test_current_result_and_future_games_cannot_change_pregame_features(db):
    game(db,1,0)
    current=game(db,2,2)
    before=features(db,2)
    assert before['home_avg_xg']==pytest.approx(.5)  # No older training data for first game.
    current.home_score=100
    for shot in db.query(Shot).filter_by(game_id=2): shot.outcome='save';shot.xg=.001
    game(db,3,10,score=(100,0),goal=False)
    db.flush()
    assert features(db,2)==before
    # Even a global after-the-fact xG recomputation cannot alter historical inputs.
    for shot in db.query(Shot):shot.xg=.02
    db.flush()
    assert features(db,2)==before


def test_same_day_games_are_not_known_before_kickoff(db):
    game(db,1,0)
    game(db,2,2,hour=10)
    game(db,3,2,hour=20)
    a,b=features(db,2),features(db,3)
    assert a==b
    assert a['home_games']==1


def test_xg_training_is_separate_by_gender_and_league(db):
    game(db,1,0);game(db,2,2)
    before=features(db,2)
    db.add_all([Competition(id=2,name='League Frauen – Vorrunde',season='24/25',gender='women'),
                Competition(id=3,name='Different Männer – Vorrunde',season='24/25',gender='men')]);db.flush()
    game(db,3,-10,comp=2,home=3,away=4,goal=False)
    game(db,4,-9,comp=3,home=3,away=4,goal=False)
    assert features(db,2)==before


def test_prior_history_must_be_before_game_and_same_group(db):
    db.add(Competition(id=2,name='League Männer – Vorrunde',season='23/24',gender='men'));db.flush()
    db.get(Competition,1).previous_competition_id=2
    game(db,1,-10,comp=2,score=(12,10))
    game(db,2,10,comp=2,score=(100,100))
    game(db,3,0)
    value=features(db,3,prior_weight=3)
    assert value['home_prev_games']==1
    assert value['home_avg_goals']==12
    assert value['home_games']==0
    db.get(Competition,2).gender='women';db.flush()
    assert features(db,3,prior_weight=3)['home_prev_games']==0
    assert 'pred_total' not in features(db,3,prior_weight=3)


def test_prior_season_is_off_by_default(db):
    db.add(Competition(id=2,name='League Männer – Vorrunde',season='23/24',gender='men'));db.flush()
    db.get(Competition,1).previous_competition_id=2
    game(db,1,-10,comp=2,score=(12,10))
    game(db,3,0)
    value=features(db,3)
    assert value['home_prev_games']==0
    assert 'pred_total' not in value


def test_all_competitions_preserve_season_scope_and_gender(db):
    db.add(Competition(id=2,name='League Männer – Vorrunde',season='25/26',gender='men'));db.flush()
    game(db,1,0);game(db,2,2,comp=2)
    all_rows=all_game_features(db)
    second=next(r['features'] for r in all_rows if r['game'].id==2)
    assert second['home_games']==0
    assert second['sex']=='men'


def test_every_allowed_feature_has_documentation_and_outcomes_are_blocked():
    docs=metric_docs()
    assert set(docs)==set(FEATURES)|set(LEGACY_NAMES)
    assert all(all(d[field] for field in ['description','formula','source','timing']) for d in docs.values())
    for name in ['home_score','away_score','home_ht','away_ht','Home_Goal','profit','result','home_xg']:
        with pytest.raises(FormulaError):validate_rules([{'feature':name,'op':'>','value':0}],KNOWN_NAMES)
        with pytest.raises(FormulaError):validate_rules([{'formula':f'{name} > 0'}],KNOWN_NAMES)

def test_rolling_xg_uses_only_older_training_games(db):
    game(db,1,0,goal=True)
    game(db,2,2,goal=True)
    target=game(db,3,4,goal=False)
    before=features(db,3)
    assert before['home_avg_xg']==pytest.approx(.75)  # first game .5, second game 1.0
    target.home_score=0
    for shot in db.query(Shot).filter_by(game_id=3):shot.outcome='goal'
    game(db,4,20,goal=False)
    db.flush()
    assert features(db,3)==before


def test_same_day_outcomes_do_not_train_each_other_xg(db):
    game(db,1,0,hour=10,goal=True)
    game(db,2,0,hour=20,goal=True)
    game(db,3,2)
    value=features(db,3)
    assert value['home_avg_xg']==pytest.approx(.5)
    assert value['home_games']==2


def test_results_without_shots_keep_goals_metrics_and_missing_xg(db):
    from app.models import AggregateStat
    g=game(db,1,0,score=(30,20));g.shots_imported=False
    game(db,2,2)
    values=features(db,2)
    assert values['home_avg_goals']==30
    assert values['home_avg_xg'] is None
    assert values['pred_total_goals']==50
    assert 'pred_total' not in values


def test_aggregate_xg_uses_only_earlier_outcomes(db):
    from app.models import AggregateStat
    g1=game(db,1,0,score=(30,20));g1.shots_imported=False;g1.stats_imported=True
    db.add_all([AggregateStat(game_id=1,is_home=True,shots=50,goals=30,source='test'),AggregateStat(game_id=1,is_home=False,shots=40,goals=20,source='test')])
    g2=game(db,2,2,score=(30,20));g2.shots_imported=False;g2.stats_imported=True
    db.add_all([AggregateStat(game_id=2,is_home=True,shots=50,goals=30,source='test'),AggregateStat(game_id=2,is_home=False,shots=40,goals=20,source='test')])
    game(db,3,4);db.flush()
    before=features(db,3)
    assert before['home_avg_xg']==pytest.approx((25+50*(50+15)/(90+30))/2)
    future=game(db,4,10,score=(100,100));future.shots_imported=False;future.stats_imported=True
    db.add_all([AggregateStat(game_id=4,is_home=True,shots=100,goals=100,source='test'),AggregateStat(game_id=4,is_home=False,shots=100,goals=100,source='test')]);db.flush()
    assert features(db,3)==before


def test_repeated_api_import_is_idempotent(db):
    from app.unified_import import import_event
    from app.models import SourceRecord
    from sqlalchemy import select,func
    event={'id':123456,'startTimestamp':1725555600,'homeTeam':{'id':100,'name':'Home'},'awayTeam':{'id':200,'name':'Away'},'homeScore':{'current':30},'awayScore':{'current':25},'status':{'type':'finished'}}
    meta={'country':'Germany','league':'Bundesliga','gender':'men','season':'24/25','tournament_id':149,'season_id':64159}
    first=import_event(db,event,meta);db.flush()
    second=import_event(db,event,meta);db.flush()
    assert first.id==second.id
    assert db.scalar(select(func.count()).select_from(Game))==1
    assert db.scalar(select(func.count()).select_from(SourceRecord))==1
    assert first.home_score==30


def test_conflicting_legacy_date_is_preserved_but_not_used_in_games(db):
    from app.unified_import import import_access_game
    from app.models import SourceRecord
    row={'ID_Game':100,'ID_country':'Croatia','sex':'men','League':'Premijer liga','Datum':'2024-01-15','season':2425,'home_team':'A','away_team':'B','Home_Goal':30,'Away_Goal':25}
    assert import_access_game(db,row) is None
    db.flush()
    assert db.get(SourceRecord,'access:RusHandbal:game:100').status=='date_season_conflict'
    assert db.query(Game).count()==0


def test_odds_import_fills_gaps_without_overwriting_manual_values(db):
    from app.unified_import import merge_line
    from app.models import GameLine
    g=game(db,1,0)
    db.add(GameLine(game_id=g.id,odds_home=2.0,over_line=59.5,source='manual'));db.flush()
    assert merge_line(db,g,{'home':3,'away':2.4,'over':60.5})
    db.flush()
    line=db.get(GameLine,g.id)
    assert line.odds_home==2
    assert line.over_line==59.5
    assert line.odds_away==2.4
