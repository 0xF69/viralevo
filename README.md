# ViralEvo — Viral Content Trend Advisor

**Self-evolving trend prediction for content creators. Monitor 11 platforms. Get told exactly what to post and when. Watch the model improve every week.**

[Full technical documentation → SKILL.md]

---

## Quick Start

```bash
# 1. Install
clawhub install 0xF69/viralevo

# 2. Add your Tavily API key (free at tavily.com)
echo "TAVILY_API_KEY=tvly-xxxx" >> ~/.openclaw/workspace/.env

# 3. Run setup check
python3 ~/.openclaw/workspace/viralevo/setup.py

# 4. Start onboarding — tell your agent:
# "Start ViralEvo setup"
# — or in Chinese —
# "开始趋势雷达设置"
```

---

## Why ViralEvo

| | ViralEvo | Generic Trend Tools | Manual Scrolling |
|---|---|---|---|
| Catches trends before mainstream | ✅ 12–48h early | ❌ Lags | ❌ |
| Learns from your specific results | ✅ | ❌ | ❌ |
| Self-corrects weekly | ✅ | ❌ | ❌ |
| Transparent reasoning | ✅ Full evidence trail | ❌ Black box | ✅ |
| Chinese language support | ✅ | ❌ | ✅ |
| Cost | Free (Tavily free tier) | $29–$299/mo | Your time |

---

## Supported Niches

AI/Tech · E-commerce · Beauty · Fitness · Finance · Gaming · Fashion · Education · Real Estate · Pets · Custom

## Supported Platforms

HackerNews · Dev.to · Reddit · Product Hunt · YouTube · Twitter/X · TikTok · Instagram · Pinterest · LinkedIn

---

## Accuracy Timeline

| Period | Expected Accuracy |
|---|---|
| Week 1–2 | 30–40% (cold start) |
| Month 2 | 55–65% |
| Month 3+ | 65–75% |
| Month 6+ | 75%+ |

Accuracy = prediction within ±20% of actual topic lifecycle.

---

## Privacy

All collected data and prediction models are stored locally on your machine. No user data is ever transmitted externally. The skill makes outbound requests only to fetch public trend signals (HackerNews, Dev.to, Reddit, Product Hunt, Tavily). Tavily receives only search query strings.

---

## Requirements

- Node.js v18+
- Python 3.10+
- OpenClaw v2026.1+
- Tavily API key (free tier sufficient — [get one at tavily.com](https://tavily.com))

---

## License

MIT — see [LICENSE](LICENSE)

## Full Documentation

See [SKILL.md](SKILL.md) for complete technical documentation, scoring formula, disclaimers, and sample reports.
