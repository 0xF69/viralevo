#!/usr/bin/env python3
"""
ViralEvo — Weekly Self-Evolution
Analyzes prediction accuracy over the past 7 days and adjusts model weights.
Run: python3 scripts/weekly_review.py
Typically runs every Monday at your configured report time.
"""

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

WEIGHT_KEYS = ["platform_signal", "engagement_velocity", "cross_platform_spread", "niche_relevance", "goal_alignment"]
W_FLOOR   = 0.08
W_CEILING = 0.45
MAX_DELTA = 0.05


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


def clamp(v): return max(W_FLOOR, min(W_CEILING, v))


def normalize(weights: dict) -> dict:
    """Ensure weights sum to exactly 1.0."""
    total = sum(weights.values())
    return {k: round(v / total, 6) for k, v in weights.items()}


def adjust_weights(current: dict, error_by_source: dict, accuracy_drop: bool) -> dict:
    """Propose new weights based on error analysis."""
    max_delta = MAX_DELTA * 2 if accuracy_drop else MAX_DELTA
    new = dict(current)

    # Penalize platform_signal if indirect sources had high error
    if error_by_source.get("indirect_avg_error", 0) > error_by_source.get("direct_avg_error", 0) + 15:
        new["platform_signal"] = clamp(new["platform_signal"] - max_delta * 0.5)
        new["niche_relevance"] = clamp(new["niche_relevance"] + max_delta * 0.5)

    # Boost niche_relevance if relevance-flagged predictions were more accurate
    if error_by_source.get("niche_accuracy_gain", 0) > 5:
        delta = min(max_delta, 0.03)
        new["niche_relevance"] = clamp(new["niche_relevance"] + delta)
        new["cross_platform_spread"] = clamp(new["cross_platform_spread"] - delta * 0.5)
        new["engagement_velocity"] = clamp(new["engagement_velocity"] - delta * 0.5)

    return normalize(new)


