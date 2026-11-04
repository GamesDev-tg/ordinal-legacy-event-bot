import sqlite3
import datetime
from typing import Optional, Dict, Any, List
from app.config import settings

def is_postgres() -> bool:
    path = settings.DATABASE_PATH.lower()
    return path.startswith("postgresql://") or path.startswith("postgres://")

# PostgreSQL Wrapper Classes to provide an identical interface to sqlite3
class PostgresCursorWrapper:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params=None):
        if params is not None:
            # Adapt '?' to '%s' for psycopg2
            adapted_sql = sql.replace("?", "%s")
            self._cur.execute(adapted_sql, params)
        else:
            self._cur.execute(sql)
        return self

    def executemany(self, sql: str, seq_of_params):
        adapted_sql = sql.replace("?", "%s")
        self._cur.executemany(adapted_sql, seq_of_params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        if size is not None:
            return self._cur.fetchmany(size)
        return self._cur.fetchmany()

    @property
    def description(self):
        return self._cur.description

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()

class PostgresConnectionWrapper:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, script: str):
        cur = self._conn.cursor()
        cur.execute(script)
        cur.close()

    def cursor(self):
        import psycopg2.extras
        raw_cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(raw_cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()

def get_db_connection():
    if is_postgres():
        import psycopg2
        import psycopg2.extras
        db_url = settings.DATABASE_PATH
        # Ensure sslmode=require for cloud providers like Supabase if not specified
        if "sslmode" not in db_url and ("supabase.co" in db_url or "pooler.supabase.com" in db_url):
            raw_conn = psycopg2.connect(db_url, sslmode="require")
        else:
            raw_conn = psycopg2.connect(db_url)
        return PostgresConnectionWrapper(raw_conn)
    else:
        conn = sqlite3.connect(settings.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

def init_postgres_db():
    conn = get_db_connection()
    with conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            gharana_id INTEGER NOT NULL CHECK (gharana_id BETWEEN 1 AND 4),
            points_total INTEGER DEFAULT 0 CHECK (points_total >= 0),
            diya_wicks INTEGER DEFAULT 10 CHECK (diya_wicks BETWEEN 0 AND 10),
            last_wick_regen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tier_level INTEGER DEFAULT 0 CHECK (tier_level BETWEEN 0 AND 5),
            referral_points_earned INTEGER DEFAULT 0,
            shubh_refill_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            referred_id BIGINT UNIQUE NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            is_companion INTEGER DEFAULT 0 CHECK (is_companion IN (0, 1)),
            bonus_awarded INTEGER DEFAULT 0 CHECK (bonus_awarded IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (referrer_id != referred_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_single_companion 
        ON referrals(referrer_id) WHERE is_companion = 1;

        CREATE TABLE IF NOT EXISTS game_sessions (
            id TEXT PRIMARY KEY,
            telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            game_type INTEGER NOT NULL CHECK (game_type BETWEEN 1 AND 3),
            seed TEXT NOT NULL,
            nonce TEXT UNIQUE NOT NULL,
            score_awarded INTEGER DEFAULT 0 CHECK (score_awarded BETWEEN 0 AND 3),
            duration_ms INTEGER NOT NULL,
            is_valid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS community_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            total_sparks INTEGER DEFAULT 0,
            target_sparks INTEGER DEFAULT 200000,
            current_stage INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (id = 1)
        );

        CREATE TABLE IF NOT EXISTS partner_wick_gifts (
            id SERIAL PRIMARY KEY,
            sender_id BIGINT NOT NULL REFERENCES users(telegram_id),
            receiver_id BIGINT NOT NULL REFERENCES users(telegram_id),
            gift_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (sender_id, gift_date)
        );

        ALTER TABLE users ADD COLUMN IF NOT EXISTS shubh_refill_date TEXT;
        ''')
        
        row = conn.execute("SELECT COUNT(*) as count FROM community_state").fetchone()
        if row["count"] == 0:
            conn.execute(
                "INSERT INTO community_state (id, total_sparks, target_sparks, current_stage) VALUES (1, 0, ?, 0)",
                (settings.GLOBAL_MILESTONE_TARGET,)
            )
    conn.close()

def init_sqlite_db():
    conn = get_db_connection()
    with conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            gharana_id INTEGER NOT NULL CHECK (gharana_id BETWEEN 1 AND 4),
            points_total INTEGER DEFAULT 0 CHECK (points_total >= 0),
            diya_wicks INTEGER DEFAULT 10 CHECK (diya_wicks BETWEEN 0 AND 10),
            last_wick_regen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tier_level INTEGER DEFAULT 0 CHECK (tier_level BETWEEN 0 AND 5),
            referral_points_earned INTEGER DEFAULT 0,
            shubh_refill_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            referred_id INTEGER UNIQUE NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            is_companion INTEGER DEFAULT 0 CHECK (is_companion IN (0, 1)),
            bonus_awarded INTEGER DEFAULT 0 CHECK (bonus_awarded IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (referrer_id != referred_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_single_companion 
        ON referrals(referrer_id) WHERE is_companion = 1;

        CREATE TABLE IF NOT EXISTS game_sessions (
            id TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            game_type INTEGER NOT NULL CHECK (game_type BETWEEN 1 AND 3),
            seed TEXT NOT NULL,
            nonce TEXT UNIQUE NOT NULL,
            score_awarded INTEGER DEFAULT 0 CHECK (score_awarded BETWEEN 0 AND 3),
            duration_ms INTEGER NOT NULL,
            is_valid INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS community_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            total_sparks INTEGER DEFAULT 0,
            target_sparks INTEGER DEFAULT 200000,
            current_stage INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (id = 1)
        );

        CREATE TABLE IF NOT EXISTS partner_wick_gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL REFERENCES users(telegram_id),
            receiver_id INTEGER NOT NULL REFERENCES users(telegram_id),
            gift_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (sender_id, gift_date)
        );
        ''')
        
        row = conn.execute("SELECT COUNT(*) as count FROM community_state").fetchone()
        if row["count"] == 0:
            conn.execute(
                "INSERT INTO community_state (id, total_sparks, target_sparks, current_stage) VALUES (1, 0, ?, 0)",
                (settings.GLOBAL_MILESTONE_TARGET,)
            )

        # Ensure backward compatibility for existing SQLite databases
        try:
            conn.execute("ALTER TABLE users ADD COLUMN shubh_refill_date TEXT;")
        except Exception:
            pass
    conn.close()

def init_db():
    if is_postgres():
        init_postgres_db()
    else:
        init_sqlite_db()

def calculate_tier(points: int) -> int:
    for tier in [5, 4, 3, 2, 1]:
        if points >= settings.TIER_THRESHOLDS[tier]:
            return tier
    return 0

def get_tier_name(tier: int) -> str:
    names = {
        0: "Diya Spark",
        1: "Diya Sevak",
        2: "Rangoli Artisan",
        3: "Spark Master",
        4: "Deep Mahant",
        5: "Akhand Jyoti Sovereign"
    }
    return names.get(tier, "Diya Spark")

def get_stage_info(sparks: int) -> tuple[int, str]:
    if sparks >= 350000:
        return 5, "Stage 5: Ananta Utsav (Overdrive)"
    elif sparks >= 200000:
        return 4, "Stage 4: Maha Akhand Jyoti (Core Goal)"
    elif sparks >= 100000:
        return 3, "Stage 3: Deepotsav Halfway Illumination"
    elif sparks >= 50000:
        return 2, "Stage 2: Shubh Rangoli Radiance"
    elif sparks >= 25000:
        return 1, "Stage 1: Pratham Jyoti (The First Spark)"
    return 0, "Stage 0: Lighting the Wick"
