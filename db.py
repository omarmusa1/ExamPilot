import os
import sqlite3

DB_PATH = os.environ.get("EXAMAI_DB", os.path.join(os.path.dirname(__file__), "examai.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    ai_provider TEXT NOT NULL DEFAULT 'demo',
    api_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_text TEXT NOT NULL,
    generated_by TEXT NOT NULL DEFAULT 'demo',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    qtype TEXT NOT NULL DEFAULT 'mcq',
    scenario TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    option_a TEXT NOT NULL DEFAULT '',
    option_b TEXT NOT NULL DEFAULT '',
    option_c TEXT NOT NULL DEFAULT '',
    option_d TEXT NOT NULL DEFAULT '',
    correct TEXT NOT NULL DEFAULT 'A' CHECK (correct IN ('A', 'B', 'C', 'D')),
    model_answer TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score REAL NOT NULL,
    total INTEGER NOT NULL,
    mode TEXT NOT NULL DEFAULT 'full' CHECK (mode IN ('full', 'missed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    chosen TEXT,
    answer_text TEXT NOT NULL DEFAULT '',
    is_correct INTEGER NOT NULL,
    points REAL NOT NULL DEFAULT 0.0,
    feedback TEXT NOT NULL DEFAULT ''
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn, table, col_name, col_def):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col_name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # ترقية تلقائية لقاعدة البيانات القديمة لمنع أي إيرور عند التوليد
        _ensure_column(conn, "users", "ai_provider", "TEXT NOT NULL DEFAULT 'demo'")
        _ensure_column(conn, "users", "api_key", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "questions", "qtype", "TEXT NOT NULL DEFAULT 'mcq'")
        _ensure_column(conn, "questions", "scenario", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "questions", "model_answer", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "answers", "answer_text", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "answers", "points", "REAL NOT NULL DEFAULT 0.0")
        _ensure_column(conn, "answers", "feedback", "TEXT NOT NULL DEFAULT ''")
