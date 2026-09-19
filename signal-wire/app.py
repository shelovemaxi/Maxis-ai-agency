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
from source_registry import REGISTRY, source_meta
try:
 from flask import Flask,jsonify,render_template
 HAS_FLASK=True
except ImportError: HAS_FLASK=False
BASE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(BASE,'data'); CACHE=os.path.join(DATA,'cache.json'); KNOWLEDGE=os.path.join(DATA,'knowledge.json'); PORT=int(os.getenv('PORT','5050')); TIMEOUT=14; REFRESH_SECONDS=900
SOURCES=[('Federal Reserve','Macro','https://www.federalreserve.gov/feeds/press_all.xml'),('ECB','Macro','https://www.ecb.europa.eu/rss/press.html'),('BLS','Macro','https://www.bls.gov/feed/bls_latest.rss'),('SEC','Equities','https://www.sec.gov/news/pressreleases.rss'),('CNBC','Equities','https://www.cnbc.com/id/100003114/device/rss/rss.html'),('Yahoo Finance','Equities','https://finance.yahoo.com/news/rssindex'),('CoinDesk','Crypto','https://www.coindesk.com/arc/outboundfeeds/rss/'),('Cointelegraph','Crypto','https://cointelegraph.com/rss'),('OilPrice','Commodities','https://oilprice.com/rss/main'),('USGS Earthquakes','Natural events','https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.atom'),('NIH News','Health & biotech','https://www.nih.gov/news-releases/feed.xml'),('NCI Cancer Research','Health & biotech','https://www.cancer.gov/syndication/rss'),('FDA Press Announcements','Health & biotech','https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml'),('ClinicalTrials.gov studies','Health & biotech','https://clinicaltrials.gov/api/v2/studies?query.cond=cancer&filter.overallStatus=RECRUITING%7CNOT_YET_RECRUITING%7CACTIVE_NOT_RECRUITING&pageSize=25&format=json')]
GDELT=[('GDELT geopolitics','Geopolitics','geopolitics OR conflict OR war'),('GDELT trade','Geopolitics','tariff OR sanctions OR trade restriction'),('GDELT supply','Commodities','oil OR gas OR OPEC OR supply disruption'),('GDELT health research','Health & biotech','cancer AI drug OR oncology breakthrough OR clinical trial')]
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
def tier_for(source, url):
 name=(source+' '+url).lower()
 if any(x in name for x in ('federal reserve','ecb','bank of','bls','bea','sec','imf','usgs','statistics','nih','cancer.gov','fda.gov','clinicaltrials.gov')): return 'official'
 if any(x in name for x in ('reuters','bloomberg','financial times','wall street journal','cnbc','marketwatch','yahoo','associated press','bbc')): return 'major-financial'
 if any(x in name for x in ('investing','trading economics','coindesk','cointelegraph','oilprice')): return 'specialist'
 return 'discovery'

def item(title,summary,url,published,source,category):
 a=analyse(title,summary,category)
 t=tier_for(source,url); ts=date(published)
 return {'id':hashlib.sha1((title+url).encode()).hexdigest()[:16],'title':title,'summary':a['summary'],'excerpt':clean(summary)[:480],'url':url,'source':source,'domain':domain(url),'category':category,'published':ts,'timestamp_type':'published','source_tier':t,'score':a['score'],'score_breakdown':a.get('score_breakdown',{}),'reasons':a['reasons'],'market_relevance':a['market_relevance'],'analysis_provider':a['analysis_provider'],'affected_assets':a.get('affected_assets',[]),'confidence':a.get('confidence','medium'),'why_it_matters':a.get('why_it_matters',a['market_relevance']),'sources':[{'name':source,'domain':domain(url),'url':url,'title':title,'published':ts,'timestamp_type':'published','tier':t,'excerpt':clean(summary)[:480],**{k:source_meta(source,url).get(k) for k in ('rating','stars','rationale')}}],'verification':'single-source','corroboration':1,'connections':[]}
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
   group['sources'].append(x['sources'][0]);group['corroboration']=len({s.get('domain') for s in group['sources']})
   group['source_tier']='official' if any(s.get('tier')=='official' for s in group['sources']) else max((s.get('tier','discovery') for s in group['sources']), key=lambda z:['discovery','specialist','major-financial','official'].index(z))
   group['verification']='corroborated-report' if group['corroboration']>=2 else 'single-source'; group['score']=min(100,group['score']+8)
   group['confidence']='high' if group['source_tier']=='official' and group['corroboration']>=2 else 'medium' if group['corroboration']>=2 or group['source_tier']=='official' else 'low'
   group['reasons']=list(dict.fromkeys(group['reasons']+['independently corroborated']))[:8]
 # Build a small, evidence-based relationship graph. Connections are hypotheses, never facts.
 out=[]
 for x in groups:
  text=(x['title']+' '+x.get('summary','')).lower(); links=[]
  if any(k in text for k in ('rate','central bank','inflation','cpi','jobs','payroll')): links += ['rates → bonds','rates → currencies']
  if any(k in text for k in ('oil','gas','opec','supply','shipping')): links += ['supply → inflation','energy → producers']
  if any(k in text for k in ('tariff','sanction','trade','export')): links += ['trade → exporters','trade → currencies']
  if any(k in text for k in ('bank','credit','default','yield')): links += ['credit → banks','yields → equities']
  x['connections']=list(dict.fromkeys(links))[:4]
  x['level']='High' if x['score']>=65 else 'Medium' if x['score']>=35 else 'Low'
  x['verification_label']='Confirmed official data' if x.get('source_tier')=='official' and x.get('corroboration',1)>=2 else 'Corroborated reporting' if x.get('corroboration',1)>=2 else 'Reported lead — unverified'
  if x['score']>=35 or (x.get('category')=='Health & biotech' and x['score']>=20):out.append(x)
 return sorted(out,key=lambda x:(x['score'],x['published']),reverse=True)[:250]
