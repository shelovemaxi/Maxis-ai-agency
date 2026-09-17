#!/usr/bin/env python3
"""Signal Wire collector, verification pipeline, JSON API, and local UI host."""
from __future__ import annotations
import json,os,re,time,html,hashlib,threading
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET
from analysis import analyse, similar
try:
 from flask import Flask,jsonify,render_template
 HAS_FLASK=True
except ImportError: HAS_FLASK=False
BASE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(BASE,'data'); CACHE=os.path.join(DATA,'cache.json'); PORT=int(os.getenv('PORT','5050')); TIMEOUT=14; REFRESH_SECONDS=900
SOURCES=[('Federal Reserve','Macro','https://www.federalreserve.gov/feeds/press_all.xml'),('ECB','Macro','https://www.ecb.europa.eu/rss/press.html'),('BLS','Macro','https://www.bls.gov/feed/bls_latest.rss'),('SEC','Equities','https://www.sec.gov/news/pressreleases.rss'),('CNBC','Equities','https://www.cnbc.com/id/100003114/device/rss/rss.html'),('Yahoo Finance','Equities','https://finance.yahoo.com/news/rssindex'),('CoinDesk','Crypto','https://www.coindesk.com/arc/outboundfeeds/rss/'),('Cointelegraph','Crypto','https://cointelegraph.com/rss'),('OilPrice','Commodities','https://oilprice.com/rss/main'),('USGS Earthquakes','Natural events','https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.atom')]
GDELT=[('GDELT geopolitics','Geopolitics','geopolitics OR conflict OR war'),('GDELT trade','Geopolitics','tariff OR sanctions OR trade restriction'),('GDELT supply','Commodities','oil OR gas OR OPEC OR supply disruption')]
WORLD_MONITOR_API='https://api.worldmonitor.app/api'
def worldmonitor_items():
 out=[]; health={}; errors=[]; key=os.getenv('WORLDMONITOR_API_KEY','').strip()
 if not key:
  return out,{'World Monitor':{'ok':False,'count':0,'url':'https://www.worldmonitor.app','error':'Public API currently requires an API key'}},[]
 def wm_json(path):
  req=Request(WORLD_MONITOR_API+path,headers={'User-Agent':'SignalWire/2.0','X-API-Key':key,'Authorization':'Bearer '+key})
  with urlopen(req,timeout=TIMEOUT) as r:return json.loads(r.read().decode('utf8'))
 try:
  raw=wm_json('/economic/v1/get-macro-signals'); signals=raw.get('signals',{}); regime=signals.get('macroRegime',{}); flow=signals.get('flowStructure',{}); title='World Monitor macro regime: '+str(regime.get('status','updated')).replace('_',' '); summary='World Monitor reports macro regime '+str(regime.get('status','updated'))+'. QQQ 20-day ROC: '+str(regime.get('qqqRoc20','n/a'))+'; XLP 20-day ROC: '+str(regime.get('xlpRoc20','n/a'))+'.'; out.append(item(title,summary,WORLD_MONITOR_API+'/economic/v1/get-macro-signals',raw.get('timestamp',now()),'World Monitor','Macro'));health['World Monitor macro']={'ok':True,'count':1,'url':WORLD_MONITOR_API+'/economic/v1/get-macro-signals'}
 except Exception as e: health['World Monitor macro']={'ok':False,'count':0,'url':WORLD_MONITOR_API+'/economic/v1/get-macro-signals','error':str(e)[:160]};errors.append('World Monitor macro: '+str(e)[:120])
 try:
  raw=wm_json('/economic/v1/get-energy-prices')
  prices=raw.get('prices',[])
  for p in prices:
   change=float(p.get('change',0) or 0)
   if abs(change)>=1:
    title='World Monitor energy price move: '+str(p.get('name') or p.get('commodity','energy'))
    summary=f"World Monitor reports {p.get('commodity','energy')} at {p.get('price','n/a')} {p.get('unit','')} with change {change:+g}."
    out.append(item(title,summary,WORLD_MONITOR_API+'/economic/v1/get-energy-prices',now(),'World Monitor','Commodities'))
  health['World Monitor energy']={'ok':True,'count':len(prices),'url':WORLD_MONITOR_API+'/economic/v1/get-energy-prices'}
 except Exception as e: health['World Monitor energy']={'ok':False,'count':0,'url':WORLD_MONITOR_API+'/economic/v1/get-energy-prices','error':str(e)[:160]};errors.append('World Monitor energy: '+str(e)[:120])
 return out,health,errors
state={'items':[],'last_refresh':None,'source_health':{},'errors':[],'refreshing':False}; lock=threading.Lock()
def now():return datetime.now(timezone.utc).isoformat()
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def domain(url):
 m=re.search(r'https?://([^/]+)',url or '');return re.sub(r'^www\.','',m.group(1).lower()) if m else 'unknown'
