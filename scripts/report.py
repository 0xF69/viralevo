#!/usr/bin/env python3
"""
ViralEvo — Daily Report Generator
Scores topics, ranks them, and outputs the formatted daily trend report.
Run: python3 scripts/report.py
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

# Load env
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

DB_PATH  = BASE_DIR / "data" / "trends.db"
CFG_PATH = BASE_DIR / "config.json"


def load_config():
    if not CFG_PATH.exists():
        print("❌ Not configured. Run: node scripts/onboarding.js")
        raise SystemExit(1)
    return json.loads(CFG_PATH.read_text())


def get_weights(config):
    weights = config.get("weights", {})
    # Migrate legacy key name from older versions
    if "cross_platform" in weights and "cross_platform_spread" not in weights:
        weights["cross_platform_spread"] = weights.pop("cross_platform")
    return weights if weights else {
        "platform_signal":     0.25,
        "engagement_velocity": 0.25,
        "cross_platform_spread": 0.20,
        "niche_relevance":     0.15,
        "goal_alignment":      0.15,
    }


TYPE_COEFFICIENTS = {
    "viral_product":   1.6,
    "security":        1.5,
    "platform_feature":1.4,
    "brand_news":      1.3,
    "tool_launch":     1.2,
    "seasonal":        1.1,
    "general":         1.0,
    "educational":     0.8,
}

PLATFORM_DECAY = {
    "tiktok":      0.70,
    "twitter":     0.75,
    "youtube":     1.00,
    "instagram":   0.90,
    "reddit":      1.20,
    "linkedin":    1.30,
    "pinterest":   1.50,
    "hackernews":  1.10,
    "dev.to":      1.20,
    "producthunt": 1.10,
}


def _niche_relevance(title: str, keyword_rows: list) -> float:
    """Score 0.0–1.0: weighted keyword match against the full index.

    Uses a log-scaled cap so that matching even one high-weight keyword
    produces a meaningful score, while matching many keywords asymptotically
    approaches 1.0. Avoids the arbitrary top-20 truncation.
    """
    if not keyword_rows:
        return 0.5  # neutral at cold start
    import math
    title_lower = title.lower()
    matched_weight = sum(r["weight"] for r in keyword_rows if r["keyword"] in title_lower)
    if matched_weight == 0:
        return 0.0
    # Normalise against the average weight so a single strong match scores ~0.5
    avg_weight = sum(r["weight"] for r in keyword_rows) / len(keyword_rows)
    # log1p curve: 1 match → ~0.5, 3 matches → ~0.75, 10 matches → ~0.92
    score = math.log1p(matched_weight / max(avg_weight, 0.01)) / math.log1p(10)
    return min(score, 1.0)


GOAL_SIGNALS = {
    "followers": ["viral", "challenge", "trend", "share", "follow"],
    "sales":     ["buy", "product", "review", "deal", "launch", "discount"],
    "authority": ["research", "study", "analysis", "expert", "guide", "explained"],
    "views":     ["viral", "trending", "watch", "popular", "breaking"],
}


def _goal_alignment(title: str, goal: str) -> float:
    """Score 0.0–1.0 based on how well title matches the user's content goal."""
    signals = GOAL_SIGNALS.get(goal, GOAL_SIGNALS["views"])
    title_lower = title.lower()
    hits = sum(1 for s in signals if s in title_lower)
    return min(hits / max(len(signals) * 0.4, 1), 1.0)


def score_topic(topic, weights, config, keyword_rows=None):
    """Compute composite score 0–100 for a topic."""
    raw = json.loads(topic["raw_signal"] or "{}")
    confidence = float(topic["confidence"] or 0.8)

    # Platform signal strength
    w1 = 0
    if topic["source_type"] == "direct":
        points = raw.get("points") or raw.get("score") or raw.get("reactions") or 0
        w1 = min(points / 1000, 1.0)
    else:
        w1 = 0.4 * confidence  # indirect: cap by confidence level

    # Engagement velocity
    comments = raw.get("comments") or raw.get("num_comments") or 0
    w2 = min(comments / 500, 1.0)

    # Cross-platform spread — counts distinct platforms in recent topics
    # (set at call site when available, otherwise use a reasonable default)
    w3 = topic.get("_cross_platform_score", 0.3)

    # Niche relevance — keyword index match
    w4 = _niche_relevance(topic["title"], keyword_rows or [])

    # Goal alignment
    goal = config.get("goal", "views")
    w5 = _goal_alignment(topic["title"], goal)

    ws = weights
    raw_score = (
        w1 * ws["platform_signal"] +
        w2 * ws["engagement_velocity"] +
        w3 * ws["cross_platform_spread"] +
        w4 * ws["niche_relevance"] +
        w5 * ws["goal_alignment"]
    ) * 100

    coef = TYPE_COEFFICIENTS.get(topic["topic_type"] or "general", 1.0)
    score = min(raw_score * coef, 100)

    return round(score, 1)


