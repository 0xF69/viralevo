#!/usr/bin/env python3
"""
ViralEvo — Keyword Index Manager
View, add, or remove keywords from your niche relevance index.
Usage:
  python3 scripts/keywords.py --show
  python3 scripts/keywords.py --add "your keyword"
  python3 scripts/keywords.py --remove "keyword"
"""

import argparse
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(os.environ.get("VIRALEVO_DATA_DIR",
    Path.home() / ".openclaw" / "workspace" / "viralevo"))

load_dotenv(BASE_DIR / ".env")
DB_PATH  = BASE_DIR / "data" / "trends.db"
CFG_PATH = BASE_DIR / "config.json"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def show_keywords(niche):
    conn = get_conn()
    rows = conn.execute("""
        SELECT keyword, source, weight, added_at
        FROM keyword_index WHERE niche=?
        ORDER BY weight DESC, added_at DESC
    """, (niche,)).fetchall()
    conn.close()
    if not rows:
        print(f"No keywords yet for niche '{niche}'.")
        print("Tip: Run onboarding to auto-populate from your niche template.")
        return
    print(f"\nKeyword index for '{niche}' ({len(rows)} terms):\n")
    for r in rows:
        print(f"  [{r['weight']:.2f}] {r['keyword']}  (source: {r['source']}, added: {r['added_at'][:10]})")


def add_keyword(niche, keyword):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO keyword_index (id, keyword, niche, source, weight, added_at)
        VALUES (?, ?, ?, 'manual', 1.0, ?)
    """, (str(uuid.uuid4()), keyword.lower(), niche, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    print(f"✅ Added: '{keyword}' to niche '{niche}'")


def remove_keyword(niche, keyword):
    conn = get_conn()
    conn.execute("DELETE FROM keyword_index WHERE niche=? AND keyword=?", (niche, keyword.lower()))
    conn.commit()
    conn.close()
    print(f"✅ Removed: '{keyword}' from niche '{niche}'")


def seed_from_template(niche, template_file, conn):
    """Seed keyword index from niche template JSON."""
    if not template_file.exists():
        return 0
    data = json.loads(template_file.read_text())
    keywords = data.get("keywords", [])
    added = 0
    for kw in keywords:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO keyword_index (id, keyword, niche, source, weight, added_at)
                VALUES (?, ?, ?, 'template', 1.0, ?)
            """, (str(uuid.uuid4()), kw.lower(), niche, datetime.now(timezone.utc).isoformat()))
            added += 1
        except Exception:
            pass
    conn.commit()
    return added


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage keyword index")
    parser.add_argument("--show",   action="store_true",  help="Show all keywords")
    parser.add_argument("--add",    type=str,             help="Add a keyword")
    parser.add_argument("--remove", type=str,             help="Remove a keyword")
    parser.add_argument("--seed",   action="store_true",  help="Seed from niche template")
    args = parser.parse_args()

    config = {}
    if CFG_PATH.exists():
        config = json.loads(CFG_PATH.read_text())
    niche = config.get("niche", "custom")

    if args.show:
        show_keywords(niche)
    elif args.add:
        add_keyword(niche, args.add)
    elif args.remove:
        remove_keyword(niche, args.remove)
    elif args.seed:
        template_path = Path(__file__).parent.parent / "templates" / f"{niche}.json"
        conn = get_conn()
        n = seed_from_template(niche, template_path, conn)
        conn.close()
        print(f"✅ Seeded {n} keywords from template '{niche}'.")
    else:
        parser.print_help()
