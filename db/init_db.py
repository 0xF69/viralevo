"""
ViralEvo — Database Initializer
Column names match all scripts exactly. Safe to re-run.
"""
import sqlite3, os
from pathlib import Path

BASE_DIR = Path(os.environ.get('VIRALEVO_DATA_DIR',
    Path.home() / '.openclaw' / 'workspace' / 'viralevo'))
DB_PATH = BASE_DIR / 'data' / 'trends.db'

def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS topics (
        id           TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        source       TEXT NOT NULL,
        source_type  TEXT NOT NULL,
        platform     TEXT NOT NULL,
        url          TEXT,
        detected_at  TEXT NOT NULL,
        topic_type   TEXT,
        score        REAL DEFAULT 0,
        confidence   REAL DEFAULT 0.8,
        raw_signal   TEXT,
        niche        TEXT,
        language     TEXT DEFAULT 'en'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS predictions (
        id              TEXT PRIMARY KEY,
        topic_id        TEXT NOT NULL,
        predicted_at    TEXT NOT NULL,
        score           REAL NOT NULL,
        lifecycle_hours REAL NOT NULL,
        best_window     TEXT NOT NULL,
        weights_used    TEXT,
        FOREIGN KEY(topic_id) REFERENCES topics(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS verifications (
        id             TEXT PRIMARY KEY,
        prediction_id  TEXT NOT NULL,
        verified_at    TEXT NOT NULL,
        actual_active  INTEGER,
        error_pct      REAL,
        error_hours    REAL,
        accurate       INTEGER,
        source_data    TEXT,
        FOREIGN KEY(prediction_id) REFERENCES predictions(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS weight_history (
        id              TEXT PRIMARY KEY,
        updated_at      TEXT NOT NULL,
        weights         TEXT NOT NULL,
        reason          TEXT,
        accuracy_before REAL,
        rollback        INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS personal_feedback (
        id             TEXT PRIMARY KEY,
        topic_id       TEXT NOT NULL,
        submitted_at   TEXT NOT NULL,
        platform       TEXT,
        published_time TEXT,
        views          INTEGER,
        likes          INTEGER,
        saves          INTEGER,
        result         TEXT,
        raw_text       TEXT,
        FOREIGN KEY(topic_id) REFERENCES topics(id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS keyword_index (
        id       TEXT PRIMARY KEY,
        keyword  TEXT NOT NULL,
        niche    TEXT NOT NULL,
        source   TEXT NOT NULL,
        weight   REAL DEFAULT 1.0,
        added_at TEXT NOT NULL,
        UNIQUE(keyword, niche)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS system_config (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()
    print(f"[DB] Initialized: {DB_PATH}")

if __name__ == "__main__":
    init()
