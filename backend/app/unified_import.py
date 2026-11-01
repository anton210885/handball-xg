"""Normalisierung und verlustfreier Import lokaler/API-Spiele."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import math, re, unicodedata
from sqlalchemy import select
from .models import Competition, Team, Game, GameLine, AggregateStat, SourceRecord


def stable_id(kind, source, value):
    # 48 bits remain exactly representable by JavaScript numbers; Russian IDs stay positive.
    return -int.from_bytes(sha256(f'{kind}|{source}|{value}'.encode()).digest()[:6], 'big') - 1


def number(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None


def count(value):
    v=number(value)
    return int(v) if v is not None and v>=0 and v.is_integer() else None


def clean_name(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or ''))).strip()


def record(session,key,payload,game_id=None,status='imported'):
    obj=session.get(SourceRecord,key)
    if obj is None:obj=SourceRecord(key=key)
    obj.payload=payload;obj.game_id=game_id;obj.status=status;session.add(obj)


def competition(session,country,league,gender,season,source,external=None):
    cid=stable_id('competition','canonical',f'{country}|{league}|{gender}|{season}')
    comp=session.get(Competition,cid)
    if comp is None:
        comp=Competition(id=cid,name=f'{country} · {league} '+('Frauen' if gender=='women' else 'Männer'),
                         country=country,league=league,season=season,gender=gender,source=source,external_id=str(external) if external else None)
        session.add(comp);session.flush()
    return comp


def team(session,country,gender,name,source,external=None):
    name=clean_name(name)
    identity=str(external) if external is not None else f'{country}|{gender}|{name.casefold()}'
    tid=stable_id('team',source,identity)
    obj=session.get(Team,tid)
    if obj is None:
        obj=Team(id=tid,name=name,name_en=name,source=source,external_id=identity)
        session.add(obj);session.flush()
    return obj


def merge_line(session,game,row):
    values={key:number(row.get(src)) for key,src in [('odds_home','home'),('odds_draw','draw'),('odds_away','away'),('over_line','over'),('hdp_line','hdp')]}
    values={k:v for k,v in values.items() if v is not None and (v>1 if k.startswith('odds_') else True)}
    if not values:return False
    line=game.line or session.get(GameLine,game.id) or GameLine(game_id=game.id,source='access')
    changed=False
    for key,value in values.items():
        if getattr(line,key) is None:setattr(line,key,value);changed=True
    if changed:
        if line.source and 'access' not in line.source:line.source+=' + access'
        line.updated_at=datetime.utcnow();session.add(line)
    return changed


def import_event(session,event,meta):
    ext=event['id'];gid=stable_id('game','handballapi',ext)
    def reject(status):
        key=f'api:event:{ext}'
        previous=session.get(SourceRecord,key)
        if previous is not None and previous.game_id is not None:
            # Ein neuer Fehlversuch darf die Quelle eines bereits gültigen Spiels nicht verdrängen.
            key=f"api:rejected:{status}:{meta['tournament_id']}:{ext}"
        record(session,key,event,status=status)
    tournament=event.get('tournament') or {}
    sport=(tournament.get('category') or {}).get('sport') or {}
    # Sofascore/HandballAPI: Handball hat Sport-ID 6. Ein URL-Präfix allein reicht nicht.
    if sport.get('id') not in (None,6) or sport.get('slug') not in (None,'handball'):
        reject('rejected_wrong_sport');return None
    actual_id=(tournament.get('uniqueTournament') or {}).get('id')
    if actual_id is not None and str(actual_id)!=str(meta['tournament_id']):
        reject('rejected_wrong_tournament');return None
    if meta.get('country')=='Germany' and meta.get('league')=='2. Bundesliga' and meta.get('gender')=='men' and meta.get('tournament_id')!=921:
        reject('rejected_wrong_tournament');return None
    ts=number(event.get('startTimestamp'))
    if ts is None or not event.get('homeTeam') or not event.get('awayTeam'):
        record(session,f'api:event:{ext}',event,status='missing_date_or_teams');return None
    comp=competition(session,meta['country'],meta['league'],meta['gender'],meta['season'],'handballapi',meta['tournament_id'])
    comp.handballapi_tournament_id=meta['tournament_id'];comp.handballapi_season_id=meta['season_id']
    home=team(session,meta['country'],meta['gender'],event['homeTeam']['name'],'handballapi',event['homeTeam']['id'])
    away=team(session,meta['country'],meta['gender'],event['awayTeam']['name'],'handballapi',event['awayTeam']['id'])
    g=session.get(Game,gid)
    if g is None:g=Game(id=gid,competition_id=comp.id,home_team_id=home.id,away_team_id=away.id,source='handballapi',external_id=str(ext),shots_imported=False,stats_imported=False)
    hs,aws=event.get('homeScore',{}),event.get('awayScore',{})
    g.start_moscow=datetime.fromtimestamp(ts,timezone.utc).replace(tzinfo=None)+timedelta(hours=3)
    g.home_score=count(hs.get('normaltime',hs.get('current')));g.away_score=count(aws.get('normaltime',aws.get('current')))
    g.home_ht=count(hs.get('period1'));g.away_ht=count(aws.get('period1'))
    g.finished=event.get('status',{}).get('type')=='finished' and g.home_score is not None and g.away_score is not None
    g.game_number=str(event.get('roundInfo',{}).get('round','')) or None
    g.handballapi_event_id=ext;g.date_quality='official_api'
    session.add(g);session.flush();record(session,f'api:event:{ext}',event,g.id)
    return g


def infer_wing_shots(stats,position):
    """Residual only for wing players; never silently clamp a contradiction to zero.

    shots6m can overlap breakthroughs/wing goals. It is deliberately not subtracted
    from this *estimated* subtype remainder; all original counters remain separate.
    """
    direct=count(stats.get('wingShots'))
    if direct is not None:return direct,[]
    if position not in ('LW','RW'):return None,['wing_not_inferable']
    total=count(stats.get('shotsTaken'))
    if total is None:return None,['missing_total_shots']
    fields=['shots7m','shots9m','fastbreakShots','pivotShots','breakthroughShots']
    known=[count(stats.get(k,0) or 0) for k in fields]
    if any(v is None for v in known):return None,['invalid_component']
    remainder=total-sum(known);goals=count(stats.get('wingGoals',0) or 0)
    if remainder<0 or goals is None or remainder<goals:return None,['wing_residual_conflict']
    return remainder,['wing_shots_estimated_residual']


def import_lineups(session,game,data,source="handballapi"):
    if not game.finished:return
    for side,ishome,expected in [('home',True,game.home_score),('away',False,game.away_score)]:
        players=data.get(side,{}).get('players',[])
        if not players:continue
        total_shots=total_goals=0;flags=[];prepared=[]
        for p in players:
            stats=dict(p.get('statistics') or {});pos=p.get('position') or p.get('player',{}).get('position')
            # Goalkeeper shooting is counted too, but saves/gkShots never enter field shots.
            shots=count(stats.get('shotsTaken'));goals=count(stats.get('goals'))
            if shots is not None:total_shots+=shots
            if goals is not None:total_goals+=goals
            wing,derived=infer_wing_shots(stats,pos)
            if wing is not None:stats['wingShots_normalized']=wing
            flags.extend(derived);prepared.append({'player':p.get('player'), 'position':pos,'statistics':stats,'flags':derived})
        if total_goals!=expected:flags.append('player_goals_disagree_with_result')
        valid=total_shots>=expected and total_goals==expected
        stat=session.get(AggregateStat,(game.id,ishome)) or AggregateStat(game_id=game.id,is_home=ishome)
        stat.shots=total_shots if valid else None;stat.goals=expected;stat.categories={'players':prepared}
        stat.source=source;stat.flags=sorted(set(flags + (['legacy_wing_method_unverified'] if source.startswith('access') else [])));session.add(stat)
    game.stats_imported=True;session.flush()


def import_access_game(session,row,players=None):
    rid=count(row.get('ID_Game'));key=f'access:RusHandbal:game:{rid}'
    # Von Hand gelöscht oder in ein anderes Spiel überführt: nicht wieder anlegen, nur fehlende Quoten ergänzen
    prev=session.get(SourceRecord,key)
    if prev is not None and prev.status=='game_deleted':return None
    if prev is not None and prev.status=='merged' and prev.game_id:
        g=session.get(Game,prev.game_id)
        if g is not None:merge_line(session,g,row)
        return g
    country=clean_name(row.get('ID_country'));gender=clean_name(row.get('sex')).lower();raw_league=clean_name(row.get('League'))
    league={'Croatia':'HRL' if gender=='women' else 'Premijer liga','Romania':'Liga nationala','Korea':'H League'}.get(country,raw_league)
    if gender not in ('men','women') or not row.get('Datum') or not row.get('home_team') or not row.get('away_team'):
        record(session,key,row,status='missing_identity_or_date');return None
    if 'Women' in raw_league and gender=='men':record(session,key,row,status='gender_conflict');return None
    date=datetime.fromisoformat(row['Datum'])
    season=count(row.get('season'));start=season//100 if season else None
    if start is None or not (datetime(2000+start,7,1)<=date<datetime(2001+start,7,1)):
        record(session,key,row,status='date_season_conflict');return None
    hg,ag=count(row.get('Home_Goal')),count(row.get('Away_Goal'))
    if hg is None or ag is None:record(session,key,row,status='missing_result');return None
    comp=competition(session,country,league,gender,f'{start:02d}/{(start+1)%100:02d}','access')
    h=team(session,country,gender,row['home_team'],'access');a=team(session,country,gender,row['away_team'],'access')
    gid=stable_id('game','access:RusHandbal',rid)
    g=session.get(Game,gid)
    if g is None:
        g=Game(id=gid,competition_id=comp.id,home_team_id=h.id,away_team_id=a.id,home_score=hg,away_score=ag,
               start_moscow=date,finished=True,shots_imported=False,stats_imported=False,source='access',external_id=str(rid),date_quality='date_only')
        session.add(g);session.flush()
    merge_line(session,g,row)
    for ishome,prefix,goals in [(True,'Home',hg),(False,'Away',ag)]:
        vals={k:count(row.get(prefix+'_'+k)) for k in ['Linie','Eck','Kurz','Weit','7m']}
        shots=sum(v for v in vals.values() if v is not None) if any(v is not None for v in vals.values()) else None
        flags=['shot_total_derived_from_spatial_counts','attack_types_kept_separate']
        if shots is not None and shots<goals:shots=None;flags.append('shots_below_goals')
        stat=session.get(AggregateStat,(g.id,ishome)) or AggregateStat(game_id=g.id,is_home=ishome)
        stat.shots=shots;stat.goals=goals;stat.categories={'reported_position_shots':vals,
            'fastbreak_reported':number(row.get(prefix+'_FB')),'longdistance_reported':number(row.get(prefix+'_LD')),
            'legacy_xg_not_used_in_pregame':number(row.get(prefix+'_XG'))}
        stat.flags=flags;stat.source='access';session.add(stat)
    g.stats_imported=True
    payload={**row,'players':players or []};record(session,key,payload,g.id)
    return g


def link_priors(session):
    groups=defaultdict(list)
    for c in session.scalars(select(Competition)):
        if c.country and c.league:groups[c.country,c.league,c.gender].append(c)
    for comps in groups.values():
        ordered=sorted(comps,key=lambda c:c.season)
        for prev,current in zip(ordered,ordered[1:]):
            if int(current.season[:2])-int(prev.season[:2])==1:current.previous_competition_id=prev.id
