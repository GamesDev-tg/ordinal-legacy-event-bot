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

_pg_pool = None

def get_pg_pool():
    global _pg_pool
    if _pg_pool is None or getattr(_pg_pool, "closed", True):
        import psycopg2.pool
        db_url = settings.DATABASE_PATH
        kwargs = {}
        if "sslmode" not in db_url and ("supabase.co" in db_url or "pooler.supabase.com" in db_url):
            kwargs["sslmode"] = "require"
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, db_url, **kwargs)
    return _pg_pool

class PostgresConnectionWrapper:
    def __init__(self, raw_conn, from_pool: bool = False):
        self._conn = raw_conn
        self._from_pool = from_pool

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
        try:
            if not getattr(self._conn, "autocommit", False):
                self._conn.commit()
        except Exception:
            pass

    def rollback(self):
        try:
            if not getattr(self._conn, "autocommit", False):
                self._conn.rollback()
        except Exception:
            pass

    def close(self):
        if self._from_pool:
            try:
                pool = get_pg_pool()
                if pool and not getattr(pool, "closed", True):
                    pool.putconn(self._conn)
                    return
            except Exception:
                pass
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()

def get_db_connection():
    if is_postgres():
        import psycopg2
        import psycopg2.extras
        db_url = settings.DATABASE_PATH
        try:
            pool = get_pg_pool()
            raw_conn = pool.getconn()
            # If connection was dropped by server, reset or fetch fresh
            if getattr(raw_conn, "closed", 0) != 0:
                raw_conn = pool.getconn()
            raw_conn.autocommit = True
            return PostgresConnectionWrapper(raw_conn, from_pool=True)
        except Exception:
            # Fallback to direct connection if pool is busy
            kwargs = {}
            if "sslmode" not in db_url and ("supabase.co" in db_url or "pooler.supabase.com" in db_url):
                kwargs["sslmode"] = "require"
            raw_conn = psycopg2.connect(db_url, **kwargs)
            raw_conn.autocommit = True
            return PostgresConnectionWrapper(raw_conn, from_pool=False)
    else:
        conn = sqlite3.connect(settings.DATABASE_PATH, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = -8000;")
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
            joined_groups INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE users ADD COLUMN IF NOT EXISTS shubh_refill_date TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS joined_groups INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS wick_cooldown_seconds INTEGER DEFAULT 120;
        ALTER TABLE game_sessions ADD COLUMN IF NOT EXISTS bonus_multiplier INTEGER DEFAULT 1;

        CREATE INDEX IF NOT EXISTS idx_users_points ON users (points_total DESC);
        CREATE INDEX IF NOT EXISTS idx_users_tier ON users (tier_level);
        CREATE INDEX IF NOT EXISTS idx_users_gharana ON users (gharana_id);
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals (referrer_id);
        CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals (referred_id);
        CREATE INDEX IF NOT EXISTS idx_game_sessions_tgid ON game_sessions (telegram_id);
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
            joined_groups INTEGER DEFAULT 0,
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

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        try:
            conn.execute("ALTER TABLE users ADD COLUMN joined_groups INTEGER DEFAULT 0;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN wick_cooldown_seconds INTEGER DEFAULT 120;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE game_sessions ADD COLUMN bonus_multiplier INTEGER DEFAULT 1;")
        except Exception:
            pass
    conn.close()

def init_db():
    if is_postgres():
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'users' LIMIT 1")
            if cur.fetchone():
                conn.close()
                return
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
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

def get_tier_reward(tier: int) -> str:
    return settings.TIER_REWARDS.get(tier, "Welcome Badge")

def get_stage_info(sparks: int) -> tuple[int, str]:
    if sparks >= 200000:
        return 5, f"Stage 5: Maha Akhand Jyoti Fully Ignited! ({sparks:,} Sparks • All Milestones Cleared!)"
    elif sparks >= 160000:
        return 4, f"Stage 4: Grand Deepotsav ({sparks:,} / 200,000 Sparks to Ignite 🪔 Maha Akhand Jyoti)"
    elif sparks >= 120000:
        return 3, f"Stage 3: Celestial Harmony ({sparks:,} / 160,000 Sparks to Clear 🐾 Pets)"
    elif sparks >= 80000:
        return 2, f"Stage 2: Sacred Radiance ({sparks:,} / 120,000 Sparks to Clear 🎟 Tickets)"
    elif sparks >= 40000:
        return 1, f"Stage 1: The First Glow ({sparks:,} / 80,000 Sparks to Clear 🔮 Pearls)"
    return 0, f"Stage 0: Lighting the Wick ({sparks:,} / 40,000 Sparks to Clear 🪙 Coins)"

def generate_full_backup() -> dict:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        # 1. Users
        cur.execute("SELECT * FROM users ORDER BY id ASC")
        users = [dict(r) for r in cur.fetchall()]
        
        # 2. Referrals
        cur.execute("SELECT * FROM referrals ORDER BY id ASC")
        referrals = [dict(r) for r in cur.fetchall()]
        
        # 3. Community state
        cur.execute("SELECT * FROM community_state")
        community = [dict(r) for r in cur.fetchall()]
        
        # 4. Game sessions
        cur.execute("SELECT * FROM game_sessions ORDER BY created_at DESC")
        game_sessions = [dict(r) for r in cur.fetchall()]
        
        # 5. Partner gifts
        cur.execute("SELECT * FROM partner_wick_gifts ORDER BY id ASC")
        gifts = [dict(r) for r in cur.fetchall()]
        
        return {
            "backup_version": "1.0",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_users": len(users),
            "total_referrals": len(referrals),
            "total_games": len(game_sessions),
            "community_sparks": community[0]["total_sparks"] if community else 0,
            "data": {
                "users": users,
                "referrals": referrals,
                "community_state": community,
                "game_sessions": game_sessions,
                "partner_wick_gifts": gifts
            }
        }
    finally:
        conn.close()

def reset_event_data() -> dict:
    conn = get_db_connection()
    with conn:
        conn.execute('''
            UPDATE users 
            SET points_total = 0, 
                tier_level = 0, 
                diya_wicks = 10, 
                referral_points_earned = 0, 
                shubh_refill_date = NULL
        ''')
        conn.execute("UPDATE community_state SET total_sparks = 0, current_stage = 0 WHERE id = 1")
        conn.execute("DELETE FROM game_sessions")
        conn.execute("DELETE FROM partner_wick_gifts")
    conn.close()
    return {"success": True, "message": "Event data reset successfully."}

def reset_scores_keep_users() -> dict:
    conn = get_db_connection()
    with conn:
        conn.execute('''
            UPDATE users 
            SET points_total = 0, 
                tier_level = 0, 
                diya_wicks = 10, 
                referral_points_earned = 0, 
                shubh_refill_date = NULL
        ''')
        conn.execute("UPDATE community_state SET total_sparks = 0, current_stage = 0 WHERE id = 1")
        conn.execute("DELETE FROM game_sessions")
        conn.execute("DELETE FROM partner_wick_gifts")
        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        ref_count = conn.execute("SELECT COUNT(*) as c FROM referrals").fetchone()["c"]
    conn.close()
    return {
        "success": True,
        "users_preserved": user_count,
        "referrals_preserved": ref_count,
        "message": f"Scores reset to 0 and wicks refilled to 10. All {user_count} players and {ref_count} referrals preserved!"
    }

def refill_all_users_wicks() -> dict:
    conn = get_db_connection()
    with conn:
        conn.execute("UPDATE users SET diya_wicks = ?", (settings.STAMINA_BANK_CAP,))
        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    conn.close()
    return {"success": True, "users_refilled": user_count}

def reset_all_shubh_refills() -> dict:
    conn = get_db_connection()
    with conn:
        conn.execute("UPDATE users SET shubh_refill_date = NULL")
        user_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    conn.close()
    return {"success": True, "users_reset": user_count}

def get_system_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    from app.cache import get_cache, set_cache
    cached = get_cache(f"setting_{key}")
    if cached is not None:
        return cached

    conn = get_db_connection()
    try:
        row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
        val = row["value"] if row else default
        if val is not None:
            # Use short TTL for critical operational settings (paused, chat IDs)
            critical_keys = ("event_paused", "logs_chat_id", "backup_chat_id", "extra_admin_ids")
            ttl = 10.0 if any(k in key for k in critical_keys) else 60.0
            set_cache(f"setting_{key}", val, ttl_seconds=ttl)
        return val
    except Exception:
        return default
    finally:
        conn.close()

def set_system_setting(key: str, value: str):
    from app.cache import delete_cache
    conn = get_db_connection()
    try:
        with conn:
            existing = conn.execute("SELECT key FROM system_settings WHERE key = ?", (key,)).fetchone()
            if existing:
                conn.execute("UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?", (value, key))
            else:
                conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, value))
        delete_cache(f"setting_{key}")
        delete_cache("all_admin_ids")
    finally:
        conn.close()

