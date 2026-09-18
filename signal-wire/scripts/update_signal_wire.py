#!/usr/bin/env python3
"""Fetch Signal Wire data and publish a static JSON snapshot for GitHub Pages."""
import json, os, sys
from datetime import datetime, timezone
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS=os.path.join(ROOT,"docs")
sys.path.insert(0,ROOT)
import app
items, health, errors = app.fetch_all()
payload={"items":items,"last_refresh":datetime.now(timezone.utc).isoformat(),"source_health":health,"errors":errors}
knowledge=app.build_knowledge(items, {})
payload['knowledge']=knowledge
for target in (os.path.join(DOCS,"knowledge.json"), os.path.join(ROOT,"knowledge.json"), os.path.join(os.path.dirname(ROOT),"knowledge.json")):
    try:
        with open(target,"w",encoding="utf8") as f: json.dump(knowledge,f,ensure_ascii=False)
    except OSError: pass
for target in (os.path.join(os.path.dirname(ROOT),'data.json'), os.path.join(ROOT,'data.json')):
    try:
        with open(target,'w',encoding='utf8') as f: json.dump(payload,f,ensure_ascii=False)
    except OSError: pass
os.makedirs(DOCS,exist_ok=True)
tmp=os.path.join(DOCS,"data.json.tmp")
with open(tmp,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False)
os.replace(tmp,os.path.join(DOCS,"data.json"))
print(json.dumps({"items":len(items),"healthy_sources":sum(1 for x in health.values() if x.get("ok")),"errors":len(errors)}))
