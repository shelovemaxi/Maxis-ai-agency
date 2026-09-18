#!/usr/bin/env python3
"""Refresh once and mirror the same snapshot to every static dashboard copy."""
import json, os, sys
from datetime import datetime, timezone
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO=os.path.dirname(ROOT)
sys.path.insert(0,ROOT)
import app
items,health,errors=app.fetch_all()
previous={}
for path in (os.path.join(ROOT,'docs','data.json'),os.path.join(REPO,'data.json')):
    try:
        with open(path,encoding='utf8') as handle: previous=json.load(handle).get('knowledge',{})
        break
    except Exception: pass
knowledge=app.build_knowledge(items,previous)
payload={'items':items,'last_refresh':datetime.now(timezone.utc).isoformat(),'source_health':health,'errors':errors,'knowledge':knowledge}
mirrors=[
    os.path.join(REPO,'data.json'),os.path.join(REPO,'docs','data.json'),
    os.path.join(ROOT,'data.json'),os.path.join(ROOT,'docs','data.json'),
    os.path.join(ROOT,'docs','knowledge.json'),os.path.join(REPO,'knowledge.json'),
]
for target in mirrors:
    os.makedirs(os.path.dirname(target),exist_ok=True)
    tmp=target+'.tmp'
    with open(tmp,'w',encoding='utf8') as handle: json.dump(payload if target.endswith('data.json') else knowledge,handle,ensure_ascii=False)
    os.replace(tmp,target)
print(json.dumps({'items':len(items),'healthy_sources':sum(1 for x in health.values() if x.get('ok')),'sources':len(health),'errors':len(errors),'learned_patterns':len(knowledge.get('entries',[]))}))