def parse_trials(raw,source,category,fallback):
 data=json.loads(raw.decode('utf-8')); out=[]
 for study in data.get('studies',[])[:40]:
  p=study.get('protocolSection',{}); ident=p.get('identificationModule',{}); stat=p.get('statusModule',{})
  title=clean(ident.get('briefTitle','')); nct=ident.get('nctId','');
  if not title or not nct: continue
  url='https://clinicaltrials.gov/study/'+nct; published=stat.get('studyFirstPostDateStruct',{}).get('date') or stat.get('lastUpdatePostDateStruct',{}).get('date') or now()
  summary=clean(p.get('descriptionModule',{}).get('briefSummary',''))
  out.append(item(title,summary,url,published,source,category))
 return out

def fetch_all():
 sources=SOURCES+[(n,c,'https://api.gdeltproject.org/api/v2/doc/doc?query='+quote_plus(q)+'&mode=artlist&maxrecords=30&format=rss&sort=datedesc') for n,c,q in GDELT]; items=[];health={};errors=[]
 for n,c,u in sources:
  try:
   got=parse_trials(fetch(u),n,c,u) if 'clinicaltrials.gov/api/' in u else parse(fetch(u),n,c,u)
   items+=got;health[n]={'ok':True,'count':len(got),'url':u}
  except Exception as e:health[n]={'ok':False,'count':0,'url':u,'error':str(e)[:160]};errors.append(n+': '+str(e)[:120])
 return merge(items),health,errors
def build_knowledge(items, previous=None):
 previous=previous or {}
 if isinstance(previous,list): learned={hashlib.sha1((str(r.get('category',''))+'|'+str(r.get('topic',''))).encode()).hexdigest()[:14]:r for r in previous if isinstance(r,dict)}
 elif isinstance(previous,dict): learned=dict(previous)
 else: learned={}
 for x in items:
  if x.get('score',0)<45 or (x.get('source_tier')!='official' and x.get('corroboration',1)<2): continue
  key=hashlib.sha1((x.get('category','')+'|'+re.sub(r'[^a-z0-9 ]','',x.get('title','').lower())[:140]).encode()).hexdigest()[:14]
  rec=learned.get(key, {'first_seen':x.get('published'), 'observations':0})
  rec.update({'topic':x.get('title'), 'category':x.get('category'), 'last_seen':x.get('published'), 'confidence':x.get('confidence','medium'), 'verification':x.get('verification_label'), 'source_tier':x.get('source_tier'), 'market_links':x.get('connections',[]), 'score':x.get('score',0), 'evidence_urls':[s.get('url') for s in x.get('sources',[])[:4]]})
  rec['observations']=int(rec.get('observations',0))+1
  learned[key]=rec
 return {'version':1,'updated':now(),'entries':list(learned.values())[-500:]}

def save(payload):
 os.makedirs(DATA,exist_ok=True);tmp=CACHE+'.tmp'
 with open(tmp,'w',encoding='utf8') as f:json.dump(payload,f,ensure_ascii=False)
 os.replace(tmp,CACHE)
 try:
  prior=json.load(open(KNOWLEDGE,encoding='utf8')).get('entries',{})
 except Exception: prior={}
 ktmp=KNOWLEDGE+'.tmp'
 with open(ktmp,'w',encoding='utf8') as f: json.dump(build_knowledge(payload.get('items',[]), prior),f,ensure_ascii=False)
 os.replace(ktmp,KNOWLEDGE)
def refresh(force=False):
 with lock:
  if state['refreshing']:return False
  state['refreshing']=True
 try:
  items,health,errors=fetch_all();payload={'items':items,'last_refresh':now(),'source_health':health,'errors':errors,'source_registry':REGISTRY,'registry_summary':{'total':len(REGISTRY),'categories':{c:sum(1 for r in REGISTRY if r['category']==c) for c in sorted({r['category'] for r in REGISTRY})},'monitored':sum(1 for r in REGISTRY if r.get('monitorable'))}};save(payload)
  try: payload['knowledge']=json.load(open(KNOWLEDGE,encoding='utf8'))
  except Exception: payload['knowledge']={'version':1,'entries':[]}
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
 @app.get('/api/sources')
 def sources():return jsonify({'sources':REGISTRY,'summary':{'total':len(REGISTRY),'categories':{c:sum(1 for r in REGISTRY if r['category']==c) for c in sorted({r['category'] for r in REGISTRY})}}})
 @app.get('/api/knowledge')
 def knowledge():
  try:return jsonify(json.load(open(KNOWLEDGE,encoding='utf8')))
  except Exception:return jsonify({'version':1,'entries':[]})
 @app.get('/health')
 def health():return jsonify({'ok':True,'items':len(state['items']),'last_refresh':state['last_refresh']})
if __name__=='__main__':init();app.run(host='0.0.0.0',port=PORT,debug=False)
