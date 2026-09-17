#!/usr/bin/env python3
"""Fetch Signal Wire data and publish snapshots used by GitHub Pages builds."""
import json, os, sys
from datetime import datetime, timezone

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP_ROOT)
sys.path.insert(0, APP_ROOT)
import app

items, health, errors = app.fetch_all()
payload = {
    "items": items,
    "last_refresh": datetime.now(timezone.utc).isoformat(),
    "source_health": health,
    "errors": errors,
}

# Keep every published dashboard copy in sync. This avoids stale data when
# Pages/custom-domain configuration points at a different directory.
paths = [
    os.path.join(ROOT, "data.json"),
    os.path.join(ROOT, "docs", "data.json"),
    os.path.join(APP_ROOT, "data.json"),
    os.path.join(APP_ROOT, "docs", "data.json"),
]
for destination in paths:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = destination + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(temporary, destination)

print(json.dumps({
    "items": len(items),
    "healthy_sources": sum(1 for value in health.values() if value.get("ok")),
    "errors": len(errors),
    "updated": paths,
}))
