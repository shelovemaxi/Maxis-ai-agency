"""Bounded, evidence-aware analysis for Signal Wire.
Rules are always available; optional AI enrichment is short, low-temperature and never authoritative.
"""
from __future__ import annotations
import json, os, re
from urllib.request import Request, urlopen

MARKET_TERMS={"central bank":20,"interest rate":18,"rate decision":20,"inflation":16,"cpi":16,"payroll":14,"jobs":12,"recession":18,"tariff":17,"sanction":17,"war":18,"conflict":15,"ceasefire":12,"opec":18,"oil":11,"gas":11,"supply disruption":20,"export ban":16,"bank failure":24,"default":20,"downgrade":14,"liquidation":16,"etf":10,"earthquake":14,"strike":11,"gdp":18}
NOISE_TERMS={"sponsored":18,"opinion":10,"podcast":8,"recipe":15,"quiz":12,"how to":8,"video":3}
ASSET_MAP={"oil":["crude oil","energy equities"],"gas":["natural gas","utilities"],"central bank":["government bonds","currency markets"],"interest rate":["government bonds","banks","growth equities"],"inflation":["bonds","currency markets"],"tariff":["exporters","currencies"],"sanction":["commodities","affected exporters"],"jobs":["government bonds","cyclical equities"]}

def rule_analysis(title:str, summary:str, category:str)->dict:
 text=(title+' '+summary).lower(); hits=[]; score=0; assets=[]
 for term,weight in MARKET_TERMS.items():
  if term in text: score+=weight; hits.append(term); assets += ASSET_MAP.get(term,[])
 for term,weight in NOISE_TERMS.items():
  if term in text: score-=weight
 for m in re.finditer(r'(?<!\w)([+-]?\d+(?:\.\d+)?)\s*%',text):
  score+=min(18,round(abs(float(m.group(1)))*1.2)); hits.append(m.group(1)+'% move')
 score=max(0,min(100,score)); confidence='medium' if score>=35 else 'low'
 relevance=('High: policy, systemic-risk, macro, or supply-shock signal.' if score>=60 else 'Moderate: potentially market-relevant; inspect evidence.' if score>=35 else 'Low: insufficient material impact detected.')
 return {"score":score,"reasons":hits[:8],"summary":summary[:320] or title,"market_relevance":relevance,"analysis_provider":"rules","affected_assets":list(dict.fromkeys(assets))[:4],"confidence":confidence}

def ai_analysis(title:str, summary:str, category:str)->dict|None:
 key=os.environ.get('GEMINI_API_KEY')
 if not key:return None
 prompt=("You are Signal Wire's evidence-aware market analyst. Return JSON only. "
  "Use only the supplied headline/excerpt; do not add facts, numbers, sources or causal claims not supported. "
  "Be concise: summary <=35 words, market_relevance <=25 words, affected_assets max 4, confidence low/medium/high. "
  f"Category: {category}. Headline: {title}. Excerpt: {summary[:900]}")
 body=json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.05,"maxOutputTokens":220}}).encode()
 try:
  req=Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key='+key,data=body,headers={'Content-Type':'application/json'},method='POST')
  with urlopen(req,timeout=20) as r: raw=json.load(r)
  out=json.loads(raw['candidates'][0]['content']['parts'][0]['text'])
  if not isinstance(out,dict):return None
  out['analysis_provider']='gemini'; return out
 except Exception:return None

def analyse(title,summary,category):
 base=rule_analysis(title,summary,category); ai=ai_analysis(title,summary,category)
 if ai:
  for k in ('summary','market_relevance','affected_assets','confidence'):
   if k in ai and ai[k] not in (None,'',[]):base[k]=ai[k]
 return base

def event_key(title:str)->str:
 words=re.findall(r'[a-z0-9]{3,}',title.lower())
 stop={'the','and','for','with','from','that','this','will','into','after','amid','over','says','said','news','market','markets','update','report'}
 return ' '.join(w for w in words if w not in stop)[:180]

def similar(a:str,b:str)->bool:
 x=set(event_key(a).split()); y=set(event_key(b).split())
 if not x or not y:return False
 overlap=len(x&y)/max(1,min(len(x),len(y)))
 return overlap>=.58 or (len(x&y)>=2 and overlap>=.45)
