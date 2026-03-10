#!/usr/bin/env node
/**
 * ViralEvo — Onboarding
 * Interactive first-time setup. Run: node scripts/onboarding.js
 * Or tell your OpenClaw agent: "Start ViralEvo setup"
 */

const readline = require("readline");
const fs = require("fs");
const path = require("path");
const { loadEnv, saveConfig, getDB, log, BASE_DIR } = require("./lib");

loadEnv(BASE_DIR);

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise(res => rl.question(q, res));

const NICHES = {
  "1":  { id: "ai_tech",    label: "AI / Tech",           template: "ai_tech" },
  "2":  { id: "ecommerce",  label: "E-commerce",          template: "ecommerce" },
  "3":  { id: "beauty",     label: "Beauty / Skincare",   template: "beauty" },
  "4":  { id: "fitness",    label: "Fitness / Health",    template: "fitness" },
  "5":  { id: "finance",    label: "Finance",             template: "finance" },
  "6":  { id: "gaming",     label: "Gaming",              template: "gaming" },
  "7":  { id: "fashion",    label: "Fashion / Lifestyle", template: "fashion" },
  "8":  { id: "pets",       label: "Pets",                template: "pets" },
  "9":  { id: "realestate", label: "Real Estate",         template: "realestate" },
  "10": { id: "education",  label: "Education",           template: "education" },
  "11": { id: "custom",     label: "Custom",              template: "custom" },
};

const GOALS = {
  "1": "followers",
  "2": "sales",
  "3": "authority",
  "4": "views",
};

