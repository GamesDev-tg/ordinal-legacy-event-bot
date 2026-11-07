import unittest
import os
import random
import tempfile
import datetime
from app.config import settings
from app.database import get_db_connection, init_db
from app.bot import handle_bot_message, register_user_if_new
from app.game_engine import execute_community_gift, get_user_gift_status

def run_coro(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    except Exception as e:
        raise e

class TestGiftsAndTop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_gift_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = cls.test_db
        settings.ADMIN_IDS = [1257427765]
        settings.BOT_TOKEN = "mock_token"
        init_db()

    def setUp(self):
        self.user_a = 91001
        self.user_b = 91002
        self.user_c = 91003
        self.user_d = 91004
        self.user_e = 91005
        self.user_f = 91006
        self.user_g = 91007

        # Register all users
        register_user_if_new(self.user_a, "alice_tag", "Alice")
        register_user_if_new(self.user_b, "bob_tag", "Bob")
        register_user_if_new(self.user_c, "charlie_tag", "Charlie")
        register_user_if_new(self.user_d, "david_tag", "David")
        register_user_if_new(self.user_e, "eve_tag", "Eve")
        register_user_if_new(self.user_f, "frank_tag", "Frank")
        register_user_if_new(self.user_g, "grace_tag", "Grace")

        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 1")
        conn.execute("DELETE FROM user_community_gifts")
        conn.commit()
        conn.close()

    def test_top_and_tops_no_usernames(self):
        from app.cache import delete_cache
        delete_cache("bot_cmd_top")
        conn = get_db_connection()
        conn.execute("UPDATE users SET points_total = 999 WHERE telegram_id = ?", (self.user_a,))
        conn.commit()
        conn.close()

        # Test /top in group
        msg_top = {
            "chat": {"id": -10012345, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": "/top"
        }
        run_coro(handle_bot_message(msg_top))
        
        from app.cache import get_cache
        cached_top = get_cache("bot_cmd_top")
        self.assertIsNotNone(cached_top)
        # Must contain Alice and her ID
        self.assertIn("Alice", cached_top)
        self.assertIn(str(self.user_a), cached_top)
        # Must NOT contain @alice_tag (no tagging username)
        self.assertNotIn("@alice_tag", cached_top)

        # Test /tops alias
        from app.cache import delete_cache
        delete_cache("bot_cmd_top")
        msg_tops = {
            "chat": {"id": -10012345, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": "/tops"
        }
        run_coro(handle_bot_message(msg_tops))
        cached_tops = get_cache("bot_cmd_top")
        self.assertIsNotNone(cached_tops)
        self.assertNotIn("@alice_tag", cached_tops)
        self.assertIn("Alice", cached_tops)

    def test_gifts_group_restriction(self):
        # 1. Private DM should be rejected
        msg_dm = {
            "chat": {"id": self.user_a, "type": "private"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": f"/gifts {self.user_b}"
        }
        run_coro(handle_bot_message(msg_dm))

        # Check that no gift was recorded
        conn = get_db_connection()
        c = conn.execute("SELECT COUNT(*) as c FROM user_community_gifts").fetchone()["c"]
        self.assertEqual(c, 0)
        conn.close()

        # 2. Other group should be rejected
        msg_other = {
            "chat": {"id": -100999, "type": "supergroup", "username": "some_random_group", "title": "Random Group"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": f"/gifts {self.user_b}"
        }
        run_coro(handle_bot_message(msg_other))

        conn = get_db_connection()
        c = conn.execute("SELECT COUNT(*) as c FROM user_community_gifts").fetchone()["c"]
        self.assertEqual(c, 0)
        conn.close()

    def test_gifts_self_gift_blocked(self):
        res = execute_community_gift(self.user_a, str(self.user_a))
        self.assertFalse(res["success"])
        self.assertIn("cannot send a Diya gift to yourself", res["error"])

    def test_gifts_flow_cooldown_and_daily_limit(self):
        conn = get_db_connection()
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_b,))
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_c,))
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_d,))
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_e,))
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_f,))
        conn.execute("UPDATE users SET diya_wicks = 5 WHERE telegram_id = ?", (self.user_g,))
        conn.commit()
        conn.close()

        # 1. First gift: User A -> User B
        res1 = execute_community_gift(self.user_a, str(self.user_b))
        self.assertTrue(res1["success"])
        self.assertEqual(res1["receiver_wicks"], 6)
        self.assertEqual(res1["gifts_used_today"], 1)
        self.assertEqual(res1["gifts_remaining_today"], 4)

        # 2. Immediate 2nd gift to User C -> should fail due to 2-hour cooldown
        res_cd = execute_community_gift(self.user_a, str(self.user_c))
        self.assertFalse(res_cd["success"])
        self.assertIn("Gift Cooldown Active", res_cd["error"])

        # 3. Simulate passing 2 hours (advance timestamp of first gift)
        conn = get_db_connection()
        past_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2, minutes=5)).isoformat()
        conn.execute("UPDATE user_community_gifts SET created_at = ? WHERE sender_id = ?", (past_time, self.user_a))
        conn.commit()
        conn.close()

        # 4. Try gifting User B again on same day -> should fail (1 gift per recipient daily)
        res_same_user = execute_community_gift(self.user_a, str(self.user_b))
        self.assertFalse(res_same_user["success"])
        self.assertIn("already gifted", res_same_user["error"])

        # 5. Gift User C after cooldown -> succeeds!
        res2 = execute_community_gift(self.user_a, str(self.user_c))
        self.assertTrue(res2["success"])
        self.assertEqual(res2["gifts_used_today"], 2)

        # 6. Fast-forward cooldown for gifts 3, 4, 5
        conn = get_db_connection()
        conn.execute("UPDATE user_community_gifts SET created_at = ?", (past_time,))
        conn.commit()
        conn.close()

        res3 = execute_community_gift(self.user_a, str(self.user_d))
        self.assertTrue(res3["success"])

        conn = get_db_connection()
        conn.execute("UPDATE user_community_gifts SET created_at = ?", (past_time,))
        conn.commit()
        conn.close()

        res4 = execute_community_gift(self.user_a, str(self.user_e))
        self.assertTrue(res4["success"])

        conn = get_db_connection()
        conn.execute("UPDATE user_community_gifts SET created_at = ?", (past_time,))
        conn.commit()
        conn.close()

        res5 = execute_community_gift(self.user_a, str(self.user_f))
        self.assertTrue(res5["success"])
        self.assertEqual(res5["gifts_used_today"], 5)
        self.assertEqual(res5["gifts_remaining_today"], 0)

        # 7. 6th gift attempt -> blocked by 5 daily limit even if cooldown elapsed
        conn = get_db_connection()
        conn.execute("UPDATE user_community_gifts SET created_at = ?", (past_time,))
        conn.commit()
        conn.close()

        res6 = execute_community_gift(self.user_a, str(self.user_g))
        self.assertFalse(res6["success"])
        self.assertIn("Daily Limit Reached", res6["error"])

    def test_gifts_recipient_max_wicks_guard(self):
        conn = get_db_connection()
        conn.execute("UPDATE users SET diya_wicks = 10 WHERE telegram_id = ?", (self.user_b,))
        conn.commit()
        conn.close()

        res = execute_community_gift(self.user_a, str(self.user_b))
        self.assertFalse(res["success"])
        self.assertIn("maximum Diya Wicks", res["error"])

    def test_gifts_via_reply_message(self):
        conn = get_db_connection()
        conn.execute("UPDATE users SET diya_wicks = 3 WHERE telegram_id = ?", (self.user_b,))
        conn.commit()
        conn.close()

        # Simulate replying to user_b's message in @Ordinal_Legacy
        msg_reply = {
            "chat": {"id": -10012345, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "reply_to_message": {
                "message_id": 999,
                "from": {"id": self.user_b, "first_name": "Bob"}
            },
            "text": "/gifts"
        }
        run_coro(handle_bot_message(msg_reply))

        conn = get_db_connection()
        row = conn.execute("SELECT diya_wicks FROM users WHERE telegram_id = ?", (self.user_b,)).fetchone()
        self.assertEqual(row["diya_wicks"], 4)
        c = conn.execute("SELECT COUNT(*) as c FROM user_community_gifts WHERE sender_id = ? AND receiver_id = ?", (self.user_a, self.user_b)).fetchone()["c"]
        self.assertEqual(c, 1)
        conn.close()

if __name__ == "__main__":
    unittest.main()
