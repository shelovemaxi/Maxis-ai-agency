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
SOURCES=[
 ('Federal Reserve','Macro','https://www.federalreserve.gov/feeds/press_all.xml'),('ECB','Macro','https://www.ecb.europa.eu/rss/press.html'),('BLS','Macro','https://www.bls.gov/feed/bls_latest.rss'),('BEA','Macro','https://apps.bea.gov/rss/rss.xml'),('SEC','Equities','https://www.sec.gov/news/pressreleases.rss'),
 ('CNBC','Equities','https://www.cnbc.com/id/100003114/device/rss/rss.html'),('Yahoo Finance','Equities','https://finance.yahoo.com/news/rssindex'),('CoinDesk','Crypto','https://www.coindesk.com/arc/outboundfeeds/rss/'),('Cointelegraph','Crypto','https://cointelegraph.com/rss'),('OilPrice','Commodities','https://oilprice.com/rss/main'),('USGS Earthquakes','Natural events','https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.atom'),
 # Official regional central-bank and regulator feeds.
 ('Bank of Japan','Macro','https://www.boj.or.jp/en/rss/whatsnew.xml'),('Bank of Canada','Macro','https://www.bankofcanada.ca/feed/'),('Reserve Bank of Australia','Macro','https://www.rba.gov.au/rss/rss-cb-speeches.xml'),('Bank of England','Macro','https://www.bankofengland.co.uk/rss/news'),('CFTC','Commodities','https://www.cftc.gov/RSS/RSSGP/rssgp.xml'),
]
# These publisher-labelled feeds use Google News' public RSS index where the publisher does not
# provide a stable open RSS endpoint. Links remain clickable; verification still requires an
# independent domain or primary source, and a publisher headline is never treated as proof alone.
PUBLISHER_QUERIES=[
 ('Reuters','Business','site:reuters.com business economy markets'),('Bloomberg','Business','site:bloomberg.com markets economy'),('Financial Times','Business','site:ft.com markets economy'),('Wall Street Journal','Business','site:wsj.com markets economy'),('MarketWatch','Equities','site:marketwatch.com stocks economy'),('Investing.com','Equities','site:investing.com news markets'),('AP Business','Business','site:apnews.com business economy'),('BBC Business','Business','site:bbc.com/news/business'),('Trading Economics','Macro','site:tradingeconomics.com news economy markets'),
]
GDELT=[('Google News geopolitics','Geopolitics','geopolitics OR conflict OR war'),('Google News trade','Geopolitics','tariff OR sanctions OR trade restriction'),('Google News supply','Commodities','oil OR gas OR OPEC OR supply disruption')]
JSON_SOURCES=[('IMF DataMapper','Macro','https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH')]