def estimate_lifecycle(score, platform, topic_type):
    """Estimate how many hours a topic will remain actionable.

    Clamped to [4, 120] hours to avoid nonsensical extremes:
    - Floor 4h: even the shortest-lived topics need at least a few hours to act on.
    - Ceiling 120h (5 days): anything beyond 5 days is evergreen, not trending.
    """
    base = 48  # hours
    score_mult = max(score, 1) / 50
    decay = PLATFORM_DECAY.get(platform, 1.0)
    coef = TYPE_COEFFICIENTS.get(topic_type or "general", 1.0)
    hours = base * score_mult * decay * coef
    return max(4, min(round(hours), 120))


def format_bar(score):
    filled = int(score / 5)
    empty  = 20 - filled
    return "█" * filled + "░" * empty


def posting_window(score, age_hours):
    if score > 80 and age_hours < 6:
        return "RIGHT NOW — window closing fast"
    elif score > 80:
        return "TODAY"
    elif score >= 60:
        return "Tomorrow morning"
    elif score >= 40:
        return "Within 24h"
    else:
        return "Any time this week"


def get_accuracy_stats(conn, days=7):
    try:
        rows = conn.execute("""
            SELECT accurate FROM verifications
            WHERE verified_at >= datetime('now', ?)
        """, (f"-{days} days",)).fetchall()
        if not rows:
            return None, 0
        total = len(rows)
        correct = sum(1 for r in rows if r[0] == 1)
        return round(correct / total * 100), total
    except Exception:
        return None, 0


def get_weight_stats(conn):
    try:
        row = conn.execute("""
            SELECT weights, updated_at FROM weight_history
            ORDER BY updated_at DESC LIMIT 1
        """).fetchone()
        if row:
            return json.loads(row[0]), row[1]
    except Exception:
        pass
    return None, None


