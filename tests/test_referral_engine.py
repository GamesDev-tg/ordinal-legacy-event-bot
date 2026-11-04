import unittest
import sys
import os
import random
from fastapi import HTTPException

import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.database import get_db_connection, init_db
from app.bot import register_user_if_new
from app.referral_engine import process_referral_claim, send_companion_wick_gift

class TestReferralEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_referral_{random.randint(10000, 99999)}.db")
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
        base = random.randint(100000, 900000)
        self.referrer = base + 1
        self.friend1 = base + 2
        self.friend2 = base + 3
        self.friend3 = base + 4
        
        register_user_if_new(self.referrer, "referrer_boss", "Boss")
        register_user_if_new(self.friend1, "friend_one", "Friend1")
        register_user_if_new(self.friend2, "friend_two", "Friend2")
        register_user_if_new(self.friend3, "friend_three", "Friend3")

    def test_self_referral_blocked(self):
        with self.assertRaises(HTTPException) as ctx:
            process_referral_claim(self.referrer, self.referrer)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("self-refer", ctx.exception.detail)

    def test_first_referral_is_companion(self):
        res1 = process_referral_claim(self.referrer, self.friend1)
        self.assertTrue(res1["success"])
        self.assertTrue(res1["is_companion"])
        self.assertEqual(res1["points_awarded_to_referrer"], 1)

        conn = get_db_connection()
        user = conn.execute("SELECT points_total, referral_points_earned FROM users WHERE telegram_id = ?", (self.referrer,)).fetchone()
        conn.close()
        self.assertEqual(user["points_total"], 1)
        self.assertEqual(user["referral_points_earned"], 1)

    def test_second_referral_is_standard(self):
        # First referral becomes companion
        res1 = process_referral_claim(self.referrer, self.friend1)
        self.assertTrue(res1["is_companion"])

        # Second referral must be standard (is_companion=False) and still award +1 point
        res2 = process_referral_claim(self.referrer, self.friend2)
        self.assertTrue(res2["success"])
        self.assertFalse(res2["is_companion"])
        self.assertEqual(res2["points_awarded_to_referrer"], 1)

        conn = get_db_connection()
        companions = conn.execute("SELECT * FROM referrals WHERE referrer_id = ? AND is_companion = 1", (self.referrer,)).fetchall()
        standards = conn.execute("SELECT * FROM referrals WHERE referrer_id = ? AND is_companion = 0", (self.referrer,)).fetchall()
        conn.close()
        self.assertEqual(len(companions), 1)
        self.assertEqual(companions[0]["referred_id"], self.friend1)
        self.assertEqual(len(standards), 1)
        self.assertEqual(standards[0]["referred_id"], self.friend2)

    def test_companion_wick_gift(self):
        # Bind companion first
        process_referral_claim(self.referrer, self.friend1)

        # Referrer can gift wick to Friend 1
        gift_res = send_companion_wick_gift(self.referrer)
        self.assertTrue(gift_res["success"])

        # Second gift on same day must be rejected
        with self.assertRaises(HTTPException) as ctx:
            send_companion_wick_gift(self.referrer)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already sent", ctx.exception.detail)

if __name__ == "__main__":
    unittest.main()
