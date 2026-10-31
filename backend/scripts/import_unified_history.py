"""Importiert vorhandene Access-Bestände und gecachte HandballAPI-Antworten.
Kein API-Aufruf; wiederholbar, Quelle bleibt unverändert. Vor jeder Ausführung Backup.
"""
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal
from collections import defaultdict,Counter
import json,sqlite3,sys,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pyodbc
from sqlalchemy import select,func
from app.config import DB_PATH
from app.db import SessionLocal,init_db
from app.models import Competition,Game,Team,SourceRecord,AggregateStat
from app.unified_import import import_event,import_access_game,merge_line,record,stable_id,number,count,import_lineups,link_priors,clean_name

ROOT=Path(r'C:\Users\anton\OneDrive\Desktop\hANDBALL')
CACHE=Path(__file__).resolve().parents[1]/'data'/'handballapi'
WOMEN={'Adyif W':110,'Chernomorochka W':2522,'Krasnodar W':112,'Dinamo-Sinara W':111,'Luch W':102,'Astrahanochka W':116,'Zvenigorod W':117,'Rostov-Don W':115,'CSKA Moscow W':1417,'Izhevsk W':114,'Alisa W':103,'Togliatti W':108}
MEN={'Viktor':129,'CSKA':1809,'Chehovskie Medvedi':105,'Zenit':122,'Perm':150,'SKIF':106,'Astrahan':119,'Dinamo-Sungul':121,'Akbuzat':148,'SGAU-Saratov':178,'Kaustik':107,'Moscow2':2526,'Omsk':123}


def safe(v):
    if isinstance(v,datetime):return v.isoformat()
    if isinstance(v,Decimal):return float(v)
    if isinstance(v,float) and not math.isfinite(v):return None
    if isinstance(v,bytes):return v.hex()
    return v


def rows(path,table):
    c=pyodbc.connect(rf'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};',readonly=True)
    try:
        columns=list(c.cursor().columns(table=table))
        # Old calculated Currency/Decimal bet columns can overflow the Access ODBC driver.
        # They are not source inputs; preserve the raw sports/odds fields and recalculate bets.
        selected=[col.column_name for col in columns if col.data_type not in (2,3) and not col.column_name.lower().endswith("_bet")]
        cur=c.cursor().execute('SELECT '+','.join('['+k+']' for k in selected)+' FROM ['+table+']');keys=[x[0] for x in cur.description]
        return [{k:safe(v) for k,v in zip(keys,row)} for row in cur.fetchall()]
    finally:c.close()