def main():
    config = load_config()
    lang = config.get("language", "en")
    zh = lang == "zh"

    if not DB_PATH.exists():
        print("❌ Database not found. Run collect first:\n   node scripts/collect.js")
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    weights = get_weights(config)
    niche_label = config.get("niche_label", config.get("niche", "General"))

    # Fetch recent topics (last 72h)
    topics = conn.execute("""
        SELECT * FROM topics
        WHERE niche = ? AND detected_at >= datetime('now', '-72 hours')
        ORDER BY detected_at DESC
        LIMIT 30
    """, (config["niche"],)).fetchall()

    if not topics:
        msg = "今天暂无新趋势数据。请先运行采集：node scripts/collect.js" if zh else \
              "No recent topics found. Run: node scripts/collect.js"
        print(msg)
        conn.close()
        return

    # Load keyword index for this niche (top 100 by weight)
    keyword_rows = conn.execute("""
        SELECT keyword, weight FROM keyword_index
        WHERE niche = ?
        ORDER BY weight DESC LIMIT 100
    """, (config["niche"],)).fetchall()

    # Compute cross-platform spread per title (titles seen on 2+ platforms score higher)
    title_platforms: dict = {}
    for t in topics:
        td = dict(t)
        title_platforms.setdefault(td["title"], set()).add(td["platform"])

    # Score all topics
    scored = []
    for t in topics:
        t_dict = dict(t)
        platforms_seen = len(title_platforms.get(t_dict["title"], set()))
        t_dict["_cross_platform_score"] = min((platforms_seen - 1) * 0.3, 1.0)
        t_dict["score_computed"] = score_topic(t_dict, weights, config, keyword_rows)
        raw_dt = t_dict["detected_at"]
        if isinstance(raw_dt, str):
            raw_dt = raw_dt.replace("Z", "+00:00")
        detected = datetime.fromisoformat(raw_dt)
        # Use astimezone to correctly handle both naive and aware ISO strings
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        else:
            detected = detected.astimezone(timezone.utc)
        age_hours = (datetime.now(timezone.utc) - detected).total_seconds() / 3600
        t_dict["age_hours"] = round(age_hours, 1)
        t_dict["lifecycle_hours"] = estimate_lifecycle(t_dict["score_computed"], t_dict["platform"], t_dict["topic_type"])
        t_dict["window_remaining"] = max(t_dict["lifecycle_hours"] - age_hours, 0)
        # Compute once and store; render_topics and DB write both reuse this value
        t_dict["_window_label"] = posting_window(t_dict["score_computed"], t_dict["age_hours"])
        scored.append(t_dict)

    scored.sort(key=lambda x: x["score_computed"], reverse=True)

    # ── Write predictions to DB (powers verify.py + weekly_review.py) ─────────
    now_iso = datetime.now(timezone.utc).isoformat()
    weights_json = json.dumps(weights)
    for t in scored:
        pred_id = f"pred-{t['id']}-{datetime.now().strftime('%Y%m%d')}"
        window_label = t["_window_label"]
        try:
            conn.execute("""
                INSERT OR IGNORE INTO predictions
                  (id, topic_id, predicted_at, score, lifecycle_hours, best_window, weights_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pred_id,
                t["id"],
                now_iso,
                t["score_computed"],
                t["lifecycle_hours"],
                window_label,
                weights_json,
            ))
        except Exception:
            pass
    conn.commit()

    # Stats
    acc_pct, acc_count = get_accuracy_stats(conn)
    latest_weights, weights_updated = get_weight_stats(conn)

    kw_count = conn.execute("SELECT COUNT(*) FROM keyword_index WHERE niche=?", (config["niche"],)).fetchone()[0]

    # Tavily usage tracking
    tavily_used = conn.execute("""
        SELECT COUNT(*) FROM topics WHERE source_type='indirect'
        AND detected_at >= datetime('now', '-30 days')
    """).fetchone()[0]

    # Count distinct platforms actually seen in last 72h (real source health)
    sources_seen = conn.execute("""
        SELECT COUNT(DISTINCT platform) FROM topics
        WHERE detected_at >= datetime('now', '-72 hours')
    """).fetchone()[0]
    SOURCES_EXPECTED = 5  # hackernews, dev.to, producthunt, reddit, tavily(indirect)
    sources_ok = sources_seen >= SOURCES_EXPECTED

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.close()

    # ── BUILD REPORT ───────────────────────────────────────────────────────────
    SEP = "━" * 37

    if zh:
        header = f"{'🔥'} ViralEvo | {niche_label} | {now_str}"
        act_header = "🔴 立即发布（评分 > 80）"
        prep_header = "🟡 准备发布（评分 60–80）"
        ev_header = "🟢 长尾常青（评分 < 60）"
        acc_label = f"本周准确率   : {acc_pct}%（{acc_count}条预测）" if acc_pct else "本周准确率   : 数据积累中…"
        idx_label = f"关键词索引   : {kw_count} 个词条"
        src_label = f"数据源       : {sources_seen}/{SOURCES_EXPECTED} {'✅' if sources_ok else '⚠️'}"
        tav_label = f"Tavily用量   : 本月 {tavily_used} / 1,000"
        footer_note = '⚠️ 标注"间接"的信号通过Tavily搜索聚合获取。\n   置信度上限0.65–0.70，请作为方向性参考。'
    else:
        header = f"{'🔥'} ViralEvo | {niche_label} | {now_str}"
        act_header = "🔴 ACT NOW (Score > 80)"
        prep_header = "🟡 PREPARE (Score 60–80)"
        ev_header = "🟢 EVERGREEN (Score < 60)"
        acc_label = f"Accuracy     : {acc_pct}% ({acc_count} predictions)" if acc_pct else "Accuracy     : Accumulating data…"
        idx_label = f"Keyword index: {kw_count} terms"
        src_label = f"Sources      : {sources_seen}/{SOURCES_EXPECTED} {'✅' if sources_ok else '⚠️ some sources missing'}"
        tav_label = f"Tavily usage : {tavily_used} / 1,000 this month"
        footer_note = 'Signals marked "indirect" use Tavily search aggregation.\nConfidence capped at 0.65–0.70. Treat as directional guidance.'

    lines = [SEP, header, SEP, ""]

    def render_topics(items, priority):
        for i, t in enumerate(items, 1):
            conf_flag = " ⚠️ indirect" if t["source_type"] == "indirect" else ""
            bar = format_bar(t["score_computed"])
            win = round(t["window_remaining"])
            window_str = t["_window_label"]

            if zh:
                lines.append(f"{i}. {t['title']}")
                lines.append(f"   {bar} {t['score_computed']}% | 置信度: {t['confidence']:.2f}{conf_flag}")
                lines.append(f"   📅 {t['age_hours']:.0f}小时前检测 | 来源: {t['source']}")
                lines.append(f"   ⏰ 预计剩余窗口：约{win}小时")
                lines.append(f"   🎯 发布时机：{window_str}")
            else:
                lines.append(f"{i}. {t['title']}")
                lines.append(f"   {bar} {t['score_computed']}% | Confidence: {t['confidence']:.2f}{conf_flag}")
                lines.append(f"   📅 Detected {t['age_hours']:.0f}h ago | Source: {t['source']}")
                lines.append(f"   ⏰ Estimated window: ~{win}h remaining")
                lines.append(f"   🎯 Post: {window_str}")
            lines.append("")

    act   = [t for t in scored if t["score_computed"] > 80][:3]
    prep  = [t for t in scored if 60 < t["score_computed"] <= 80][:3]
    ev    = [t for t in scored if t["score_computed"] <= 60][:2]

    if act:
        lines.append(act_header)
        lines.append("─" * 33)
        render_topics(act, "act")

    if prep:
        lines.append(prep_header)
        lines.append("─" * 33)
        render_topics(prep, "prep")

    if ev:
        lines.append(ev_header)
        lines.append("─" * 33)
        render_topics(ev, "ev")

    lines += [SEP, "📊 Model Health" if not zh else "📊 模型状态"]
    lines += [f"  {acc_label}", f"  {src_label}", f"  {tav_label}", f"  {idx_label}"]
    lines += [SEP, footer_note]

    report = "\n".join(lines)
    print(report)

    # Save to reports/
    report_dir = BASE_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    rfile = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}_daily.md"
    rfile.write_text(report)


if __name__ == "__main__":
    main()
