# Changelog

## v0.6.4 — 2026-03-10

### Bug Fixes
- **report.py**: Fixed `fromisoformat()` crash on Python 3.10 with `Z`-suffix ISO timestamps
- **report.py / onboarding.js / weekly_review.py**: Unified weight key to `cross_platform_spread` across all scripts; added auto-migration for old `cross_platform` key in existing config.json
- **setup.py**: Robust version detection — handles `Python 3.x`, `v18.x`, timeout, FileNotFoundError, and unknown formats
- **onboarding.js**: Fixed version display showing v0.6.1 instead of v0.6.4
- **collect.js / verify.py**: Updated User-Agent to reduce Reddit 403 rate limiting

### Improvements
- **collect.js**: Added exponential backoff retry (3 attempts) for all platform fetches
- **weekly_review.py**: Clear explanation when no data yet, instead of silent exit
- **scripts/status.py**: New quick health check — config, API key, DB stats, report age, weights sum
- **requirements.txt**: Tightened dependency version ranges

## v0.6.1 — 2026-03-09

### Initial Release
- Self-evolving viral content trend advisor for OpenClaw
- Monitors 11 platforms (HN, Dev.to, Product Hunt, Reddit, YouTube, Twitter, TikTok, Instagram, Pinterest, LinkedIn)
- Weekly self-evolution loop with automatic weight adjustment
- Bilingual support (English / 中文)
- 11 niche templates
