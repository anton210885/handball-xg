"""Read-only Access import of available Russian women's Superleague odds/lines.

Match home/away team, date window and known score; fill missing fields only.
"""
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pyodbc
from sqlalchemy import select
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import SessionLocal
from app.models import Competition, Game, GameLine

DEFAULT_DB = r'C:\Users\anton\OneDrive\Desktop\hANDBALL\RusHandbal.accdb'
TEAM_IDS = {'Adyif W':110,'Chernomorochka W':2522,'Krasnodar W':112,
            'Dinamo-Sinara W':111,'Luch W':102,'Astrahanochka W':116,
            'Zvenigorod W':117,'Rostov-Don W':115,'CSKA Moscow W':1417,'Izhevsk W':114}

def number(value):
    if value is None: return None
    value=float(value)
    return value if math.isfinite(value) else None

def main(path=DEFAULT_DB):
    conn=pyodbc.connect(rf'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};',readonly=True)
    try:
        rows=conn.cursor().execute("SELECT ID_Game,Datum,home_team,away_team,home,Draw,away,over,hdp,Home_Goal,Away_Goal FROM Games WHERE sex='women' AND ID_country='Russia' AND League='Superleague' ORDER BY Datum,ID_Game").fetchall()
    finally: conn.close()
    counts={'read':len(rows),'matched':0,'updated':0,'unmatched':0,'ambiguous':0,'missing_score':0}
    with SessionLocal() as s:
        for acc,date,home,away,o1,ox,o2,line,hdp,hg,ag in rows:
            hid,aid=TEAM_IDS.get(home),TEAM_IDS.get(away)
            if hid is None or aid is None:
                counts['unmatched']+=1
                print('UNKNOWN TEAM',acc,home,away)
                continue
            day=datetime(date.year,date.month,date.day)
            candidates=s.scalars(select(Game).join(Competition).where(
                Competition.gender=='women',Game.home_team_id==hid,Game.away_team_id==aid,
                Game.start_moscow>=day-timedelta(days=1),Game.start_moscow<day+timedelta(days=5))).unique().all()
            if number(hg) is None or number(ag) is None:
                counts['missing_score']+=1
                print('MISSING SCORE',acc,home,away)
                continue
            candidates=[g for g in candidates if g.finished and (g.home_score,g.away_score)==(int(hg),int(ag))]
            if len(candidates)!=1:
                counts['ambiguous' if len(candidates)>1 else 'unmatched']+=1
                print('NO UNIQUE MATCH',acc,home,away)
                continue
            g=candidates[0];counts['matched']+=1
            dest=g.line or GameLine(game_id=g.id,odds_over=1.8,odds_under=1.8)
            changed=[]
            for key,value in zip(['odds_home','odds_draw','odds_away','over_line','hdp_line'],[o1,ox,o2,line,hdp]):
                value=number(value)
                if value is not None and getattr(dest,key) is None:
                    setattr(dest,key,value);changed.append(key)
            if changed:
                dest.source='access' if not dest.source else dest.source if 'access' in dest.source else dest.source+'+access'
                dest.updated_at=datetime.utcnow();s.add(dest);counts['updated']+=1
            print('MATCH',int(acc),'game',g.id,home,away,'fields',','.join(changed))
        s.commit()
    print('RESULT',counts)
    return counts

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(*sys.argv[1:2])