async function main() {
  console.log("\n🦞 Welcome to ViralEvo v0.6.4\n");
  console.log("I need to understand your content business.");
  console.log("This takes about 3 minutes. Everything can be changed later.\n");

  // Language
  const langRaw = await ask("Which language? [1] English  [2] 中文  > ");
  const zh = langRaw.trim() === "2";
  const lang = zh ? "zh" : "en";

  if (zh) {
    console.log("\n✅ 已选择中文模式。后续所有问题和报告将使用中文。\n");
  }

  // Niche
  if (zh) {
    console.log("你创作哪类内容？");
    Object.entries(NICHES).forEach(([k, v]) => console.log(`  [${k}] ${v.label}`));
  } else {
    console.log("What type of content do you create?");
    Object.entries(NICHES).forEach(([k, v]) => console.log(`  [${k}] ${v.label}`));
  }
  const nicheRaw = await ask(zh ? "请输入序号 > " : "Enter number > ");
  const niche = NICHES[nicheRaw.trim()] || NICHES["1"];

  // Platforms
  const platformsQ = zh
    ? "\n你在哪些平台发布内容？（用逗号分隔，例如 TikTok, YouTube, Twitter）\n> "
    : "\nWhich platforms do you publish on? (comma-separated, e.g. TikTok, YouTube, Twitter)\n> ";
  const platformsRaw = await ask(platformsQ);
  const platforms = platformsRaw.split(",").map(p => p.trim().toLowerCase()).filter(Boolean);

  // Region
  const regionQ = zh
    ? "\n你的主要受众在哪个地区？（例如：中国、美国、全球英文）\n> "
    : "\nWhere is your main audience located? (e.g. US, Global, Southeast Asia)\n> ";
  const region = (await ask(regionQ)).trim() || "Global";

  // Goal
  if (zh) {
    console.log("\n目前最重要的目标是什么？");
    console.log("  [1] 涨粉");
    console.log("  [2] 带货/转化");
    console.log("  [3] 建立行业权威");
    console.log("  [4] 最大化播放量/广告收入");
  } else {
    console.log("\nWhat matters most right now?");
    console.log("  [1] Grow followers");
    console.log("  [2] Drive sales / conversions");
    console.log("  [3] Build brand authority");
    console.log("  [4] Maximize views / ad revenue");
  }
  const goalRaw = await ask(zh ? "请输入序号 > " : "Enter number > ");
  const goal = GOALS[goalRaw.trim()] || "views";

  // Posting frequency
  const freqQ = zh
    ? "\n你通常多久发一次内容？（例如：每天、每周3次）\n> "
    : "\nHow often do you typically post? (e.g. daily, 3x per week)\n> ";
  const frequency = (await ask(freqQ)).trim() || "daily";

  // Report time
  const timeQ = zh
    ? "\n你希望每天几点收到趋势报告？（24小时格式，默认 08:00）\n> "
    : "\nWhat time should your daily report arrive? (24h format, default 08:00)\n> ";
  const reportTime = (await ask(timeQ)).trim() || "08:00";

  // Build config
  const config = {
    language: lang,
    niche: niche.id,
    niche_label: niche.label,
    niche_template: niche.template,
    platforms,
    region,
    goal,
    frequency,
    report_time: reportTime,
    weights: {
      platform_signal:     0.25,
      engagement_velocity: 0.25,
      cross_platform_spread: 0.20,
      niche_relevance:     0.15,
      goal_alignment:      0.15,
    },
    setup_at: new Date().toISOString(),
    version: "0.6.4",
  };

  // Show summary
  console.log("\n" + "─".repeat(40));
  if (zh) {
    console.log("✅ 配置确认如下，请检查：\n");
    console.log(`  语言         : 中文`);
    console.log(`  赛道         : ${niche.label}`);
    console.log(`  发布平台     : ${platforms.join(", ") || "未设置"}`);
    console.log(`  受众地区     : ${region}`);
    console.log(`  目标         : ${goal}`);
    console.log(`  发布频率     : ${frequency}`);
    console.log(`  报告时间     : 每天 ${reportTime}`);
    console.log(`  Tavily预计用量: ~4 次/天（固定4路搜索，约120次/月）`);
  } else {
    console.log("✅ Configuration summary — please review:\n");
    console.log(`  Language     : English`);
    console.log(`  Niche        : ${niche.label}`);
    console.log(`  Platforms    : ${platforms.join(", ") || "not set"}`);
    console.log(`  Region       : ${region}`);
    console.log(`  Goal         : ${goal}`);
    console.log(`  Frequency    : ${frequency}`);
    console.log(`  Report time  : Daily at ${reportTime}`);
    console.log(`  Tavily est.  : ~4 calls/day (fixed 4 queries, ~120/month)`);
  }
  console.log("─".repeat(40));

  const confirmQ = zh
    ? "\n确认此配置？ [yes / 修改] > "
    : "\nConfirm this configuration? [yes / change] > ";
  const confirm = await ask(confirmQ);

  if (!confirm.toLowerCase().startsWith("y") && confirm.toLowerCase() !== "yes") {
    console.log(zh ? "\n已取消。重新运行以修改设置。" : "\nCancelled. Run again to reconfigure.");
    rl.close();
    return;
  }

  // Save
  fs.mkdirSync(BASE_DIR, { recursive: true });
  saveConfig(BASE_DIR, config);

  // Init DB
  let db;
  try {
    db = getDB(BASE_DIR);
  } catch (e) {
    console.error("DB init error:", e.message);
  }

  // Seed keyword index from niche template
  if (db) {
    try {
      const templatePath = path.join(__dirname, "..", "templates", `${niche.template}.json`);
      if (fs.existsSync(templatePath)) {
        const tmpl = JSON.parse(fs.readFileSync(templatePath, "utf8"));
        const keywords = tmpl.keywords || [];
        const now = new Date().toISOString();
        const stmt = db.prepare(`
          INSERT OR IGNORE INTO keyword_index (id, keyword, niche, source, weight, added_at)
          VALUES (?, ?, ?, 'template', 1.0, ?)
        `);
        const insertMany = db.transaction((kws) => {
          for (const kw of kws) {
            stmt.run(require("crypto").randomUUID(), kw.toLowerCase(), niche.id, now);
          }
        });
        insertMany(keywords);
        console.log(zh
          ? `\n  ✅ 已加载 ${keywords.length} 个 ${niche.label} 赛道关键词`
          : `\n  ✅ Seeded ${keywords.length} keywords for ${niche.label} niche`
        );
      }
    } catch (e) {
      console.error("Keyword seed error:", e.message);
    }
    db.close();
  }

  if (zh) {
    console.log("\n✅ 配置已保存！");
    console.log("\n下一步：");
    console.log("  1. 运行数据采集：   node scripts/collect.js");
    console.log("  2. 生成今日报告：   python3 scripts/report.py");
    console.log("  或直接告诉你的 OpenClaw Agent：\"今天该发什么内容？\"");
  } else {
    console.log("\n✅ Configuration saved!");
    console.log("\nNext steps:");
    console.log("  1. Collect data:    node scripts/collect.js");
    console.log("  2. Generate report: python3 scripts/report.py");
    console.log("  Or tell your OpenClaw agent: \"What should I post today?\"");
  }

  rl.close();
  log("Onboarding completed. Niche: " + niche.id);
}

main().catch(e => { console.error("Onboarding error:", e.message); rl.close(); process.exit(1); });