WORLD_MONITOR_API='https://api.worldmonitor.app/api'
def worldmonitor_items():
 """Fetch optional World Monitor signals without making refresh fragile.

 World Monitor's hosted API requires a key and documents X-WorldMonitor-Key.
 A bad key, rate limit, outage, or response-shape change is recorded as source
 health and never aborts the other collectors.
 """
 out=[]; health={}; errors=[]
 key=os.getenv('WORLDMONITOR_API_KEY','').strip()
 base=os.getenv('WORLDMONITOR_API_BASE', WORLD_MONITOR_API).rstrip('/')
 if not key:
  return out,{'World Monitor':{'ok':False,'count':0,'url':'https://www.worldmonitor.app/docs/api-reference','error':'API key not configured; skipped safely'}},[]
 def wm_json(path):
  last=None
  for attempt in range(3):
   try:
    req=Request(base+path,headers={'User-Agent':'SignalWire/2.1','Accept':'application/json','X-WorldMonitor-Key':key})
    with urlopen(req,timeout=TIMEOUT) as r:
     if getattr(r,'status',200) != 200: raise RuntimeError('HTTP '+str(r.status))
     value=json.loads(r.read().decode('utf8'))
     if not isinstance(value,dict): raise ValueError('response was not an object')
     return value
   except Exception as exc:
    last=exc
    if attempt < 2: time.sleep(0.6*(attempt+1))
  raise last or RuntimeError('request failed')
 def record_failure(label,path,exc):
  message=str(exc)[:160]
  health[label]={'ok':False,'count':0,'url':base+path,'error':message}
  errors.append(label+': '+message[:120])
 try:
  path='/economic/v1/get-macro-signals'; raw=wm_json(path)
  signals=raw.get('signals') if isinstance(raw.get('signals'),dict) else raw
  regime=signals.get('macroRegime') if isinstance(signals.get('macroRegime'),dict) else {}
  status=str(regime.get('status') or 'updated').replace('_',' ')
  title='World Monitor macro regime: '+status
  summary='World Monitor reports macro regime '+status+'. QQQ 20-day ROC: '+str(regime.get('qqqRoc20','n/a'))+'; XLP 20-day ROC: '+str(regime.get('xlpRoc20','n/a'))+'.'
  out.append(item(title,summary,base+path,raw.get('timestamp',now()),'World Monitor','Macro'))
  health['World Monitor macro']={'ok':True,'count':1,'url':base+path}
 except Exception as exc: record_failure('World Monitor macro','/economic/v1/get-macro-signals',exc)
 try:
  path='/economic/v1/get-energy-prices'; raw=wm_json(path)
  prices=raw.get('prices',[])
  if not isinstance(prices,list): prices=[]
  accepted=0
  for price in prices:
   if not isinstance(price,dict): continue
   try: change=float(price.get('change',0) or 0)
   except (TypeError,ValueError): continue
   if abs(change) >= 1:
    commodity=str(price.get('commodity') or price.get('name') or 'energy')
    title='World Monitor energy price move: '+commodity
    summary='World Monitor reports '+commodity+' at '+str(price.get('price','n/a'))+' '+str(price.get('unit',''))+' with change '+f'{change:+g}'+'.'
    out.append(item(title,summary,base+path,raw.get('timestamp',now()),'World Monitor','Commodities')); accepted += 1
  health['World Monitor energy']={'ok':True,'count':accepted,'url':base+path}
 except Exception as exc: record_failure('World Monitor energy','/economic/v1/get-energy-prices',exc)
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
PRIMARY_SOURCES={'Federal Reserve','ECB','BLS','BEA','SEC','IMF DataMapper','Bank of Japan','Bank of Canada','Reserve Bank of Australia','Bank of England','CFTC','USGS Earthquakes'}
def freshness_label(published):
 try: age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(date(published))).total_seconds())
 except Exception: age=10**9
 if age < 6*3600:return 'developing'
 if age < 48*3600:return 'recent'
 return 'older'
def relationships(title,category):
 text=(title+' '+category).lower(); out=[]
 if any(k in text for k in ('central bank','interest rate','rate decision','monetary policy','inflation','cpi')): out += ['rates → government bonds','rates → currency markets','rates → bank and growth-sensitive equities']
 if any(k in text for k in ('oil','gas','opec','energy','supply disruption')): out += ['energy supply → inflation expectations','energy prices → transport and industrial margins']
 if any(k in text for k in ('tariff','sanction','trade','export ban')): out += ['trade policy → currencies and exporters','trade friction → supply chains and inflation']
 if any(k in text for k in ('jobs','payroll','employment','recession','gdp')): out += ['growth data → rates and bond yields','growth data → cyclical equities and currency']
 return out[:4]
def item(title,summary,url,published,source,category,source_url=None,timestamp_kind='published'):
 a=analyse(title,summary,category); published_at=date(published); src_url=source_url or url; src_domain=domain(src_url)
 return {'id':hashlib.sha1((title+url).encode()).hexdigest()[:16],'title':title,'summary':a['summary'],'excerpt':clean(summary)[:600],'url':url,'source':source,'domain':domain(url),'source_url':src_url,'source_domain':src_domain,'category':category,'published':published_at,'timestamp_kind':timestamp_kind,'freshness':freshness_label(published_at),'developing':freshness_label(published_at)=='developing','source_tier':'primary' if source in PRIMARY_SOURCES else 'reported','fact_status':'confirmed data' if source in PRIMARY_SOURCES else 'reported; not independently confirmed','score':a['score'],'reasons':a['reasons'],'market_relevance':a['market_relevance'],'analysis_provider':a['analysis_provider'],'affected_assets':a.get('affected_assets',[]),'relationships':relationships(title,category),'confidence':a.get('confidence','medium'),'sources':[{'name':source,'domain':src_domain,'url':url,'source_url':src_url,'title':title,'published':published_at}],'verification':'single-source','corroboration':1}
def parse(raw,source,category,fallback):
 root=ET.fromstring(raw); out=[]
 for n in [e for e in root.iter() if e.tag.split('}')[-1].lower() in ('item','entry')][:60]:
  title=clean(child(n,{'title'})); link=child(n,{'link'})
  for c in list(n):
   if c.tag.split('}')[-1].lower()=='link' and c.attrib.get('href'):link=c.attrib['href'];break
  source_url=''
  for c in list(n):
   if c.tag.split('}')[-1].lower()=='source': source_url=c.attrib.get('url','') or clean(''.join(c.itertext()))
  if title:out.append(item(title,clean(child(n,{'description','summary','content','encoded'})),link or fallback,child(n,{'pubdate','published','updated','date'}),source,category,source_url or None))
 return out