def is_event_paused() -> bool:
    """Returns True if the event has been paused/frozen by an administrator."""
    val = get_system_setting("event_paused", "0")
    return val in ("1", "true", "yes", "paused")

def set_event_paused(paused: bool):
    """Pauses or resumes the event games."""
    set_system_setting("event_paused", "1" if paused else "0")

def get_effective_logs_chat_id() -> Optional[int]:
    val = get_system_setting("logs_chat_id", settings.LOGS_CHAT_ID)
    if val and (val.lstrip("-").isdigit()):
        return int(val)
    return None

def get_effective_backup_chat_id() -> Optional[int]:
    val = get_system_setting("backup_chat_id", settings.BACKUP_CHAT_ID)
    if val and (val.lstrip("-").isdigit()):
        return int(val)
    return None

def get_all_admin_ids() -> List[int]:
    from app.cache import get_cache, set_cache
    cached = get_cache("all_admin_ids")
    if cached is not None:
        return cached

    base_admins = set(settings.ADMIN_IDS)
    extra_str = get_system_setting("extra_admin_ids", "")
    if extra_str:
        for x in extra_str.split(","):
            x = x.strip()
            if x.isdigit():
                base_admins.add(int(x))
    res = sorted(list(base_admins))
    set_cache("all_admin_ids", res, ttl_seconds=60.0)
    return res

