#!/usr/bin/env python3
"""
ViralEvo — Quick Status Check
Run: python3 scripts/status.py
"""
import os, sys, json, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = Path(os.environ.get("VIRALEVO_DATA_DIR",
    Path.home() / ".openclaw" / "workspace" / "viralevo"))

load_dotenv(BASE_DIR / ".env")

def ok(msg): print(f"  ✅ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def err(msg): print(f"  ❌ {msg}")

print(f"\n📊 ViralEvo Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

# Config
cfg_path = BASE_DIR / "config.json"
if cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    ok(f"Config: niche={cfg.get('niche','?')}, lang={cfg.get('language','?')}")
else:
    err("Not configured — run: node scripts/onboarding.js")
    sys.exit(1)

# API Key
key = os.environ.get("TAVILY_API_KEY", "")
if key and key.startswith("tvly-"):
    ok(f"Tavily API key: {key[:10]}...")
elif key:
    warn(f"Tavily key present but unexpected format: {key[:8]}...")
else:
    err("TAVILY_API_KEY not set — add to ~/.openclaw/workspace/viralevo/.env")

# Database
db_path = BASE_DIR / "data" / "trends.db"
if db_path.exists():
    conn = sqlite3.connect(db_path)
    topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    preds  = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    verifs = conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0]
    recent = conn.execute(
        "SELECT COUNT(*) FROM topics WHERE detected_at >= datetime('now', '-24 hours')"
    ).fetchone()[0]
    conn.close()
    ok(f"Database: {topics} topics, {preds} predictions, {verifs} verifications")
    if recent > 0:
        ok(f"Recent signals: {recent} topics from last 24h")
    else:
        warn("No topics from last 24h — run: node scripts/collect.js")
else:
    err("No database — run: python3 db/init_db.py")

# Reports
reports_dir = BASE_DIR / "reports"
reports = list(reports_dir.glob("*.md")) if reports_dir.exists() else []
if reports:
    latest = max(reports, key=lambda p: p.stat().st_mtime)
    age_h = (datetime.now().timestamp() - latest.stat().st_mtime) / 3600
    ok(f"Latest report: {latest.name} ({age_h:.0f}h ago)")
else:
    warn("No reports yet — run: python3 scripts/report.py")

# Weights
weights = cfg.get("weights", {})
if weights:
    total = sum(weights.values())
    ok(f"Weights sum: {total:.4f} (should be 1.0)")
    if abs(total - 1.0) > 0.01:
        err(f"Weights don't sum to 1.0! Run weekly_review to fix.")

print()
