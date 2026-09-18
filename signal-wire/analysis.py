"""Small, auditable analysis layer for Signal Wire.

Rules are the safe default. Optional AI enrichment receives only a short source
excerpt and can never change verification or invent evidence.
"""
from __future__ import annotations
import json, os, re
from urllib.request import Request, urlopen

MARKET_TERMS={
    'central bank':20,'interest rate':18,'rate decision':20,'inflation':16,'cpi':16,'payroll':14,'jobs':12,'recession':18,'gdp':18,
    'tariff':17,'sanction':17,'war':18,'conflict':15,'ceasefire':12,'opec':18,'oil':11,'gas':11,'supply disruption':20,
    'export ban':16,'bank failure':24,'default':20,'downgrade':14,'liquidation':16,'etf':10,'earthquake':14,'strike':11,
    'semiconductor':15,'chip shortage':18,'shipping':13,'yield':12,'treasury':13,'currency':10,
}
NOISE_TERMS={'sponsored':18,'opinion':10,'podcast':8,'recipe':15,'quiz':12,'how to':8,'video':3,'slideshow':8}
TIER_WEIGHT={'official':20,'major-financial':12,'specialist':6,'discovery':0}

def rule_analysis(title: str, summary: str, category: str, source_tier: str='discovery')->dict:
    text=(title+' '+summary).lower(); hits=[]; raw_signal=0; noise=0
    for term,weight in MARKET_TERMS.items():
        # Match complete words/phrases only: "war" must not score "Warren".
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)', text): raw_signal+=weight; hits.append(term)
    for term,weight in NOISE_TERMS.items():
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)', text): noise+=weight
    magnitude=0
    for match in re.finditer(r'(?<!\w)([+-]?\d+(?:\.\d+)?)\s*%',text):
        magnitude+=min(18,round(abs(float(match.group(1)))*1.2));hits.append(match.group(1)+'% move')
    market_signal=min(48,raw_signal)
    breadth=min(14,len(set(hits))*2)
    source_priority=TIER_WEIGHT.get(source_tier,0)
    score=max(0,min(100,market_signal+magnitude+breadth+source_priority-noise))
    if score>=65: relevance='High-priority market signal: broad, material, or policy-sensitive.'
    elif score>=35: relevance='Potentially market-relevant; verify the key claim before relying on it.'
    else: relevance='Below the materiality threshold unless new evidence changes the picture.'
    assets=[]
    if any(k in text for k in ('rate','inflation','cpi','jobs','payroll','gdp','yield','treasury')): assets += ['government bonds','FX','rate-sensitive equities']
    if any(k in text for k in ('oil','gas','opec','supply','shipping','energy')): assets += ['energy','commodities','inflation-sensitive assets']
    if any(k in text for k in ('bank','credit','default','loan')): assets += ['banks','credit markets']
    if any(k in text for k in ('chip','semiconductor','technology')): assets += ['technology','manufacturing']
    if any(k in text for k in ('crypto','bitcoin','ethereum','token')): assets += ['crypto']
    return {
        'score':score,
        'score_breakdown':{'market_signal':market_signal,'magnitude':min(18,magnitude),'breadth':breadth,'source_priority':source_priority,'noise_penalty':noise},
        'reasons':hits[:8],
        'summary':summary[:420] or title,
        'market_relevance':relevance,
        'why_it_matters':('Could transmit through '+('macro markets' if score>=65 else 'a sector or asset group')+'; this is analysis, not a confirmed price effect.'),
        'affected_assets':list(dict.fromkeys(assets))[:5],
        'confidence':'medium' if source_tier=='official' or score>=65 else 'low',
        'analysis_provider':'rules'
    }

def ai_analysis(title: str, summary: str, category: str, source_tier: str)->dict|None:
    """Optional Gemini enrichment; enabled only by a server/Actions secret."""
    key=os.environ.get('GEMINI_API_KEY')
    if not key:return None
    prompt=("Return JSON only with summary (max 45 words), market_relevance (max 30 words), "
            "affected_assets (array up to 5), and confidence (low|medium|high). Use only the excerpt. "
            "Do not invent facts, numbers, sources, dates, causation, or certainty. "
            f"Tier: {source_tier}. Category: {category}. Headline: {title}. Excerpt: {summary[:900]}")
    body=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseMimeType':'application/json','temperature':0.1,'maxOutputTokens':220}}).encode()
    try:
        req=Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key='+key,data=body,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=15) as response: raw=json.load(response)
        text=raw['candidates'][0]['content']['parts'][0]['text'];out=json.loads(text);out['analysis_provider']='gemini';return out
    except Exception:return None

def analyse(title, summary, category, source_tier='discovery'):
    base=rule_analysis(title,summary,category,source_tier)
    ai=ai_analysis(title,summary,category,source_tier)
    if ai:base.update({k:v for k,v in ai.items() if v not in (None,'',[])})
    return base

def event_key(title: str)->str:
    words=re.findall(r'[a-z0-9]{3,}',title.lower())
    stop={'the','and','for','with','from','that','this','will','into','after','amid','over','says','said','news','market','markets','update','reported'}
    return ' '.join(w for w in words if w not in stop)[:180]

def similar(a: str,b: str)->bool:
    x=set(event_key(a).split());y=set(event_key(b).split())
    if not x or not y:return False
    overlap=len(x&y)/max(1,min(len(x),len(y)))
    return overlap>=.58 or (len(x)>=3 and len(y)>=3 and len(x&y)>=3)
