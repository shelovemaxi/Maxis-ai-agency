#!/usr/bin/env python3
"""Generate the static and Flask frontend copies from one canonical source.

The root frontend files are the only files edited by hand.  GitHub Pages and the
local Flask app still receive the copies they need, but a single command keeps
them identical and fails loudly if a generated copy drifts.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import shutil

ROOT = Path(__file__).resolve().parents[1]

# source -> generated destinations.  Keep this list small and explicit: it is
# the source-of-truth map for the frontend, not a second implementation.
COPIES = {
    "app.js": (ROOT / "docs/app.js", ROOT / "static/app.js"),
    "style.css": (ROOT / "docs/style.css", ROOT / "static/style.css"),
    "index.html": (ROOT / "docs/index.html", ROOT / "templates/index.html"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> list[str]:
    drift: list[str] = []
    for source, destinations in COPIES.items():
        source_path = ROOT / source
        if not source_path.exists():
            drift.append(f"missing canonical file: {source}")
            continue
        source_hash = digest(source_path)
        for destination in destinations:
            if not destination.exists():
                drift.append(f"missing generated file: {destination.relative_to(ROOT)}")
            elif digest(destination) != source_hash:
                drift.append(f"out of sync: {destination.relative_to(ROOT)}")
    return drift


def sync() -> None:
    for source, destinations in COPIES.items():
        source_path = ROOT / source
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report drift without changing files")
    args = parser.parse_args()
    if args.check:
        drift = check()
        if drift:
            print("Frontend copies are out of sync:")
            print("\n".join(f"- {entry}" for entry in drift))
            return 1
        print("Frontend copies are in sync.")
        return 0
    sync()
    print("Synced generated frontend copies from the canonical root files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