def run_weekly_review():
    if not CFG_PATH.exists():
        print("❌ Not configured. Run: node scripts/onboarding.js")
        return

    config = json.loads(CFG_PATH.read_text())
    lang = config.get("language", "en")
    zh = lang == "zh"

    if not DB_PATH.exists():
        log("No database yet. Skipping.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Accuracy stats ─────────────────────────────────────────────────────────
    rows = conn.execute("""
        SELECT v.accurate, v.error_pct, t.source_type, t.platform
        FROM verifications v
        JOIN predictions p ON v.prediction_id = p.id
        JOIN topics t ON p.topic_id = t.id
        WHERE v.verified_at >= datetime('now', '-7 days')
    """).fetchall()

    if not rows:
        log("⚠️  No verification data from last 7 days.")
        log("   This is normal if you just installed ViralEvo.")
        log("   The system needs at least 24h of predictions before it can verify accuracy.")
        log("   Come back next Monday after running collect + report daily.")
        conn.close()
        return

    total = len(rows)
    correct = sum(1 for r in rows if r["accurate"] == 1)
    accuracy = round(correct / total * 100)

    direct_errors   = [r["error_pct"] for r in rows if r["source_type"] == "direct"]
    indirect_errors = [r["error_pct"] for r in rows if r["source_type"] == "indirect"]
    direct_avg      = round(sum(direct_errors) / len(direct_errors), 1) if direct_errors else 0
    indirect_avg    = round(sum(indirect_errors) / len(indirect_errors), 1) if indirect_errors else 0

    # Check prior week accuracy (for rollback logic)
    prior_row = conn.execute("""
        SELECT accuracy_before FROM weight_history
        ORDER BY updated_at DESC LIMIT 1
    """).fetchone()
    prior_accuracy = prior_row["accuracy_before"] if prior_row else None

    accuracy_drop = prior_accuracy is not None and accuracy < prior_accuracy - 20

    # Check for consecutive accuracy drops (auto-rollback trigger)
    # A "drop" = this week's accuracy is lower than the previous week's.
    # We look at the last 3 weight_history rows (excluding current week) and
    # count how many consecutive trailing entries show a declining accuracy_before.
    consecutive_drops = 0
    if prior_accuracy is not None and accuracy < prior_accuracy:
        recent_rows = conn.execute("""
            SELECT accuracy_before FROM weight_history
            ORDER BY updated_at DESC LIMIT 3
        """).fetchall()
        prev = accuracy
        for row in recent_rows:
            if row["accuracy_before"] is not None and prev < row["accuracy_before"]:
                consecutive_drops += 1
                prev = row["accuracy_before"]
            else:
                break

    current_weights = config.get("weights", {k: 0.2 for k in WEIGHT_KEYS})

    # Auto-rollback?
    if consecutive_drops >= 2:
        rollback_row = conn.execute("""
            SELECT weights FROM weight_history
            WHERE rollback = 0
            ORDER BY accuracy_before DESC LIMIT 1
        """).fetchone()
        if rollback_row:
            new_weights = json.loads(rollback_row["weights"])
            reason = f"AUTO-ROLLBACK: accuracy dropped {consecutive_drops} consecutive weeks"
            log(f"⚠️ {reason}")
            rollback = True
        else:
            new_weights = current_weights
            reason = "No rollback candidate found"
            rollback = False
    else:
        # niche_accuracy_gain: compare accuracy rate of direct vs indirect predictions.
        # A positive value means direct-source predictions were more accurate,
        # which is the real signal that niche_relevance weight should increase.
        direct_accurate   = sum(1 for r in rows if r["source_type"] == "direct"   and r["accurate"] == 1)
        indirect_accurate = sum(1 for r in rows if r["source_type"] == "indirect" and r["accurate"] == 1)
        direct_rate   = (direct_accurate   / len(direct_errors)   * 100) if direct_errors   else 50
        indirect_rate = (indirect_accurate / len(indirect_errors) * 100) if indirect_errors else 50
        error_context = {
            "direct_avg_error":   direct_avg,
            "indirect_avg_error": indirect_avg,
            "niche_accuracy_gain": max(0, direct_rate - indirect_rate),
        }
        new_weights = adjust_weights(current_weights, error_context, accuracy_drop)
        reason = f"Weekly review: accuracy={accuracy}%, direct_err={direct_avg}%, indirect_err={indirect_avg}%"
        rollback = False

    # Write config first — if it fails, we don't corrupt the DB
    config["weights"] = new_weights
    try:
        CFG_PATH.write_text(json.dumps(config, indent=2))
    except Exception as e:
        log(f"❌ Failed to write config: {e}. Aborting weight_history update.")
        conn.close()
        return

    # Record in weight_history only after config is safely written
    conn.execute("""
        INSERT INTO weight_history (id, updated_at, weights, reason, accuracy_before, rollback)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(uuid.uuid4()),
        datetime.now(timezone.utc).isoformat(),
        json.dumps(new_weights),
        reason,
        accuracy,
        1 if rollback else 0
    ))
    conn.commit()
    conn.close()

    # ── Generate weekly report ─────────────────────────────────────────────────
    changes = []
    for k in WEIGHT_KEYS:
        old = round(current_weights.get(k, 0.2), 4)
        new = round(new_weights.get(k, 0.2), 4)
        if abs(new - old) > 0.001:
            arrow = "↑" if new > old else "↓"
            changes.append(f"  {k}: {old} → {new} {arrow}{abs(new-old):.3f}")

    report_lines = [
        f"# ViralEvo Weekly Review — {datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"**Accuracy this week:** {accuracy}% ({total} predictions)",
        f"**Prior week accuracy:** {prior_accuracy}%" if prior_accuracy else "**Prior week accuracy:** N/A (first week)",
        "",
        "## Weight Changes",
        *(changes if changes else ["  No changes — model is stable."]),
        "",
        f"## Error Analysis",
        f"  Direct source avg error:   {direct_avg}%",
        f"  Indirect source avg error: {indirect_avg}%",
        "",
        f"**Reason:** {reason}",
    ]

    report_dir = BASE_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}_weekly.md"

    # ── Personal feedback summary (appended before file write) ────────────────
    try:
        conn_fb = sqlite3.connect(DB_PATH)
        conn_fb.row_factory = sqlite3.Row
        fb_rows = conn_fb.execute("""
            SELECT f.result, f.views, f.likes, f.saves
            FROM personal_feedback f
            WHERE f.submitted_at >= datetime('now', '-7 days')
        """).fetchall()
        conn_fb.close()
        if fb_rows:
            fb_views = sum(r["views"] or 0 for r in fb_rows)
            fb_good  = sum(1 for r in fb_rows if (r["result"] or "").lower() in ("great", "good", "excellent"))
            report_lines += [
                "",
                "## Feedback from Your Posts (Last 7 Days)",
                f"  Submissions : {len(fb_rows)}",
                f"  Total views : {fb_views:,}",
                f"  Positive    : {fb_good} / {len(fb_rows)}",
            ]
    except Exception:
        pass

    # Write file after all sections are assembled
    report_path.write_text("\n".join(report_lines))
    log(f"✅ Weekly review complete. Accuracy: {accuracy}%. Weights updated. Report: {report_path.name}")
    print("\n".join(report_lines))


if __name__ == "__main__":
    run_weekly_review()