def fetch(url):
 req=Request(url,headers={'User-Agent':'SignalWire/2.0 research dashboard','Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml'});
 with urlopen(req,timeout=TIMEOUT) as r:return r.read()
def merge(items):
 # Build connected components so duplicate matching is not dependent on feed order.
 groups=[]
 for x in items:
  matches=[i for i,g in enumerate(groups) if any(similar(g["title"],x["title"]) for g in [g])]
  if not matches: groups.append(x); continue
  base=groups[matches[0]]
  existing={s.get("domain") for s in base.get("sources",[])}
  incoming=x.get("sources",[])[0] if x.get("sources") else {}
  if incoming.get("domain") not in existing: base.setdefault("sources",[]).append(incoming)
  # Prefer primary-source facts and the freshest, more complete headline.
  if x.get("source_tier")=="primary" and base.get("source_tier")!="primary":
   for key in ("title","summary","excerpt","url","source","domain","source_url","source_domain","published","timestamp_kind","source_tier","fact_status"): base[key]=x.get(key,base.get(key))
  base["corroboration"]=len({z.get("domain") for z in base.get("sources",[])})
  base["verification"]="verified" if base["corroboration"]>=2 else "single-source"
  if base["corroboration"]>=2: base["fact_status"]="corroborated report" if base.get("source_tier")!="primary" else "confirmed data with independent reporting"
  base["score"]=min(100,max(base.get("score",0),x.get("score",0))+ (8 if base["corroboration"]>=2 else 0))
  base["reasons"]=list(dict.fromkeys(base.get("reasons",[])+x.get("reasons",[])+(["independently corroborated"] if base["corroboration"]>=2 else [])))[:8]
  base["confidence"]="high" if base["corroboration"]>=2 and base.get("source_tier")=="primary" else "medium" if base["corroboration"]>=2 else base.get("confidence","low")
 out=[]
 for x in groups:
  x["level"]="High" if x["score"]>=65 else "Medium" if x["score"]>=35 else "Low"
  # Never surface low relevance noise, and put primary evidence first.
  if x["score"]>=35: out.append(x)
 return sorted(out,key=lambda x:(x.get("source_tier")=="primary",x.get("score",0),x.get("published","")),reverse=True)[:250]

def fetch_json(url):
 req=Request(url,headers={'User-Agent':'SignalWire/2.2 research dashboard','Accept':'application/json'})
 with urlopen(req,timeout=TIMEOUT) as r:return json.loads(r.read().decode('utf8'))
def json_items(raw,source,category,url):
 # IMF DataMapper is primary numeric data: create one transparent snapshot item,
 # never infer a story from a value without corroborating reporting.
 if not isinstance(raw,dict) or not raw.get('values'): return []
 values=raw.get('values',{}); latest=[]
 for country, series in values.items():
  if isinstance(series,dict) and series:
   year=max(series, key=lambda x: str(x)); latest.append((country,series[year],year))
 latest=latest[:12]
 if not latest:return []
 summary='IMF DataMapper real GDP growth observations: '+', '.join(f'{c} {v}% ({y})' for c,v,y in latest if isinstance(v,(int,float)))
 return [item('IMF DataMapper: real GDP growth snapshot',summary,url,now(),source,category,url,'retrieved_at')]
def fetch_all():
 publisher_sources=[(n,c,'https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=en-US&gl=US&ceid=US:en') for n,c,q in PUBLISHER_QUERIES]
 sources=SOURCES+publisher_sources+[(n,c,'https://news.google.com/rss/search?q='+quote_plus(q)+'&hl=en-US&gl=US&ceid=US:en') for n,c,q in GDELT]; items=[];health={};errors=[]
 for n,c,u in sources:
  try:
   got=parse(fetch(u),n,c,u);items+=got;health[n]={'ok':True,'count':len(got),'url':u}
  except Exception as e:
   health[n]={'ok':False,'count':0,'url':u,'error':str(e)[:160]};errors.append(n+': '+str(e)[:120])
 for n,c,u in JSON_SOURCES:
  try:
   got=json_items(fetch_json(u),n,c,u);items+=got;health[n]={'ok':True,'count':len(got),'url':u}
  except Exception as e:
   health[n]={'ok':False,'count':0,'url':u,'error':str(e)[:160]};errors.append(n+': '+str(e)[:120])
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
