#!/usr/bin/env node
/**
 * ViralEvo — Signal Collector
 * Fetches trend signals from all configured sources for the user's niche.
 * Run: node scripts/collect.js
 */

const axios = require("axios");
const fs = require("fs");
const path = require("path");
const { loadConfig, loadEnv, getDB, log } = require("./lib");

// Exponential backoff retry
async function fetchWithRetry(fn, retries = 3, delay = 1000) {
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i === retries - 1) throw e;
      const wait = delay * Math.pow(2, i);
      log(`Retry ${i + 1}/${retries - 1} after ${wait}ms: ${e.message}`);
      await new Promise(r => setTimeout(r, wait));
    }
  }
}

const BASE_DIR = process.env.VIRALEVO_DATA_DIR ||
  path.join(process.env.HOME, ".openclaw", "workspace", "viralevo");

async function fetchHackerNews(keywords) {
  log("Fetching HackerNews...");
  const results = [];
  for (const kw of keywords.slice(0, 3)) {
    try {
      const url = `https://hn.algolia.com/api/v1/search?query=${encodeURIComponent(kw)}&tags=story&hitsPerPage=5`;
      const res = await axios.get(url, { timeout: 8000 });
      for (const hit of res.data.hits || []) {
        results.push({
          id: `hn-${hit.objectID}`,
          title: hit.title,
          source: "hackernews",
          source_type: "direct",
          platform: "hackernews",
          url: hit.url || `https://news.ycombinator.com/item?id=${hit.objectID}`,
          detected_at: new Date().toISOString(),
          raw_signal: JSON.stringify({ points: hit.points, comments: hit.num_comments })
        });
      }
    } catch (e) {
      log(`HackerNews fetch error for "${kw}": ${e.message}`);
    }
  }
  return results;
}

async function fetchDevTo(keywords) {
  log("Fetching Dev.to...");
  const results = [];
  // Dev.to tag API only works with single slug-style words; extract single-word
  // candidates from the keyword list and try up to 3 distinct tags.
  const tagCandidates = keywords
    .map(kw => kw.toLowerCase().replace(/[^a-z0-9]/g, ""))
    .filter(t => t.length >= 3 && t.length <= 20)
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, 3);
  if (tagCandidates.length === 0) tagCandidates.push("programming");
  const seen = new Set();
  for (const tag of tagCandidates) {
    try {
      const url = `https://dev.to/api/articles?per_page=8&tag=${encodeURIComponent(tag)}`;
      const res = await axios.get(url, { timeout: 8000 });
      for (const article of res.data || []) {
        if (seen.has(article.id)) continue;
        seen.add(article.id);
        results.push({
          id: `devto-${article.id}`,
          title: article.title,
          source: "dev.to",
          source_type: "direct",
          platform: "dev.to",
          url: article.url,
          detected_at: new Date().toISOString(),
          raw_signal: JSON.stringify({ reactions: article.positive_reactions_count, comments: article.comments_count })
        });
      }
    } catch (e) {
      log(`Dev.to fetch error for tag "${tag}": ${e.message}`);
    }
  }
  return results;
}

async function fetchProductHunt() {
  log("Fetching Product Hunt RSS...");
  const results = [];
  try {
    const res = await axios.get("https://www.producthunt.com/feed", { timeout: 8000 });
    const items = (res.data.match(/<item>([\s\S]*?)<\/item>/g) || []).slice(0, 5);
    for (const item of items) {
      const title = (item.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/) || [])[1] || "";
      const link = (item.match(/<link>(.*?)<\/link>/) || [])[1] || "";
      if (title) {
        const crypto = require("crypto");
        const phId = crypto.createHash("md5").update(link || title).digest("hex").slice(0, 16);
        // Extract vote count from RSS if present (format varies; default to 50 as typical PH item)
        const votesMatch = item.match(/(\d+)\s*upvote/i) || item.match(/<votes>(\d+)<\/votes>/);
        const votes = votesMatch ? parseInt(votesMatch[1]) : 50;
        results.push({
          id: `ph-${phId}`,
          title,
          source: "producthunt",
          source_type: "direct",
          platform: "producthunt",
          topic_type: "tool_launch",
          url: link,
          detected_at: new Date().toISOString(),
          raw_signal: JSON.stringify({ points: votes, comments: 0 })
        });
      }
    }
  } catch (e) {
    log(`Product Hunt fetch error: ${e.message}`);
  }
  return results;
}

async function fetchReddit(subreddits) {
  log("Fetching Reddit...");
  const results = [];
  // Use all configured subreddits (capped at 5 to stay within rate limits)
  for (const sub of subreddits.slice(0, 5)) {
    try {
      const url = `https://www.reddit.com/r/${sub}/hot.json?limit=8`;
      const res = await axios.get(url, {
        timeout: 8000,
        headers: { "User-Agent": "Mozilla/5.0 (compatible; ViralEvo/0.6.3; +https://github.com/0xF69/viralevo)" }
      });
      for (const post of (res.data?.data?.children || [])) {
        const d = post.data;
        // Skip NSFW, stickied mod posts, and deleted posts
        if (d.over_18 || d.stickied || !d.title || d.removed_by_category) continue;
        results.push({
          id: `reddit-${d.id}`,
          title: d.title,
          source: `reddit/r/${sub}`,
          source_type: "direct",
          platform: "reddit",
          url: `https://reddit.com${d.permalink}`,
          detected_at: new Date().toISOString(),
          raw_signal: JSON.stringify({ score: d.score, comments: d.num_comments, upvote_ratio: d.upvote_ratio })
        });
      }
    } catch (e) {
      log(`Reddit r/${sub} fetch error: ${e.message}`);
    }
  }
  return results;
}

