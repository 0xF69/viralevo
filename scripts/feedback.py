#!/usr/bin/env python3
"""
ViralEvo — Feedback Logger
Records real post performance back into the model so weekly_review can learn from it.

Usage (CLI):
  python3 scripts/feedback.py --topic-id <id> --platform tiktok --views 80000
  python3 scripts/feedback.py --list           # show recent unmatched topics
  python3 scripts/feedback.py --search "hair clips"  # find topic by keyword

Called by the OpenClaw agent when the user says things like:
  "The hair clips video got 80k views on TikTok"
  "那个AI文章效果很好，小红书5000收藏"
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
load_dotenv(BASE_DIR.parent / ".env")

DB_PATH  = BASE_DIR / "data" / "trends.db"
CFG_PATH = BASE_DIR / "config.json"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_recent_topics(limit=10):
    """Show recent topics that don't yet have feedback, to help the user pick one."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.id, t.title, t.platform, t.detected_at
        FROM topics t
        LEFT JOIN personal_feedback f ON t.id = f.topic_id
        WHERE f.id IS NULL
        ORDER BY t.detected_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    if not rows:
        print("No topics without feedback found.")
        return
    print(f"\nRecent topics without feedback ({len(rows)} shown):\n")
    for r in rows:
        print(f"  {r['id'][:12]}…  [{r['platform']}]  {r['title'][:60]}  ({r['detected_at'][:10]})")


def search_topics(keyword):
    """Find topics matching a keyword to help identify which one to log feedback for."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, platform, detected_at
        FROM topics
        WHERE title LIKE ?
        ORDER BY detected_at DESC
        LIMIT 10
    """, (f"%{keyword}%",)).fetchall()
    conn.close()
    if not rows:
        print(f"No topics found matching '{keyword}'.")
        return
    print(f"\nMatching topics for '{keyword}':\n")
    for r in rows:
        print(f"  {r['id'][:12]}…  [{r['platform']}]  {r['title'][:60]}  ({r['detected_at'][:10]})")


def log_feedback(topic_id, platform, views=None, likes=None, saves=None,
                 result=None, published_time=None, raw_text=None):
    """Write feedback for a topic into personal_feedback table."""
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False

    conn = get_conn()

    # Verify topic exists
    topic = conn.execute("SELECT id, title FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if not topic:
        # Try prefix match
        topic = conn.execute("SELECT id, title FROM topics WHERE id LIKE ?", (f"{topic_id}%",)).fetchone()
    if not topic:
        print(f"❌ Topic not found: {topic_id}")
        conn.close()
        return False

    # Use a stable ID (hash of topic_id) so re-submitting feedback replaces the existing row
    import hashlib
    feedback_id = "fb-" + hashlib.md5(topic["id"].encode()).hexdigest()[:16]
    conn.execute("""
        INSERT OR REPLACE INTO personal_feedback
          (id, topic_id, submitted_at, platform, published_time, views, likes, saves, result, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        feedback_id,
        topic["id"],
        datetime.now(timezone.utc).isoformat(),
        platform or "",
        published_time or "",
        views,
        likes,
        saves,
        result or "",
        raw_text or "",
    ))
    conn.commit()
    conn.close()

    print(f"✅ Feedback logged for: {topic['title'][:60]}")
    if views:  print(f"   Views  : {views:,}")
    if likes:  print(f"   Likes  : {likes:,}")
    if saves:  print(f"   Saves  : {saves:,}")
    if result: print(f"   Result : {result}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log post performance feedback")
    parser.add_argument("--topic-id",       type=str, help="Topic ID (or prefix) to attach feedback to")
    parser.add_argument("--platform",       type=str, help="Platform where you posted (tiktok, instagram, etc.)")
    parser.add_argument("--views",          type=int, help="View count")
    parser.add_argument("--likes",          type=int, help="Like count")
    parser.add_argument("--saves",          type=int, help="Save / bookmark count")
    parser.add_argument("--result",         type=str, help="Qualitative result (great/ok/poor)")
    parser.add_argument("--published-time", type=str, help="When you published (ISO datetime)")
    parser.add_argument("--raw",            type=str, help="Free-text description of results")
    parser.add_argument("--list",           action="store_true", help="List recent topics without feedback")
    parser.add_argument("--search",         type=str, help="Search topics by keyword")
    args = parser.parse_args()

    if args.list:
        list_recent_topics()
    elif args.search:
        search_topics(args.search)
    elif args.topic_id:
        log_feedback(
            topic_id=args.topic_id,
            platform=args.platform,
            views=args.views,
            likes=args.likes,
            saves=args.saves,
            result=args.result,
            published_time=args.published_time,
            raw_text=args.raw,
        )
    else:
        parser.print_help()