def add_admin_id(new_admin_id: int) -> bool:
    from app.cache import delete_cache
    current = get_all_admin_ids()
    if new_admin_id in current:
        return False
    current.append(new_admin_id)
    extras = [str(i) for i in current if i not in settings.ADMIN_IDS]
    set_system_setting("extra_admin_ids", ",".join(extras))
    delete_cache("all_admin_ids")
    return True

def remove_admin_id(admin_id: int) -> bool:
    from app.cache import delete_cache
    if admin_id in settings.ADMIN_IDS:
        return False
    current = get_all_admin_ids()
    if admin_id in current:
        current.remove(admin_id)
        extras = [str(i) for i in current if i not in settings.ADMIN_IDS]
        set_system_setting("extra_admin_ids", ",".join(extras))
        delete_cache("all_admin_ids")
        return True
    return False

def restore_from_backup_data(backup_data: dict) -> dict:
    import secrets
    data = backup_data.get("data", backup_data)
    users = data.get("users", [])
    comm = data.get("community_state", [])
    referrals = data.get("referrals", [])
    game_sessions = data.get("game_sessions", [])

    conn = get_db_connection()
    users_restored = 0
    refs_restored = 0
    games_restored = 0
    with conn:
        if comm and len(comm) > 0:
            c = comm[0]
            conn.execute(
                "UPDATE community_state SET total_sparks = ?, target_sparks = ?, current_stage = ? WHERE id = 1",
                (c.get("total_sparks", 0), c.get("target_sparks", settings.GLOBAL_MILESTONE_TARGET), c.get("current_stage", 0))
            )

        for u in users:
            tid = u.get("telegram_id")
            if not tid:
                continue
            existing = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tid,)).fetchone()
            if existing:
                conn.execute(
                    '''UPDATE users SET username = ?, first_name = ?, gharana_id = ?, points_total = ?,
                       diya_wicks = ?, tier_level = ?, referral_points_earned = ?, shubh_refill_date = ?,
                       joined_groups = ? WHERE telegram_id = ?''',
                    (
                        u.get("username"), u.get("first_name"), u.get("gharana_id", 1),
                        u.get("points_total", 0), u.get("diya_wicks", 10), u.get("tier_level", 0),
                        u.get("referral_points_earned", 0), u.get("shubh_refill_date"),
                        u.get("joined_groups", 0), tid
                    )
                )
            else:
                conn.execute(
                    '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total,
                       diya_wicks, tier_level, referral_points_earned, shubh_refill_date, joined_groups)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        tid, u.get("username"), u.get("first_name"), u.get("gharana_id", 1),
                        u.get("points_total", 0), u.get("diya_wicks", 10), u.get("tier_level", 0),
                        u.get("referral_points_earned", 0), u.get("shubh_refill_date"),
                        u.get("joined_groups", 0)
                    )
                )
            users_restored += 1

        for r in referrals:
            r_id = r.get("referrer_id")
            ref_id = r.get("referred_id")
            if r_id and ref_id and r_id != ref_id:
                try:
                    conn.execute(
                        '''INSERT INTO referrals (referrer_id, referred_id, is_companion, bonus_awarded)
                           VALUES (?, ?, ?, ?)''',
                        (r_id, ref_id, r.get("is_companion", 0), r.get("bonus_awarded", 0))
                    )
                    refs_restored += 1
                except Exception:
                    pass

        for g in game_sessions:
            gid = g.get("id")
            if gid:
                try:
                    conn.execute(
                        '''INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, duration_ms, is_valid)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (gid, g.get("telegram_id"), g.get("game_type", 1), g.get("seed", "restored"),
                         g.get("nonce", secrets.token_hex(8)), g.get("score_awarded", 1),
                         g.get("duration_ms", 15000), g.get("is_valid", 1))
                    )
                    games_restored += 1
                except Exception:
                    pass

    conn.close()
    return {
        "success": True,
        "users_restored": users_restored,
        "referrals_restored": refs_restored,
        "games_restored": games_restored
    }

def purge_dummy_data() -> dict:
    conn = get_db_connection()
    with conn:
        # Delete specific non-real test IDs
        conn.execute("DELETE FROM users WHERE telegram_id IN (99998888, 999888777, 1087968824)")
        conn.execute("DELETE FROM game_sessions WHERE telegram_id IN (99998888, 999888777, 1087968824)")
        conn.execute("DELETE FROM referrals WHERE referrer_id IN (99998888, 999888777, 1087968824) OR referred_id IN (99998888, 999888777, 1087968824)")

        # Keep real admin (1257427765) and genuine Telegram users
        conn.execute('''
            DELETE FROM users 
            WHERE telegram_id NOT IN (1257427765, 6621196996) 
              AND (
                  username LIKE 'test_%' 
                  OR username LIKE 'target_%' 
                  OR username LIKE 'dev_%' 
                  OR username LIKE 'mock_%'
                  OR first_name LIKE 'Target%' 
                  OR first_name LIKE 'Test%' 
                  OR first_name LIKE 'DiwaliPlayer_%'
                  OR telegram_id < 10000000
              )
        ''')
        # Clean referrals that point to deleted users
        conn.execute('''
            DELETE FROM referrals 
            WHERE referrer_id NOT IN (SELECT telegram_id FROM users) 
               OR referred_id NOT IN (SELECT telegram_id FROM users)
        ''')
        # Clean game sessions of deleted users
        conn.execute('''
            DELETE FROM game_sessions 
            WHERE telegram_id NOT IN (SELECT telegram_id FROM users)
        ''')
        # Recalculate community sparks from remaining valid user scores
        row = conn.execute("SELECT COALESCE(SUM(points_total), 0) as s FROM users").fetchone()
        valid_sparks = row["s"] if row else 0
        from app.database import get_stage_info
        stage, _ = get_stage_info(valid_sparks)
        conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (valid_sparks, stage))
        users_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    conn.close()
    return {"success": True, "remaining_users": users_count, "sparks": valid_sparks}