async function fetchTavily(queries, apiKey) {
  log("Fetching via Tavily (indirect platforms)...");
  const results = [];
  for (const q of queries) {
    try {
      const res = await axios.post("https://api.tavily.com/search", {
        api_key: apiKey,
        query: q.query,
        search_depth: "basic",
        max_results: 5
      }, { timeout: 12000 });
      for (const r of res.data.results || []) {
        results.push({
          id: `tavily-${require("crypto").createHash("md5").update(r.url).digest("hex").slice(0, 16)}`,
          title: r.title,
          source: `tavily:${q.platform}`,
          source_type: "indirect",
          platform: q.platform,
          url: r.url,
          detected_at: new Date().toISOString(),
          confidence: q.confidence_cap,
          raw_signal: JSON.stringify({ snippet: r.content?.slice(0, 200) })
        });
      }
    } catch (e) {
      log(`Tavily query error for "${q.query}": ${e.message}`);
    }
  }
  return results;
}

function buildTavilyQueries(config) {
  const niche  = config.niche_label || config.niche || "content creation";
  const region = config.region || "global";
  const zh     = (config.language || "en") === "zh";

  if (zh) {
    // Chinese-language queries produce far better results for CN/TW/HK audiences
    return [
      { query: `${niche} YouTube 热门视频 ${region} 本周`, platform: "youtube",   confidence_cap: 0.70 },
      { query: `${niche} 抖音 TikTok 爆款内容 本周`,       platform: "tiktok",    confidence_cap: 0.65 },
      { query: `${niche} 微博 微信 热搜话题 今天`,          platform: "twitter",   confidence_cap: 0.70 },
      { query: `${niche} 小红书 Instagram 热门内容 本周`,   platform: "instagram", confidence_cap: 0.65 },
    ];
  }
  return [
    { query: `${niche} trending YouTube ${region} this week`, platform: "youtube",   confidence_cap: 0.70 },
    { query: `${niche} viral TikTok trend this week`,          platform: "tiktok",    confidence_cap: 0.65 },
    { query: `${niche} trending Twitter discussion today`,     platform: "twitter",   confidence_cap: 0.70 },
    { query: `${niche} trending Instagram content this week`,  platform: "instagram", confidence_cap: 0.65 },
  ];
}

async function main() {
  loadEnv(BASE_DIR);

  const configPath = path.join(BASE_DIR, "config.json");
  if (!fs.existsSync(configPath)) {
    console.error("❌ ViralEvo is not configured. Run onboarding first:\n   node scripts/onboarding.js");
    process.exit(1);
  }

  const config = loadConfig(BASE_DIR);
  const tavilyKey = process.env.TAVILY_API_KEY;
  if (!tavilyKey) {
    console.error("❌ TAVILY_API_KEY not set. Add it to your .env file.");
    process.exit(1);
  }

  const db = getDB(BASE_DIR);
  const template = loadTemplate(config.niche);
  const keywords = template.keywords || [];
  const subreddits = template.subreddits || ["technology", "entrepreneur"];

  let allTopics = [];

  allTopics = allTopics.concat(await fetchHackerNews(keywords));
  allTopics = allTopics.concat(await fetchDevTo(keywords));
  allTopics = allTopics.concat(await fetchProductHunt());
  allTopics = allTopics.concat(await fetchReddit(subreddits));
  allTopics = allTopics.concat(await fetchTavily(buildTavilyQueries(config), tavilyKey));

  // Deduplicate by id, save to DB
  const stmt = db.prepare(`
    INSERT OR IGNORE INTO topics
      (id, title, source, source_type, platform, url, detected_at, topic_type, score, confidence, raw_signal, niche, language)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  let saved = 0;
  for (const t of allTopics) {
    if (!t.title) continue;
    try {
      stmt.run(
        t.id, t.title, t.source, t.source_type, t.platform,
        t.url || "", t.detected_at, t.topic_type || "general",
        t.score || 0, t.confidence || 0.8, t.raw_signal || "{}",
        config.niche, config.language || "en"
      );
      saved++;
    } catch (_) {}
  }

  log(`✅ Collected ${allTopics.length} signals, saved ${saved} new topics.`);
  db.close();
}

function loadTemplate(niche) {
  // __dirname = <skill_install_dir>/scripts → templates at <skill_install_dir>/templates
  const p = path.join(__dirname, "..", "templates", `${niche}.json`);
  try {
    if (fs.existsSync(p)) {
      const raw = fs.readFileSync(p, "utf8").trim();
      if (raw) return JSON.parse(raw);
    }
  } catch (e) {
    log(`Template load error for '${niche}': ${e.message}`);
  }
  log(`No template for niche '${niche}', using generic fallback.`);
  return { keywords: ["trending", "viral", "content"], subreddits: ["entrepreneur", "technology"] };
}

main().catch(e => { console.error("Collect failed:", e.message); process.exit(1); });