def main():
    backup=DB_PATH.with_name('handball.before-unified-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
    with sqlite3.connect(DB_PATH) as src,sqlite3.connect(backup) as dst:src.backup(dst)
    print('BACKUP',backup.name,flush=True)
    init_db();result=Counter();issues=[]
    local=rows(ROOT/'RusHandbal.accdb','Games')
    grouped_players=defaultdict(list)
    for p in rows(ROOT/'RusHandbal.accdb','SpielerStatistik_pro_Spiel'):grouped_players[count(p.get('ID_Game'))].append(p)
    api_local=rows(ROOT/'Handball.accdb','Kopie von tbl_base')
    odds=rows(ROOT/'Handball.accdb','tbl_Odds')
    api_players=defaultdict(list)
    for p in rows(ROOT/'Handball.accdb','tbl_PlayerStatistik_per_Game'):api_players[count(p['event_id'])].append(p)
    with SessionLocal() as s:
        initial=s.scalar(select(func.count()).select_from(Game))
        for c in s.scalars(select(Competition)).all():
            if c.id in [6597,7284,8070,6604,7286,8078]:c.country='Russia';c.league='Superliga'
        manifest=json.loads((CACHE/'manifest.json').read_text(encoding='utf-8'))
        for m in manifest:
            if m.get('disabled'):
                result['disabled_cache_entries']+=1;continue
            data=json.loads((CACHE/m['file']).read_text(encoding='utf-8'));events={}
            for teams in data.get('tournamentTeamEvents',{}).values():
                for evs in teams.values():
                    for e in evs:events[e['id']]=e
            for e in events.values():
                if import_event(s,e,m):result['api_events_processed']+=1
            s.commit();print('API_IMPORTED',m['league'],m['gender'],m['season'],len(events),flush=True)
        old_meta=next(m for m in manifest if m['tournament_id']==149 and m['season']=='24/25')
        for p in CACHE.glob('match_*.json'):
            data=json.loads(p.read_text(encoding='utf-8'));e=data.get('event',data)
            if e.get('id'):import_event(s,e,old_meta)
        s.commit()
        for row in api_local:
            gid=stable_id('game','handballapi',count(row['event_id']));g=s.get(Game,gid)
            record(s,f"access:Handball:base:{count(row['event_id'])}",row,g.id if g else None,'imported' if g else 'missing_official_match_date')
            if g:
                merge_line(s,g,row);result['api_analysis_rows_matched']+=1
        for row in odds:
            g=s.get(Game,stable_id('game','handballapi',count(row['event_id'])))
            record(s,f"access:Handball:odds:{count(row['event_id'])}",row,g.id if g else None,'imported' if g else 'unmatched_event_id')
            if g and merge_line(s,g,row):result['api_odds_updated']+=1
        # Preserve original API player rows and use only independently reported total shots.
        for eid,players in api_players.items():
            g=s.get(Game,stable_id('game','handballapi',eid))
            record(s,f'access:Handball:players:{eid}',{'players':players},g.id if g else None,'imported' if g else 'missing_official_match_date')
            if not g:continue
            data={'home':{'players':[]},'away':{'players':[]}}
            for p in players:
                side='home' if clean_name(p.get('Team'))==clean_name(g.home_team.name) else 'away' if clean_name(p.get('Team'))==clean_name(g.away_team.name) else None
                if side is None:continue
                stats={k:v for k,v in p.items() if k not in ['event_id','Team','Spielername','Id_Spieler','round_number','Position','tournament','XG_new'] and v is not None}
                data[side]['players'].append({'position':p.get('Position'),'player':{'id':p.get('Id_Spieler'),'name':p.get('Spielername')},'statistics':stats})
            import_lineups(s,g,data,source='access:Handball');result['api_local_player_games']+=1
        for p in CACHE.glob('lineups_*.json'):
            eid=int(p.stem.split('_')[1]);g=s.get(Game,stable_id('game','handballapi',eid))
            if g:import_lineups(s,g,json.loads(p.read_text(encoding='utf-8')));result['api_live_player_games']+=1
        s.commit()
        russian_games=s.scalars(select(Game).join(Competition).where(Competition.country=='Russia')).unique().all()
        comp_gender={c.id:c.gender for c in s.scalars(select(Competition))}
        for i,row in enumerate(local):
            if row['ID_country']=='Russia':
                names=WOMEN if row['sex']=='women' else MEN
                h,a=names.get(clean_name(row['home_team'])),names.get(clean_name(row['away_team']))
                day=datetime.fromisoformat(row['Datum']) if row['Datum'] else None
                cand=[g for g in russian_games if h==g.home_team_id and a==g.away_team_id and comp_gender[g.competition_id]==row['sex'] and g.finished
                    and (g.home_score,g.away_score)==(count(row['Home_Goal']),count(row['Away_Goal']))]
                close=[g for g in cand if day and day-timedelta(days=1)<=g.start_moscow<day+timedelta(days=5)]
                if len(close)==1:
                    g=close[0]
                    changed=merge_line(s,g,row)
                    result['russian_'+row['sex']+'_matched']+=1
                    if changed:result['russian_'+row['sex']+'_lines_updated']+=1
                    record(s,f"access:RusHandbal:game:{count(row['ID_Game'])}",row,g.id)
                else:
                    status='date_conflict' if len(cand)==1 else 'no_unique_team_score_match'
                    record(s,f"access:RusHandbal:game:{count(row['ID_Game'])}",row,status=status)
                    result['russian_unmatched']+=1
                continue
            g=import_access_game(s,row,grouped_players[count(row['ID_Game'])])
            if g:result['access_non_russian_games']+=1
            else:result['access_quarantined']+=1
            if i%200==0:s.commit();print('LOCAL_PROGRESS',i,len(local),flush=True)
        link_priors(s);s.commit()
        result['new_games']=s.scalar(select(func.count()).select_from(Game))-initial
        result['total_games']=s.scalar(select(func.count()).select_from(Game))
        result['aggregate_team_rows']=s.scalar(select(func.count()).select_from(AggregateStat))
        result['source_records']=s.scalar(select(func.count()).select_from(SourceRecord))
        result['source_records_pending']=s.scalar(select(func.count()).select_from(SourceRecord).where(SourceRecord.game_id.is_(None)))
        report=[]
        for c in s.scalars(select(Competition)).all():
            games=s.scalars(select(Game).where(Game.competition_id==c.id)).unique().all()
            report.append({'country':c.country,'league':c.league,'gender':c.gender,'season':c.season,'games':len(games),'finished':sum(g.finished for g in games),'aggregate':sum(bool(g.stats_imported) for g in games),'event_stats':sum(g.shots_imported for g in games),'with_line':sum(g.line is not None and g.line.over_line is not None for g in games)})
        statuses=s.execute(select(SourceRecord.status,func.count()).group_by(SourceRecord.status)).all()
        output={'summary':dict(result),'leagues':report,'source_record_statuses':dict(statuses),'backup':backup.name}
        (CACHE/'import_report.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        print('RESULT',dict(result),flush=True)
        print('STATUS',dict(statuses),flush=True)
    return output

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
