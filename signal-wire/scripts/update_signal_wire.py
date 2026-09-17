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
os.makedirs(DOCS,exist_ok=True)
tmp=os.path.join(DOCS,"data.json.tmp")
with open(tmp,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False)
os.replace(tmp,os.path.join(DOCS,"data.json"))
print(json.dumps({"items":len(items),"healthy_sources":sum(1 for x in health.values() if x.get("ok")),"errors":len(errors)}))
