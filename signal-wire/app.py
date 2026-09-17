#!/usr/bin/env python3
"""Signal Wire: dependency-light local market intelligence dashboard."""
from __future__ import annotations
import json, os, re, time, html, hashlib, threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

try:
    from flask import Flask, jsonify, render_template, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
PORT = int(os.environ.get("PORT", "5050"))
REFRESH_SECONDS = 15 * 60
TIMEOUT = 12
USER_AGENT = "SignalWire/1.0 (local market intelligence; contact: local@example.invalid)"

# Edit this list to add/remove free feeds. No credentials are used.
SOURCE_CONFIG = [
    ("Federal Reserve", "Macro", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("ECB", "Macro", "https://www.ecb.europa.eu/rss/press.html"),
    ("BLS", "Macro", "https://www.bls.gov/feed/bls_latest.rss"),
    ("SEC", "Equities", "https://www.sec.gov/news/pressreleases.rss"),
    ("CNBC", "Equities", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Yahoo Finance", "Equities", "https://finance.yahoo.com/news/rssindex"),
    ("CoinDesk", "Crypto", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "Crypto", "https://cointelegraph.com/rss"),
    ("OilPrice", "Commodities", "https://oilprice.com/rss/main"),
    ("USGS Earthquakes", "Natural events", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.atom"),
]
GDELT_QUERIES = [
    ("GDELT geopolitics", "Geopolitics", "geopolitics OR conflict OR war"),
    ("GDELT trade", "Geopolitics", "tariff OR sanctions OR trade restriction"),
    ("GDELT supply", "Commodities", "oil OR gas OR OPEC OR supply disruption"),
]

POSITIVE = {
    "rate decision": 20, "interest rate": 14, "inflation": 14, "cpi": 14, "jobs": 12,
    "payroll": 12, "recession": 18, "sanctions": 16, "tariff": 15, "war": 18,
    "conflict": 16, "ceasefire": 14, "opec": 16, "oil": 10, "gas": 10,
    "supply disruption": 17, "bank failure": 22, "downgrade": 12, "hack": 18,
    "etf": 11, "liquidation": 16, "earthquake": 16, "default": 18, "emergency": 16,
    "strike": 10, "export ban": 15, "market crash": 22, "restructure": 10,
}
NEGATIVE = {"sponsored": 12, "opinion": 7, "podcast": 5, "recipe": 9, "how to": 6, "quiz": 8, "video: ": 4}

state = {"items": [], "last_refresh": None, "source_health": {}, "errors": [], "refreshing": False}
lock = threading.Lock()

def now_iso(): return datetime.now(timezone.utc).isoformat()
def domain(url):
    return re.sub(r"^www\.", "", (re.search(r"https?://([^/]+)", url or "") or ["", "unknown"])[1].lower())
def clean_text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def parse_date(s):
    if not s: return now_iso()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return now_iso()
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()
def tag_text(el, names):
    for child in list(el):
        if child.tag.split("}")[-1].lower() in names:
            return "".join(child.itertext()).strip()
    return ""

def parse_feed(raw, source, category, url):
    root = ET.fromstring(raw)
    out=[]
    # RSS item and Atom entry are both handled by local-name.
    nodes=[e for e in root.iter() if e.tag.split("}")[-1].lower() in ("item","entry")]
    for n in nodes[:60]:
        title=clean_text(tag_text(n,{"title"}))
        if not title: continue
        link=tag_text(n,{"link"})
        for c in list(n):
            if c.tag.split("}")[-1].lower()=="link" and c.attrib.get("href"): link=c.attrib["href"]; break
        summary=clean_text(tag_text(n,{"description","summary","content","encoded"}))
        date=tag_text(n,{"pubdate","published","updated","date"})
        out.append(make_item(title, summary, link or url, date, source, category))
    return out

def make_item(title, summary, link, date, source, category):
    text=(title+" "+summary).lower(); reasons=[]; score=0
    for phrase, weight in POSITIVE.items():
        if phrase in text: score += weight; reasons.append(phrase)
    for phrase, weight in NEGATIVE.items():
        if phrase in text: score -= weight
    for m in re.findall(r"(?:up|down|gain|lose|rose|fell|drop|surge|plunge)[^%]{0,12}(\d+(?:\.\d+)?)%|([+-]?\d+(?:\.\d+)?)%", text):
        val=float(next(x for x in m if x)); score += min(18, int(abs(val)*1.2))
        reasons.append(f"{val:g}% move")
    score=max(0,min(100,score));
    return {"id": hashlib.sha1((title+link).encode()).hexdigest()[:16], "title":title, "summary":summary[:360], "url":link,
            "source":source, "domain":domain(link), "category":category, "published":parse_date(date),
            "score":score, "level":"High" if score>=60 else "Medium" if score>=30 else "Low", "reasons":reasons[:8], "corroboration":1}

def fetch(url):
    req=Request(url, headers={"User-Agent":USER_AGENT, "Accept":"application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urlopen(req, timeout=TIMEOUT) as r: return r.read()

def fetch_all():
    items=[]; health={}; errors=[]
    sources=SOURCE_CONFIG[:]
    for name, cat, query in GDELT_QUERIES:
        sources.append((name,cat,"https://api.gdeltproject.org/api/v2/doc/doc?query="+quote_plus(query)+"&mode=artlist&maxrecords=25&format=rss&sort=datedesc"))
    for name,cat,url in sources:
        try:
            parsed=parse_feed(fetch(url),name,cat,url); items.extend(parsed); health[name]={"ok":True,"count":len(parsed),"url":url}
        except Exception as e:
            health[name]={"ok":False,"count":0,"url":url,"error":str(e)[:160]}; errors.append(f"{name}: {str(e)[:120]}")
    # Normalize duplicates by title, then enrich corroboration by distinct domains.
    groups={}
    for it in items:
        key=re.sub(r"[^a-z0-9]+"," ",it["title"].lower()).strip()
        if not key: continue
        if key not in groups: groups[key]=it
        else:
            old=groups[key]; old["corroboration"] += 1
            if it["domain"] != old["domain"]: old["score"]=min(100,old["score"]+4); old["reasons"].append("multi-source corroboration")
    items=list(groups.values())
    for it in items: it["level"]="High" if it["score"]>=60 else "Medium" if it["score"]>=30 else "Low"
    items.sort(key=lambda x:(x["score"],x["published"]),reverse=True)
    return items[:300],health,errors

def load_cache():
    try:
        with open(CACHE_FILE,encoding="utf8") as f: return json.load(f)
    except Exception: return None

def save_cache(items,health,errors):
    os.makedirs(DATA_DIR,exist_ok=True)
    payload={"items":items,"last_refresh":now_iso(),"source_health":health,"errors":errors}
    tmp=CACHE_FILE+".tmp"
    with open(tmp,"w",encoding="utf8") as f: json.dump(payload,f,ensure_ascii=False)
    os.replace(tmp,CACHE_FILE); return payload

def refresh(force=False):
    with lock:
        if state["refreshing"]: return False
        if not force and state["last_refresh"]:
            try:
                if time.time()-datetime.fromisoformat(state["last_refresh"].replace("Z","+00:00")).timestamp()<REFRESH_SECONDS: return False
            except Exception: pass
        state["refreshing"]=True
    try:
        items,health,errors=fetch_all(); payload=save_cache(items,health,errors)
        with lock: state.update(payload)
        return True
    except Exception as e:
        with lock: state["errors"]=["Refresh failed: "+str(e)]
        return False
    finally:
        with lock: state["refreshing"]=False

def init():
    cached=load_cache()
    if cached: state.update(cached)
    if not state["items"] or not state["last_refresh"]:
        threading.Thread(target=refresh,args=(True,),daemon=True).start()
    elif time.time()-datetime.fromisoformat(state["last_refresh"].replace("Z","+00:00")).timestamp()>=REFRESH_SECONDS:
        threading.Thread(target=refresh,daemon=True).start()

HTML_FALLBACK='''<!doctype html><meta charset="utf-8"><title>Signal Wire</title><h1>Signal Wire</h1><p>Flask is not installed. Use <code>pip install -r requirements.txt</code> for the full dashboard.</p><p><a href="/api/items">View API data</a></p>'''
if HAS_FLASK:
    app=Flask(__name__)
    @app.get("/")
    def index(): return render_template("index.html")
    @app.get("/api/items")
    def api_items():
        if state["last_refresh"] and time.time()-datetime.fromisoformat(state["last_refresh"].replace("Z","+00:00")).timestamp()>=REFRESH_SECONDS: threading.Thread(target=refresh,daemon=True).start()
        return jsonify({"items":state["items"],"last_refresh":state["last_refresh"],"source_health":state["source_health"],"errors":state["errors"],"refreshing":state["refreshing"]})
    @app.post("/api/refresh")
    def api_refresh(): threading.Thread(target=refresh,args=(True,),daemon=True).start(); return jsonify({"accepted":True})
    @app.get("/api/status")
    def api_status(): return jsonify({"last_refresh":state["last_refresh"],"source_health":state["source_health"],"errors":state["errors"],"refreshing":state["refreshing"],"refresh_interval_seconds":REFRESH_SECONDS})
    @app.get("/health")
    def health(): return jsonify({"ok":True,"items":len(state["items"]),"last_refresh":state["last_refresh"]})
else:
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=="/": body=HTML_FALLBACK.encode(); typ="text/html"
            elif self.path.startswith("/api/") or self.path=="/health": body=json.dumps({"items":state["items"],"last_refresh":state["last_refresh"],"source_health":state["source_health"],"errors":state["errors"]}).encode(); typ="application/json"
            else: self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type",typ); self.end_headers(); self.wfile.write(body)
        def log_message(self,*a): pass
    app=None

if __name__=="__main__":
    init()
    if HAS_FLASK: app.run(host="0.0.0.0",port=PORT,debug=False)
    else: ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
