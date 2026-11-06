import unittest
import sys
import os
from fastapi import HTTPException

import tempfile
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.database import get_db_connection, init_db, calculate_tier
from app.bot import register_user_if_new
from app.game_engine import start_game_session, finish_game_session, claim_shubh_refill

class TestGameEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_game_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = cls.test_db
        init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def setUp(self):
        import random
        self.user_id = random.randint(100000, 999999)
        register_user_if_new(self.user_id, f"user_{self.user_id}", "Tester")

    def test_stamina_and_session_start(self):
        res = start_game_session(self.user_id, game_type=1)
        self.assertIn("session_id", res)
        self.assertIn("nonce", res)
        self.assertEqual(res["wicks_remaining"], 9)

    def test_score_strictly_one_to_three(self):
        res_start = start_game_session(self.user_id, game_type=1)
        finish = finish_game_session(
            self.user_id,
            res_start["session_id"],
            res_start["nonce"],
            raw_score=3,
            duration_ms=13000
        )
        self.assertTrue(finish["success"])
        expected_score = 3 * finish.get("multiplier", 1)
        self.assertEqual(finish["points_awarded"], expected_score)
        self.assertEqual(finish["new_user_total"], expected_score)

        res_start2 = start_game_session(self.user_id, game_type=1)
        with self.assertRaises(HTTPException) as ctx:
            finish_game_session(
                self.user_id,
                res_start2["session_id"],
                res_start2["nonce"],
                raw_score=0,
                duration_ms=13000
            )
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            finish_game_session(
                self.user_id,
                res_start2["session_id"],
                res_start2["nonce"],
                raw_score=4,
                duration_ms=13000
            )
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            finish_game_session(
                self.user_id,
                res_start2["session_id"],
                res_start2["nonce"],
                raw_score=9,
                duration_ms=13000
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_duration_check_rejects_speed_runs(self):
        res_start = start_game_session(self.user_id, game_type=2)
        with self.assertRaises(HTTPException) as ctx:
            finish_game_session(
                self.user_id,
                res_start["session_id"],
                res_start["nonce"],
                raw_score=3,
                duration_ms=1000
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("too fast", ctx.exception.detail)

    def test_replay_attack_rejected(self):
        res_start = start_game_session(self.user_id, game_type=3)
        finish_game_session(
            self.user_id,
            res_start["session_id"],
            res_start["nonce"],
            raw_score=2,
            duration_ms=14000
        )
        with self.assertRaises(HTTPException) as ctx:
            finish_game_session(
                self.user_id,
                res_start["session_id"],
                res_start["nonce"],
                raw_score=2,
                duration_ms=14000
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Replay attack", ctx.exception.detail)

    def test_shubh_refill_success_and_duplicate_blocked(self):
        # Consume wicks first
        start_game_session(self.user_id, game_type=1) # 9 wicks
        start_game_session(self.user_id, game_type=1) # 8 wicks
        
        # First claim succeeds
        res = claim_shubh_refill(self.user_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["wicks_total"], 10)
        self.assertEqual(res["wicks_added"], 2)

        # Duplicate claim today must be blocked
        with self.assertRaises(HTTPException) as ctx:
            claim_shubh_refill(self.user_id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already claimed", ctx.exception.detail)

    def test_gharana_boost_rotation_and_multiplier(self):
        from app.game_engine import get_gharana_boost_status
        # Equal 10-minute rotation check:
        # Time 0: Gharana 1 (Surya)
        b0 = get_gharana_boost_status(0)
        self.assertEqual(b0["active_gharana_id"], 1)
        self.assertEqual(b0["seconds_remaining"], 600)
        self.assertEqual(b0["next_gharana_id"], 2)

        # Time 600: Gharana 2 (Agni)
        b1 = get_gharana_boost_status(600)
        self.assertEqual(b1["active_gharana_id"], 2)
        self.assertEqual(b1["next_gharana_id"], 3)

        # Time 1200: Gharana 3 (Chandra)
        b2 = get_gharana_boost_status(1200)
        self.assertEqual(b2["active_gharana_id"], 3)
        self.assertEqual(b2["next_gharana_id"], 4)

        # Time 1800: Gharana 4 (Vayu)
        b3 = get_gharana_boost_status(1800)
        self.assertEqual(b3["active_gharana_id"], 4)
        self.assertEqual(b3["next_gharana_id"], 1)

        # Time 2400: Repeats back to Gharana 1 (Surya)
        b4 = get_gharana_boost_status(2400)
        self.assertEqual(b4["active_gharana_id"], 1)

        # Verify 2X multiplier when user belongs to boosted gharana:
        active_gid = get_gharana_boost_status()["active_gharana_id"]
        conn = get_db_connection()
        conn.execute("UPDATE users SET gharana_id = ?, points_total = 0, diya_wicks = 10 WHERE telegram_id = ?", (active_gid, self.user_id))
        conn.commit()
        conn.close()

        sess = start_game_session(self.user_id, game_type=1)
        res_boosted = finish_game_session(self.user_id, sess["session_id"], sess["nonce"], raw_score=3, duration_ms=10000)
        self.assertTrue(res_boosted["is_boosted"])
        self.assertEqual(res_boosted["multiplier"], 2)
        self.assertEqual(res_boosted["points_awarded"], 6)
        self.assertEqual(res_boosted["new_user_total"], 6)

    def test_out_of_stamina_rejection(self):
        conn = get_db_connection()
        conn.execute("UPDATE users SET diya_wicks = 0 WHERE telegram_id = ?", (self.user_id,))
        conn.commit()
        conn.close()

        with self.assertRaises(HTTPException) as ctx:
            start_game_session(self.user_id, game_type=1)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Out of Diya Wicks", ctx.exception.detail)

if __name__ == "__main__":
    unittest.main()