def date(s):
 try:d=parsedate_to_datetime(s)
 except Exception:
  try:d=datetime.fromisoformat((s or '').replace('Z','+00:00'))
  except Exception:return now()
 return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)).isoformat()
def child(el,names):
 for c in list(el):
  if c.tag.split('}')[-1].lower() in names:return ''.join(c.itertext()).strip()
 return ''
def item(title,summary,url,published,source,category):
 a=analyse(title,summary,category)
 return {'id':hashlib.sha1((title+url).encode()).hexdigest()[:16],'title':title,'summary':a['summary'],'url':url,'source':source,'domain':domain(url),'category':category,'published':date(published),'score':a['score'],'reasons':a['reasons'],'market_relevance':a['market_relevance'],'analysis_provider':a['analysis_provider'],'affected_assets':a.get('affected_assets',[]),'confidence':a.get('confidence','medium'),'sources':[{'name':source,'domain':domain(url),'url':url,'title':title}],'verification':'single-source','corroboration':1}
def parse(raw,source,category,fallback):
 root=ET.fromstring(raw); out=[]
 for n in [e for e in root.iter() if e.tag.split('}')[-1].lower() in ('item','entry')][:60]:
  title=clean(child(n,{'title'})); link=child(n,{'link'})
  for c in list(n):
   if c.tag.split('}')[-1].lower()=='link' and c.attrib.get('href'):link=c.attrib['href'];break
  if title:out.append(item(title,clean(child(n,{'description','summary','content','encoded'})),link or fallback,child(n,{'pubdate','published','updated','date'}),source,category))
 return out
def fetch(url):
 req=Request(url,headers={'User-Agent':'SignalWire/2.0 research dashboard','Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml'});
 with urlopen(req,timeout=TIMEOUT) as r:return r.read()
def merge(items):
 groups=[]
 for x in items:
  group=next((g for g in groups if similar(g['title'],x['title'])),None)
  if not group:groups.append(x);continue
  if x['domain'] not in {s['domain'] for s in group['sources']}:
   group['sources'].append(x['sources'][0]);group['corroboration']=len(group['sources'])
   group['verification']='verified' if group['corroboration']>=2 else 'single-source'; group['score']=min(100,group['score']+8)
   group['reasons']=list(dict.fromkeys(group['reasons']+['independently corroborated']))[:8]
 # Only publish material events; source-verified does not mean true, only independently reported.
 out=[]
 for x in groups:
  x['level']='High' if x['score']>=65 else 'Medium' if x['score']>=35 else 'Low'
  if x['score']>=35:out.append(x)
 return sorted(out,key=lambda x:(x['score'],x['published']),reverse=True)[:250]
def fetch_all():
 sources=SOURCES+[(n,c,'https://api.gdeltproject.org/api/v2/doc/doc?query='+quote_plus(q)+'&mode=artlist&maxrecords=30&format=rss&sort=datedesc') for n,c,q in GDELT]; items=[];health={};errors=[]
 for n,c,u in sources:
  try: got=parse(fetch(u),n,c,u);items+=got;health[n]={'ok':True,'count':len(got),'url':u}
  except Exception as e:health[n]={'ok':False,'count':0,'url':u,'error':str(e)[:160]};errors.append(n+': '+str(e)[:120])
 wm_items,wm_health,wm_errors=worldmonitor_items();items+=wm_items;health.update(wm_health);errors.extend(wm_errors)
 return merge(items),health,errors
def save(payload):
 os.makedirs(DATA,exist_ok=True);tmp=CACHE+'.tmp'
 with open(tmp,'w',encoding='utf8') as f:json.dump(payload,f,ensure_ascii=False)
 os.replace(tmp,CACHE)
def refresh(force=False):
 with lock:
  if state['refreshing']:return False
  state['refreshing']=True
 try:
  items,health,errors=fetch_all();payload={'items':items,'last_refresh':now(),'source_health':health,'errors':errors};save(payload)
  with lock:state.update(payload)
 finally:
  with lock:state['refreshing']=False
 return True
def init():
 try:
  with open(CACHE,encoding='utf8') as f:state.update(json.load(f))
 except Exception:pass
 if not state['items']:threading.Thread(target=refresh,daemon=True).start()
if HAS_FLASK:
 app=Flask(__name__)
 @app.get('/')
 def index():return render_template('index.html')
 @app.get('/api/items')
 def api():return jsonify(state)
 @app.post('/api/refresh')
 def api_refresh():threading.Thread(target=refresh,args=(True,),daemon=True).start();return jsonify({'accepted':True})
 @app.get('/health')
 def health():return jsonify({'ok':True,'items':len(state['items']),'last_refresh':state['last_refresh']})
if __name__=='__main__':init();app.run(host='0.0.0.0',port=PORT,debug=False)
