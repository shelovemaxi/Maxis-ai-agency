"""Pluggable Signal Wire analysis layer.
Providers may return a small JSON analysis; deterministic rules remain the safe fallback.
"""
from __future__ import annotations
import json, os, re
from urllib.request import Request, urlopen

MARKET_TERMS={
 "central bank":20,"interest rate":18,"rate decision":20,"inflation":16,"cpi":16,"payroll":14,"jobs":12,"recession":18,
 "tariff":17,"sanction":17,"war":18,"conflict":15,"ceasefire":12,"opec":18,"oil":11,"gas":11,"supply disruption":20,"cancer":16,"oncology":14,"clinical trial":16,"immunotherapy":18,"drug approval":20,"biotech":12,"ai drug":15,"artificial intelligence":10,
 "export ban":16,"bank failure":24,"default":20,"downgrade":14,"liquidation":16,"etf":10,"earthquake":14,"strike":11,
}
NOISE_TERMS={"sponsored":18,"opinion":10,"podcast":8,"recipe":15,"quiz":12,"how to":8,"video":3}

def rule_analysis(title:str, summary:str, category:str)->dict:
    text=(title+' '+summary).lower(); hits=[]; score=0
    for term,weight in MARKET_TERMS.items():
        if term in text: score+=weight; hits.append(term)
    for term,weight in NOISE_TERMS.items():
        if term in text: score-=weight
    for m in re.finditer(r'(?<!\w)([+-]?\d+(?:\.\d+)?)\s*%',text):
        score+=min(18,round(abs(float(m.group(1)))*1.2)); hits.append(m.group(1)+'% move')
    source_quality=0
    if category in ('Macro','Commodities','Health & biotech'): source_quality=8
    breadth=min(12, len(hits)*2)
    score=max(0,min(100,score+source_quality))
    if score>=60: relevance='High: material macro, policy, systemic-risk, or supply-shock signal.'
    elif score>=35: relevance='Moderate: potentially market-relevant; inspect primary reporting.'
    else: relevance='Low: insufficient material market impact detected.'
    assets=[]
    if any(k in text for k in ("rate","inflation","cpi","jobs","payroll")): assets += ["bonds", "currencies"]
    if any(k in text for k in ("oil","gas","opec","supply")): assets += ["energy", "inflation-sensitive assets"]
    if any(k in text for k in ("bank","credit","default")): assets += ["banks", "credit markets"]
    if any(k in text for k in ("cancer","oncology","clinical trial","immunotherapy","drug approval","biotech")): assets += ["biotech and healthcare", "pharmaceutical supply chains"]
    return {"score":score,"score_breakdown":{"market_signal":max(0,score-source_quality),"source_priority":source_quality,"breadth":breadth,"noise_penalty":max(0,-score)},"reasons":hits[:8],"summary":summary[:420] or title,"market_relevance":relevance,"why_it_matters":("Potential " + ("macro/market-wide" if score>=60 else "sector-level") + " transmission; confirm against primary data."),"affected_assets":list(dict.fromkeys(assets))[:4],"confidence":"medium" if score>=35 else "low","analysis_provider":"rules"}

def ai_analysis(title:str, summary:str, category:str)->dict|None:
    """Optional Gemini enrichment. Enabled only by GEMINI_API_KEY in server/Actions secrets."""
    key=os.environ.get('GEMINI_API_KEY')
    if not key: return None
    prompt=("Return JSON only with summary (max 55 words), market_relevance (max 35 words), "
            "affected_assets (array up to 4), and confidence (low|medium|high). Do not invent facts. "
            f"Category: {category}. Headline: {title}. Source excerpt: {summary[:1400]}")
    body=json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.15}}).encode()
    try:
        req=Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key='+key,data=body,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=20) as r: raw=json.load(r)
        text=raw['candidates'][0]['content']['parts'][0]['text']
        out=json.loads(text); out['analysis_provider']='gemini'; return out
    except Exception: return None

def analyse(title,summary,category):
    base=rule_analysis(title,summary,category); ai=ai_analysis(title,summary,category)
    if ai:
        base.update({k:v for k,v in ai.items() if v not in (None,'',[])})
    return base

def event_key(title:str)->str:
    # Stable topic key: removes boilerplate and weak terms, retains meaningful nouns/tickers.
    words=re.findall(r'[a-z0-9]{3,}',title.lower())
    stop={'the','and','for','with','from','that','this','will','into','after','amid','over','says','said','news','market','markets','update'}
    return ' '.join(w for w in words if w not in stop)[:180]

def similar(a:str,b:str)->bool:
    x=set(event_key(a).split()); y=set(event_key(b).split())
    if not x or not y:return False
    return len(x&y)/max(1,min(len(x),len(y)))>=.58
