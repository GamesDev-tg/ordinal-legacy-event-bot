import unittest
import sys
import os
import random
import tempfile
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.database import get_db_connection, init_db
from app.bot import handle_bot_message, handle_bot_callback_query, register_user_if_new
from app.routes.community_routes import api_community_state
from app.routes.game_routes import api_game_start, api_game_finish, api_shubh_refill
from app.routes.auth_routes import auth_demo
from app.models import GameStartRequest, GameFinishRequest

class TestBotAndAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_bot_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = cls.test_db
        settings.ADMIN_IDS = [999001]
        init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def setUp(self):
        self.user_id = random.randint(100000, 999999)
        register_user_if_new(self.user_id, f"testuser_{self.user_id}", "DiwaliHero")

    def test_auth_demo_endpoint(self):
        demo_id = random.randint(100000, 999999)
        resp = auth_demo(demo_id)
        self.assertTrue(resp.success)
        self.assertEqual(resp.user.telegram_id, demo_id)
        self.assertEqual(resp.target_sparks, 200000)

    def test_community_state_endpoint(self):
        resp = api_community_state()
        self.assertGreaterEqual(resp.target_sparks, 200000)
        self.assertEqual(len(resp.top_gharanas), 4)

    def test_game_full_flow_via_api(self):
        # 1. Start Game
        start_req = GameStartRequest(game_type=1)
        start_res = api_game_start(start_req, x_telegram_id=str(self.user_id))
        self.assertIsNotNone(start_res.session_id)
        self.assertIsNotNone(start_res.nonce)
        self.assertEqual(start_res.wicks_remaining, 9)

        # 2. Finish Game with 3 Points
        finish_req = GameFinishRequest(
            session_id=start_res.session_id,
            nonce=start_res.nonce,
            raw_score=3,
            duration_ms=13500
        )
        finish_res = api_game_finish(finish_req, x_telegram_id=str(self.user_id))
        self.assertTrue(finish_res.success)
        self.assertEqual(finish_res.points_awarded, 3)
        self.assertEqual(finish_res.new_user_total, 3)

        # 3. Shubh Refill
        refill_res = api_shubh_refill(x_telegram_id=str(self.user_id))
        self.assertTrue(refill_res.success)
        self.assertEqual(refill_res.wicks_total, 10)

    def test_bot_registration_and_status(self):
        new_uid = random.randint(100000, 999999)
        u = register_user_if_new(new_uid, "lord_ram", "Shri Ram")
        self.assertEqual(u["telegram_id"], new_uid)
        self.assertIn(u["gharana_id"], [1, 2, 3, 4])
        self.assertEqual(u["diya_wicks"], 10)
        self.assertEqual(u["points_total"], 0)

    def test_database_tier_and_stats_lookup(self):
        conn = get_db_connection()
        conn.execute("UPDATE users SET points_total = 400, tier_level = 3 WHERE telegram_id = ?", (self.user_id,))
        conn.commit()
        
        tier3_users = conn.execute("SELECT * FROM users WHERE tier_level = 3").fetchall()
        self.assertGreaterEqual(len(tier3_users), 1)

        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        self.assertGreaterEqual(total_users, 1)
        conn.close()

    def test_execute_in_chat_game_flow(self):
        from app.bot import execute_in_chat_game
        # Execute Chakri game (game_type 1)
        res = execute_in_chat_game(self.user_id, 1)
        self.assertTrue(res.get("success"))
        self.assertIn(res["score"], [1, 2, 3])
        self.assertEqual(res["new_wicks"], 9)
        self.assertGreaterEqual(res["community_total"], res["score"])

        # Execute Rangoli game (game_type 2)
        res2 = execute_in_chat_game(self.user_id, 2)
        self.assertTrue(res2.get("success"))
        self.assertEqual(res2["new_wicks"], 8)

        # Verify DB persisted
        conn = get_db_connection()
        u = conn.execute("SELECT points_total, diya_wicks FROM users WHERE telegram_id = ?", (self.user_id,)).fetchone()
        self.assertEqual(u["diya_wicks"], 8)
        self.assertEqual(u["points_total"], res2["new_pts"])
        conn.close()

if __name__ == "__main__":
    unittest.main()
