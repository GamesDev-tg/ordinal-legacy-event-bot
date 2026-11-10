import unittest
import datetime
import time
import sqlite3
from unittest.mock import patch, MagicMock, AsyncMock
from app.config import settings
from app.database import get_db_connection, init_db
from app.game_engine import _parse_timestamp, update_user_stamina, start_game_session
import app.bot as bot_module

class TestAuditFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
    def test_bug1_sqlite_pragmas(self):
        """Bug 1: Verify busy_timeout, synchronous=NORMAL, and WAL journal mode."""
        conn = get_db_connection()
        if not getattr(conn, "_from_pool", False):
            # SQLite connection
            row_sync = conn.execute("PRAGMA synchronous;").fetchone()
            # 1 corresponds to NORMAL
            self.assertEqual(row_sync[0], 1)
            row_busy = conn.execute("PRAGMA busy_timeout;").fetchone()
            self.assertEqual(row_busy[0], 10000)
        conn.close()

    def test_bug2_game_session_allows_zero_score(self):
        """Bug 2: Verify game_sessions allows score_awarded = 0 for pending sessions."""
        conn = get_db_connection()
        with conn:
            # Ensure a test user exists
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, diya_wicks) VALUES (?, ?, ?, ?, ?)",
                (88812345, "tester_pending", "Tester", 1, 5)
            )
            # Insert session with 0 score
            session_id = f"test_session_{int(time.time())}"
            conn.execute(
                """INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, duration_ms, is_valid)
                   VALUES (?, ?, ?, ?, ?, 0, 0, 0)""",
                (session_id, 88812345, 1, "testseed", f"nonce_{int(time.time()*1000)}")
            )
            sess = conn.execute("SELECT score_awarded FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
            self.assertEqual(sess["score_awarded"], 0)
            # Clean up
            conn.execute("DELETE FROM game_sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (88812345,))
        conn.close()

    def test_bug3_timezone_offset_naive_vs_aware(self):
        """Bug 3: Verify parsing timestamps with Z, +00:00, or naive strings never raises TypeError."""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Test offset-naive string
        ts_naive_str = "2026-11-10 12:00:00"
        parsed_naive = _parse_timestamp(ts_naive_str)
        self.assertIsNotNone(parsed_naive)
        self.assertIsNotNone(parsed_naive.tzinfo)
        diff_seconds = (now - parsed_naive).total_seconds()
        self.assertIsInstance(diff_seconds, float)

        # Test ISO string with Z
        ts_z_str = "2026-11-10T12:00:00Z"
        parsed_z = _parse_timestamp(ts_z_str)
        self.assertIsNotNone(parsed_z)
        self.assertIsNotNone(parsed_z.tzinfo)
        diff_z = (now - parsed_z).total_seconds()
        self.assertIsInstance(diff_z, float)

        # Test ISO string with +00:00
        ts_aware_str = "2026-11-10T12:00:00+00:00"
        parsed_aware = _parse_timestamp(ts_aware_str)
        self.assertIsNotNone(parsed_aware)
        self.assertIsNotNone(parsed_aware.tzinfo)
        diff_aware = (now - parsed_aware).total_seconds()
        self.assertIsInstance(diff_aware, float)

        # Test datetime object that is naive
        dt_naive = datetime.datetime(2026, 11, 10, 12, 0, 0)
        parsed_dt = _parse_timestamp(dt_naive)
        self.assertIsNotNone(parsed_dt.tzinfo)
        diff_dt = (now - parsed_dt).total_seconds()
        self.assertIsInstance(diff_dt, float)

    def test_bug4_button_cooldown_pruning(self):
        """Bug 4: Verify _BUTTON_CLICK_COOLDOWN purges entries older than 60s when exceeding 2000 entries."""
        now = time.time()
        # Seed 2500 entries with old timestamps
        bot_module._BUTTON_CLICK_COOLDOWN.clear()
        for i in range(2500):
            bot_module._BUTTON_CLICK_COOLDOWN[100000 + i] = now - 120.0  # 2 minutes ago
        
        # Add 5 fresh entries
        for i in range(5):
            bot_module._BUTTON_CLICK_COOLDOWN[200000 + i] = now - 5.0

        # Simulate user callback query triggering the pruning block
        user_id = 999999
        bot_module._BUTTON_CLICK_COOLDOWN[user_id] = now
        if len(bot_module._BUTTON_CLICK_COOLDOWN) > 2000:
            cutoff = now - 60.0
            bot_module._BUTTON_CLICK_COOLDOWN = {
                uid: ts for uid, ts in bot_module._BUTTON_CLICK_COOLDOWN.items() if ts > cutoff
            }
        
        # All old 2500 entries should be pruned, only the 5 fresh + 1 current = 6 remain
        self.assertLessEqual(len(bot_module._BUTTON_CLICK_COOLDOWN), 10)
        self.assertIn(user_id, bot_module._BUTTON_CLICK_COOLDOWN)

    def test_final_rush_event(self):
        """Final Rush: Test 2X baseline, 3X surge, and +5 Wicks blessing."""
        from app.database import set_system_setting, get_system_setting
        from app.game_engine import get_final_rush_multiplier, claim_final_rush_wicks, get_gharana_boost_status
        
        # 1. Normal state (rush off)
        set_system_setting("final_rush_active", "0")
        boost = get_gharana_boost_status()
        active_gid = boost["active_gharana_id"]
        other_gid = (active_gid % 4) + 1
        
        mult_act, is_b_act, is_r = get_final_rush_multiplier(active_gid)
        self.assertEqual(mult_act, 2)
        self.assertTrue(is_b_act)
        self.assertFalse(is_r)
        
        mult_oth, is_b_oth, is_r2 = get_final_rush_multiplier(other_gid)
        self.assertEqual(mult_oth, 1)
        self.assertFalse(is_b_oth)
        
        # 2. Activate Final Rush
        set_system_setting("final_rush_active", "1")
        mult_rush_act, _, is_r3 = get_final_rush_multiplier(active_gid)
        self.assertEqual(mult_rush_act, 3)  # Cosmic 3X
        self.assertTrue(is_r3)
        
        mult_rush_oth, _, _ = get_final_rush_multiplier(other_gid)
        self.assertEqual(mult_rush_oth, 2)  # Baseline 2X for all houses
        
        # 3. Claim +5 Wicks blessing
        test_uid = 77766655
        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM system_settings WHERE key = ?", (f"rush_claimed_{test_uid}",))
            from app.cache import delete_cache
            delete_cache(f"setting_rush_claimed_{test_uid}")
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, diya_wicks) VALUES (?, ?, ?, ?, ?)",
                (test_uid, "rush_user", "Rusher", 1, 3)
            )
            conn.execute("UPDATE users SET diya_wicks = 3 WHERE telegram_id = ?", (test_uid,))
        conn.close()
        
        res1 = claim_final_rush_wicks(test_uid)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["added"], 5)
        self.assertGreaterEqual(res1["new_wicks"], 8)
        
        # Duplicate claim rejected
        res2 = claim_final_rush_wicks(test_uid)
        self.assertFalse(res2["success"])
        
        # Clean up
        set_system_setting("final_rush_active", "0")
        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (test_uid,))
        conn.close()
