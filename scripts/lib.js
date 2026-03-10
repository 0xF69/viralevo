/**
 * ViralEvo — Shared Node.js utilities
 */

const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");

const BASE_DIR = process.env.VIRALEVO_DATA_DIR ||
  path.join(process.env.HOME, ".openclaw", "workspace", "viralevo");

function loadEnv(baseDir) {
  const envPath = path.join(baseDir, ".env");
  const rootEnv = path.join(baseDir, "..", ".env");
  for (const p of [envPath, rootEnv]) {
    if (fs.existsSync(p)) {
      const lines = fs.readFileSync(p, "utf8").split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const eqIdx = trimmed.indexOf("=");
        if (eqIdx === -1) continue;
        const k = trimmed.slice(0, eqIdx).trim();
        if (!k || process.env[k]) continue;
        let val = trimmed.slice(eqIdx + 1).trim();
        // Strip surrounding quotes (single or double)
        if ((val.startsWith('"') && val.endsWith('"')) ||
            (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1);
        }
        process.env[k] = val;
      }
    }
  }
}

function loadConfig(baseDir) {
  const p = path.join(baseDir, "config.json");
  if (!fs.existsSync(p)) return {};
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

function saveConfig(baseDir, config) {
  const p = path.join(baseDir, "config.json");
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(config, null, 2));
}

function getDB(baseDir) {
  const dbPath = path.join(baseDir, "data", "trends.db");
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  // Init tables if not exist
  db.exec(`
    CREATE TABLE IF NOT EXISTS topics (
      id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
      source_type TEXT NOT NULL, platform TEXT NOT NULL, url TEXT,
      detected_at TEXT NOT NULL, topic_type TEXT, score REAL DEFAULT 0,
      confidence REAL DEFAULT 0.8, raw_signal TEXT, niche TEXT, language TEXT DEFAULT 'en'
    );
    CREATE TABLE IF NOT EXISTS predictions (
      id TEXT PRIMARY KEY, topic_id TEXT NOT NULL, predicted_at TEXT NOT NULL,
      score REAL NOT NULL, lifecycle_hours REAL NOT NULL, best_window TEXT NOT NULL,
      weights_used TEXT, FOREIGN KEY(topic_id) REFERENCES topics(id)
    );
    CREATE TABLE IF NOT EXISTS verifications (
      id TEXT PRIMARY KEY, prediction_id TEXT NOT NULL, verified_at TEXT NOT NULL,
      actual_active INTEGER, error_pct REAL, error_hours REAL, accurate INTEGER,
      source_data TEXT, FOREIGN KEY(prediction_id) REFERENCES predictions(id)
    );
    CREATE TABLE IF NOT EXISTS weight_history (
      id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, weights TEXT NOT NULL,
      reason TEXT, accuracy_before REAL, rollback INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS personal_feedback (
      id TEXT PRIMARY KEY, topic_id TEXT NOT NULL, submitted_at TEXT NOT NULL,
      platform TEXT, published_time TEXT, views INTEGER, likes INTEGER,
      saves INTEGER, result TEXT, raw_text TEXT,
      FOREIGN KEY(topic_id) REFERENCES topics(id)
    );
    CREATE TABLE IF NOT EXISTS keyword_index (
      id TEXT PRIMARY KEY, keyword TEXT NOT NULL, niche TEXT NOT NULL,
      source TEXT NOT NULL, weight REAL DEFAULT 1.0, added_at TEXT NOT NULL,
      UNIQUE(keyword, niche)
    );
    CREATE TABLE IF NOT EXISTS system_config (
      key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
    );
  `);
  return db;
}

function log(msg) {
  const ts = new Date().toISOString();
  const line = `[${ts}] ${msg}`;
  console.log(line);
  try {
    const logPath = path.join(BASE_DIR, "logs", "execution.log");
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, line + "\n");
  } catch (_) {}
}

module.exports = { loadEnv, loadConfig, saveConfig, getDB, log, BASE_DIR };
