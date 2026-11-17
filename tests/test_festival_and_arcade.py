import unittest
from app.festival_engine import get_active_festival, set_active_festival, get_festival_config, render_welcome_for_current_festival, render_festival_switch_menu
from app.arcade_engine import play_dice_vs_ai, play_rps_vs_ai, play_coin_vs_ai, create_pvp_dice_challenge, accept_pvp_dice_challenge
from app.database import get_db_connection, init_db

class TestFestivalAndArcade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Create a test user
        self.test_uid = 99887766
        self.test_opp_uid = 99887755
        conn = get_db_connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks) VALUES (?, ?, ?, ?, ?, ?)",
                (self.test_uid, "test_hero", "TestHero", 1, 100, 10)
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks) VALUES (?, ?, ?, ?, ?, ?)",
                (self.test_opp_uid, "test_rival", "TestRival", 2, 50, 10)
            )
        conn.close()

    def test_festival_theme_switching(self):
        # 1. Switch to Arcade
        ok, msg = set_active_festival("arcade")
        self.assertTrue(ok)
        self.assertEqual(get_active_festival(), "arcade")
        cfg = get_festival_config()
        self.assertEqual(cfg["id"], "arcade")
        self.assertIn("Arcade Arena", cfg["name"])

        # 2. Switch to Diwali
        ok, msg = set_active_festival("diwali")
        self.assertTrue(ok)
        self.assertEqual(get_active_festival(), "diwali")
        cfg_d = get_festival_config()
        self.assertEqual(cfg_d["id"], "diwali")

        # 3. Switch to Christmas
        ok, msg = set_active_festival("christmas")
        self.assertTrue(ok)
        self.assertEqual(get_active_festival(), "christmas")
        cfg_c = get_festival_config()
        self.assertEqual(cfg_c["id"], "christmas")

        # 4. Invalid festival
        ok, msg = set_active_festival("invalid_halloween")
        self.assertFalse(ok)

        # Revert to arcade
        set_active_festival("arcade")

    def test_render_welcome_messages(self):
        dummy_user = {"telegram_id": self.test_uid, "points_total": 500, "diya_wicks": 8, "gharana_id": 1}
        
        # In arcade mode
        set_active_festival("arcade")
        text, kb = render_welcome_for_current_festival(dummy_user, "TestHero")
        self.assertIn("Arcade Arena", text)
        self.assertIn("Dice Duel", text)

        # In diwali mode
        set_active_festival("diwali")
        text, kb = render_welcome_for_current_festival(dummy_user, "TestHero")
        self.assertIn("Deepotsav", text)

        # In christmas mode
        set_active_festival("christmas")
        text, kb = render_welcome_for_current_festival(dummy_user, "TestHero")
        self.assertIn("Winter Wonderland", text)

        set_active_festival("arcade")

    def test_arcade_dice_pv_ai(self):
        res = play_dice_vs_ai(self.test_uid, "TestHero")
        self.assertTrue(res["success"])
        self.assertIn(res["outcome"], ["win", "tie", "loss"])
        self.assertIn("COSMIC DICE DUEL", res["message"])

    def test_arcade_rps_pv_ai(self):
        res = play_rps_vs_ai(self.test_uid, "TestHero", "fire")
        self.assertTrue(res["success"])
        self.assertIn(res["outcome"], ["win", "tie", "loss"])
        self.assertIn("ELEMENTAL CLASH", res["message"])

    def test_arcade_coin_pv_ai(self):
        res = play_coin_vs_ai(self.test_uid, "TestHero", "heads")
        self.assertTrue(res["success"])
        self.assertIn("SATOSHI COIN FLIP", res["message"])

    def test_arcade_pvp_duel(self):
        # 1. Create Challenge
        text, kb = create_pvp_dice_challenge(-100123456, self.test_uid, "TestHero")
        self.assertIn("ARCADE DICE DUEL CHALLENGE", text)
        duel_id = kb["inline_keyboard"][0][0]["callback_data"].split(":")[1]

        # 2. Cannot duel self
        res_self = accept_pvp_dice_challenge(duel_id, self.test_uid, "TestHero")
        self.assertFalse(res_self["success"])
        self.assertIn("cannot duel yourself", res_self["error"])

        # 3. Opponent accepts
        res = accept_pvp_dice_challenge(duel_id, self.test_opp_uid, "TestRival")
        self.assertTrue(res["success"])
        self.assertIn("DICE DUEL SHOWDOWN COMPLETE", res["message"])

        # 4. Cannot accept twice
        res_dup = accept_pvp_dice_challenge(duel_id, self.test_opp_uid, "TestRival")
        self.assertFalse(res_dup["success"])

if __name__ == "__main__":
    unittest.main()
