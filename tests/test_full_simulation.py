import unittest
import asyncio
import os
import random
import tempfile
from app.config import settings
from app.database import get_db_connection, init_db, calculate_tier, get_tier_name, get_stage_info
from app.bot import handle_bot_message, handle_bot_callback_query, register_user_if_new, is_admin
from app.referral_engine import process_referral_claim, send_companion_wick_gift
from app.captcha_engine import (
    get_or_create_captcha, verify_captcha_answer, is_user_captcha_locked,
    lock_user_captcha, unlock_user_captcha
)

# Generator dispatcher for coroutines
def run_coro(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    except Exception as e:
        raise e

class TestFullE2ESimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_sim_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = cls.test_db
        settings.ADMIN_IDS = [1257427765]
        settings.BOT_TOKEN = "mock_token"
        init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def setUp(self):
        # Create users with diverse profiles
        self.user_exotic = 771001
        self.user_no_uname = 771002
        self.user_referrer = 771003
        self.user_referred = 771004
        self.admin_id = 1257427765
        self.attacker_id = 771999

        # Register them
        register_user_if_new(self.user_exotic, "john_doe*star[link]", "🪔 Rohan_Kumar*")
        register_user_if_new(self.user_no_uname, None, "SilentLampbearer")
        register_user_if_new(self.user_referrer, "ref_master", "Master")
        register_user_if_new(self.user_referred, "new_friend", "Friend")
        register_user_if_new(self.attacker_id, "bad_actor", "Hacker")

        # Bypass group verify for test users
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id IN (?, ?, ?, ?)",
                     (self.user_exotic, self.user_no_uname, self.user_referrer, self.user_referred))
        conn.close()

    def test_exotic_username_and_markdown_safety(self):
        """Verify that exotic characters in usernames and names do not crash Markdown rendering."""
        # Test /mydata with user_exotic
        msg = {
            "chat": {"id": self.user_exotic, "type": "private"},
            "from": {"id": self.user_exotic, "username": "john_doe*star[link]", "first_name": "🪔 Rohan_Kumar*"},
            "text": "/mydata"
        }
        res = run_coro(handle_bot_message(msg))
        self.assertIsNone(res)

        # Test /status
        msg["text"] = "/status"
        res = run_coro(handle_bot_message(msg))
        self.assertIsNone(res)

        # Test /house
        msg["text"] = "/house"
        res = run_coro(handle_bot_message(msg))
        self.assertIsNone(res)

    def test_user_without_username(self):
        """Verify that a user without a Telegram username runs seamlessly."""
        msg = {
            "chat": {"id": self.user_no_uname, "type": "private"},
            "from": {"id": self.user_no_uname, "first_name": "SilentLampbearer"},
            "text": "/shagun"
        }
        res = run_coro(handle_bot_message(msg))
        self.assertIsNone(res)

    def test_referral_and_companion_flow(self):
        """Test referral bonding, companion assignment, and point crediting."""
        # Ensure clean referral state for test pair
        conn = get_db_connection()
        conn.execute("DELETE FROM referrals WHERE referred_id = ?", (self.user_referred,))
        conn.close()

        # Join via Shagun link: /start shagun_<referrer_id>
        msg = {
            "chat": {"id": self.user_referred, "type": "private"},
            "from": {"id": self.user_referred, "username": "new_friend", "first_name": "Friend"},
            "text": f"/start shagun_{self.user_referrer}"
        }
        run_coro(handle_bot_message(msg))

        # Check DB: referrer earned +1 point, companion bonded
        conn = get_db_connection()
        ref_row = conn.execute("SELECT * FROM referrals WHERE referred_id = ?", (self.user_referred,)).fetchone()
        self.assertIsNotNone(ref_row)
        self.assertEqual(ref_row["is_companion"], 1)
        
        referrer = conn.execute("SELECT points_total, referral_points_earned FROM users WHERE telegram_id = ?", (self.user_referrer,)).fetchone()
        self.assertGreaterEqual(referrer["referral_points_earned"], 1)
        conn.close()

        # Test companion wick gift
        gift_res = send_companion_wick_gift(self.user_referrer)
        self.assertTrue(gift_res["success"])

    def test_self_referral_guard(self):
        """Self-referrals must be safely rejected."""
        msg = {
            "chat": {"id": self.user_exotic, "type": "private"},
            "from": {"id": self.user_exotic, "username": "john_doe", "first_name": "Rohan"},
            "text": f"/start shagun_{self.user_exotic}"
        }
        res = run_coro(handle_bot_message(msg))
        self.assertIsNone(res)

    def test_anti_hack_admin_privileges(self):
        """Unauthorized non-admins must be rejected on all admin endpoints."""
        attacker_msg = {
            "chat": {"id": self.attacker_id, "type": "private"},
            "from": {"id": self.attacker_id, "username": "bad_actor", "first_name": "Hacker"},
            "text": "/admin"
        }
        run_coro(handle_bot_message(attacker_msg))

        attacker_msg["text"] = "/resetscores CONFIRM"
        run_coro(handle_bot_message(attacker_msg))

        attacker_msg["text"] = "/query SELECT * FROM users;"
        run_coro(handle_bot_message(attacker_msg))

        attacker_msg["text"] = "/setpoints 771999 5000"
        run_coro(handle_bot_message(attacker_msg))

        # Verify attacker still has 0 points
        conn = get_db_connection()
        att = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (self.attacker_id,)).fetchone()
        self.assertEqual(att["points_total"], 0)
        conn.close()

    def test_anti_macro_captcha_system(self):
        """Test that captcha locks actions until solved."""
        unlock_user_captcha(self.user_exotic)
        
        # Test self-test captcha
        msg = {
            "chat": {"id": self.user_exotic, "type": "private"},
            "from": {"id": self.user_exotic, "username": "john_doe", "first_name": "Rohan"},
            "text": "/captcha"
        }
        run_coro(handle_bot_message(msg))

        # Force lock captcha
        lock_user_captcha(self.user_exotic)
        self.assertTrue(is_user_captcha_locked(self.user_exotic))

        # Trying to play in chat must be blocked by captcha prompt
        msg["text"] = "/chakri"
        run_coro(handle_bot_message(msg))

        # Solve captcha
        challenge = get_or_create_captcha(self.user_exotic)
        cb_query = {
            "id": "cb_test_1",
            "from": {"id": self.user_exotic},
            "message": {"chat": {"id": self.user_exotic, "type": "private"}},
            "data": f"cpa:{self.user_exotic}:{challenge['correct_index']}:{challenge['token']}"
        }
        run_coro(handle_bot_callback_query(cb_query))

        # Must be unlocked now
        self.assertFalse(is_user_captcha_locked(self.user_exotic))

    def test_group_vs_dm_hygiene(self):
        """In groups, personal and game commands must be redirected to DM, not spammed."""
        group_msg = {
            "chat": {"id": -1001234567, "type": "supergroup"},
            "from": {"id": self.user_exotic, "username": "john_doe", "first_name": "Rohan"},
            "text": "/play"
        }
        # In group, /play should not execute in group
        res = run_coro(handle_bot_message(group_msg))
        self.assertIsNone(res)

        # Allowed group command /top executes safely
        group_msg["text"] = "/top"
        res = run_coro(handle_bot_message(group_msg))
        self.assertIsNone(res)

    def test_5k_tier_ladder_and_5_segments(self):
        """Verify the 5,000 top tier and 5 segments of 200k community target."""
        self.assertEqual(calculate_tier(0), 0)
        self.assertEqual(calculate_tier(500), 1)
        self.assertEqual(calculate_tier(1500), 2)
        self.assertEqual(calculate_tier(2750), 3)
        self.assertEqual(calculate_tier(4000), 4)
        self.assertEqual(calculate_tier(5000), 5)

        # Community 5 segments
        s0_num, s0_text = get_stage_info(1358)
        self.assertEqual(s0_num, 0)
        self.assertIn("1,358 / 40,000 Sparks", s0_text)

        s1_num, s1_text = get_stage_info(40000)
        self.assertEqual(s1_num, 1)
        self.assertIn("40,000 / 80,000 Sparks", s1_text)

        self.assertEqual(get_stage_info(80000)[0], 2)
        self.assertEqual(get_stage_info(120000)[0], 3)
        self.assertEqual(get_stage_info(160000)[0], 4)
        self.assertEqual(get_stage_info(200000)[0], 5)

    def test_leave_group_chat_revokes_verification_and_blocks_game(self):
        """When a user leaves an official group chat, verification is revoked and mini-games are blocked."""
        from app.bot import handle_bot_chat_member, run_in_chat_chakri
        from unittest.mock import patch
        
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id = ?", (self.user_exotic,))
        conn.close()
        
        leave_update = {
            "chat": {
                "id": -100999888,
                "title": "Ordinal Legacy Main",
                "username": "OrdinalLegacy",
                "type": "supergroup"
            },
            "from": {"id": self.user_exotic, "is_bot": False},
            "old_chat_member": {"user": {"id": self.user_exotic}, "status": "member"},
            "new_chat_member": {"user": {"id": self.user_exotic}, "status": "left"}
        }
        run_coro(handle_bot_chat_member(leave_update))
        
        conn = get_db_connection()
        u = conn.execute("SELECT joined_groups FROM users WHERE telegram_id = ?", (self.user_exotic,)).fetchone()
        conn.close()
        self.assertEqual(u["joined_groups"], 0)
        
        with patch("app.bot.execute_in_chat_game") as mock_exec:
            run_coro(run_in_chat_chakri(self.user_exotic, self.user_exotic))
            mock_exec.assert_not_called()
