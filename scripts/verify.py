#!/usr/bin/env python3
"""
ViralEvo — Prediction Verifier
Checks how accurate predictions made N hours ago actually were.
Run: python3 scripts/verify.py --hours 24
     python3 scripts/verify.py --hours 72
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

DB_PATH = BASE_DIR / "data" / "trends.db"


def log(msg):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        log_path = BASE_DIR / "logs" / "execution.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _check_activity(pred: dict, age_hours: int):
    """
    Check whether a topic is still active at verification time.

    For direct sources (HackerNews, Reddit): attempts a lightweight re-fetch
    to see if the topic still has recent activity. Falls back to decay model
    on network errors.

    For indirect sources (Tavily): uses a decay model only, since re-fetching
    Tavily would consume API quota and indirect signals are inherently imprecise.

    Returns (actual_active: int, method: str)
    """
    source_type = pred.get("source_type", "indirect")
    platform    = pred.get("platform", "")
    url         = pred.get("url", "")
    lifecycle   = float(pred.get("lifecycle_hours", 48))

    # ── Decay model (used for indirect sources or on fetch failure) ────────────
    def decay_model():
        # Exponential decay: activity drops to ~37% at t=lifecycle
        import math
        activity_ratio = math.exp(-age_hours / max(lifecycle, 1))
        active = 1 if activity_ratio > 0.25 else 0
        return active, "decay_model"

    if source_type == "indirect":
        return decay_model()

    # ── Direct source re-fetch ─────────────────────────────────────────────────
    try:
        import urllib.request
        import urllib.error

        # HackerNews: check item API for recent comments
        if platform == "hackernews" and "ycombinator.com/item?id=" in url:
            item_id = url.split("id=")[-1].strip()
            api_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (compatible; ViralEvo/0.6.3; +https://github.com/0xF69/viralevo)"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read())
            # Still active if it has descendants (comments) and score > 5
            active = 1 if (data.get("descendants", 0) > 0 and data.get("score", 0) > 5) else 0
            return active, "hn_api"

        # Reddit: check post JSON
        if platform == "reddit" and "reddit.com" in url:
            api_url = url.rstrip("/") + ".json?limit=1"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (compatible; ViralEvo/0.6.3; +https://github.com/0xF69/viralevo)"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read())
            post_data = data[0]["data"]["children"][0]["data"]
            # Still active if upvote ratio > 0.6 and not archived
            active = 1 if (post_data.get("upvote_ratio", 0) > 0.6 and not post_data.get("archived", False)) else 0
            return active, "reddit_api"

        # Dev.to: check article API for recent reactions
        if platform == "dev.to" and "dev.to" in url:
            # Extract article ID from URL (format: https://dev.to/author/slug-12345)
            slug = url.rstrip("/").split("/")[-1]
            api_url = f"https://dev.to/api/articles/{slug}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (compatible; ViralEvo/0.6.3; +https://github.com/0xF69/viralevo)"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read())
            # Still active if reactions > 5 (low bar — dev.to articles stay relevant longer)
            active = 1 if data.get("positive_reactions_count", 0) > 5 else 0
            return active, "devto_api"

    except Exception:
        pass

    # Fallback to decay model if re-fetch failed
    return decay_model()


def verify(hours: int):
    if hours < 4:
        print(f"❌ --hours must be at least 4 (got {hours}). Minimum meaningful verification window is 4h.")
        return

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find predictions made ~N hours ago (±2h window)
    # Lower bound = older (more negative), upper bound = newer (less negative)
    lower = f"-{hours + 2} hours"
    upper = f"-{hours - 2} hours"
    predictions = conn.execute("""
        SELECT p.*, t.title, t.platform, t.source_type, t.source, t.url
        FROM predictions p
        JOIN topics t ON p.topic_id = t.id
        WHERE p.predicted_at BETWEEN
            datetime('now', ?) AND
            datetime('now', ?)
        AND p.id NOT IN (SELECT prediction_id FROM verifications)
    """, (lower, upper)).fetchall()

    if not predictions:
        log(f"No unverified predictions from ~{hours}h ago.")
        conn.close()
        return

    verified = 0
    for pred in predictions:
        pred = dict(pred)
        lifecycle = float(pred["lifecycle_hours"])
        age_at_verify = hours

        # Verification method:
        # For direct sources (HN, Reddit, Dev.to): re-fetch to check if topic still has activity.
        # For indirect sources (Tavily): use a decay model — topic is active if age < predicted lifecycle.
        # In both cases the error is measured against the predicted lifecycle_hours.
        actual_active, method = _check_activity(pred, age_at_verify)

        if actual_active:
            # Still active — real lifecycle is at least age_at_verify, estimate 1.2x predicted
            actual_lifecycle_estimate = max(lifecycle * 1.2, age_at_verify)
        else:
            # Gone quiet — actual lifecycle was approximately age_at_verify
            actual_lifecycle_estimate = age_at_verify

        error_hours = abs(lifecycle - actual_lifecycle_estimate)
        error_pct = error_hours / lifecycle * 100 if lifecycle > 0 else 100
        accurate = 1 if error_pct <= 20 else 0

        conn.execute("""
            INSERT OR IGNORE INTO verifications
              (id, prediction_id, verified_at, actual_active, error_pct, error_hours, accurate, source_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            pred["id"],
            datetime.now(timezone.utc).isoformat(),
            actual_active,
            round(error_pct, 2),
            round(error_hours, 2),
            accurate,
            json.dumps({"method": method, "hours_checked": hours})
        ))
        verified += 1

    conn.commit()

    # Summary stats
    total = conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0]
    correct = conn.execute("SELECT COUNT(*) FROM verifications WHERE accurate=1").fetchone()[0]
    accuracy = round(correct / total * 100) if total > 0 else 0

    log(f"✅ Verified {verified} predictions ({hours}h check). Overall accuracy: {accuracy}% ({total} total)")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify prediction accuracy")
    parser.add_argument("--hours", type=int, default=24, help="Check predictions made N hours ago")
    args = parser.parse_args()
    verify(args.hours)
