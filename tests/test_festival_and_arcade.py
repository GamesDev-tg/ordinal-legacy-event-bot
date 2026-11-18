import unittest
from app.festival_engine import get_active_festival, set_active_festival, get_festival_config, render_welcome_for_current_festival, render_festival_switch_menu
from app.arcade_engine import play_dice_vs_ai, play_rps_vs_ai, play_coin_vs_ai, create_pvp_dice_challenge, accept_pvp_dice_challenge
from app.database import get_db_connection, init_db

def run_coro_sync(coro):
    while True:
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value

class TestFestivalAndArcade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        from app.config import settings
        cls._orig_token = settings.BOT_TOKEN
        settings.BOT_TOKEN = "mock_bot_token_for_dev"

    @classmethod
    def tearDownClass(cls):
        from app.config import settings
        settings.BOT_TOKEN = cls._orig_token

    def setUp(self):
        # Create a test user
        self.test_uid = 99887766
        self.test_opp_uid = 99887755
        conn = get_db_connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, joined_groups) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (self.test_uid, "test_hero", "TestHero", 1, 100, 10)
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, joined_groups) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (self.test_opp_uid, "test_rival", "TestRival", 2, 50, 10)
            )
            conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id IN (?, ?)", (self.test_uid, self.test_opp_uid))
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

    def test_sync_telegram_bot_commands_themes(self):
        from app.bot import sync_telegram_bot_commands

        # Test in arcade mode
        set_active_festival("arcade")
        res = run_coro_sync(sync_telegram_bot_commands())
        self.assertTrue(res)

        # Test in diwali mode
        set_active_festival("diwali")
        res = run_coro_sync(sync_telegram_bot_commands())
        self.assertTrue(res)

        # Test in christmas mode
        set_active_festival("christmas")
        res = run_coro_sync(sync_telegram_bot_commands())
        self.assertTrue(res)

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

    def test_mini_app_festival_api_and_models(self):
        from app.main import api_get_current_festival
        from app.routes.auth_routes import auth_demo
        from app.routes.community_routes import api_community_state

        # 1. Check /api/festival/current in arcade mode
        set_active_festival("arcade")
        data = api_get_current_festival()
        self.assertTrue(data["ok"])
        self.assertEqual(data["active_theme"], "arcade")
        cfg = data["config"]
        self.assertEqual(cfg["header_title"], "ORDINAL ARCADE")
        self.assertEqual(cfg["stamina_name"], "Energy")
        self.assertEqual(cfg["theme_class"], "theme-arcade")
        self.assertEqual(cfg["featured_game_ids"][0], 4) # Ludo is first in arcade

        # 2. Check auth returns festival theme & config
        auth_data = auth_demo(self.test_uid)
        self.assertTrue(auth_data.success)
        self.assertEqual(auth_data.festival_theme, "arcade")
        self.assertEqual(auth_data.festival_config["id"], "arcade")

        # 3. Check community state returns festival theme & config
        comm_data = api_community_state()
        self.assertEqual(comm_data.festival_theme, "arcade")
        self.assertEqual(comm_data.festival_config["id"], "arcade")

        # 4. Switch to diwali and verify API reflects update
        set_active_festival("diwali")
        data_d = api_get_current_festival()
        self.assertEqual(data_d["active_theme"], "diwali")
        self.assertEqual(data_d["config"]["header_title"], "ORDINAL LEGACY")
        self.assertEqual(data_d["config"]["stamina_name"], "Diya Wicks")
        self.assertEqual(data_d["config"]["theme_class"], "theme-diwali")
        self.assertEqual(data_d["config"]["featured_game_ids"][0], 1) # Chakri is first in diwali

        # Revert back to arcade
        set_active_festival("arcade")

    def test_pure_arcade_bot_commands_separation(self):
        from app.bot import handle_bot_message
        from unittest.mock import patch, AsyncMock

        def run_coro(coro):
            try:
                while True:
                    sub = coro.send(None)
                    if hasattr(sub, "send"):
                        try:
                            run_coro(sub)
                        except Exception:
                            pass
            except StopIteration as e:
                return e.value

        sent_messages = []
        async def mock_send(chat_id, text, reply_markup=None):
            sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"message_id": 1234}

        # 1. ARCADE MODE VERIFICATION
        set_active_festival("arcade")

        with patch("app.bot.send_telegram_message", side_effect=mock_send):
            # Test /help in arcade mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/help"
            }))
            help_out = sent_messages[-1]["text"]
            self.assertIn("ORDINAL LEGACY ARCADE: COMMAND GUIDE", help_out)
            self.assertIn("/ludo", help_out)
            self.assertIn("/c4", help_out)
            self.assertIn("/2048", help_out)
            self.assertIn("/wordle", help_out)
            self.assertIn("/squad", help_out)
            self.assertIn("/refill", help_out)
            self.assertNotIn("Chakri", help_out)
            self.assertNotIn("Rangoli", help_out)
            self.assertNotIn("Mithai", help_out)
            self.assertNotIn("Akhand Jyoti", help_out)

            # Test /status in arcade mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/status"
            }))
            status_out = sent_messages[-1]["text"]
            self.assertIn("Arcade Power Core Status Report", status_out)
            self.assertIn("Energy Stamina", status_out)
            self.assertIn("Gaming Duo", status_out)
            self.assertIn("Squad Recruits", status_out)
            self.assertNotIn("Diya Wicks", status_out)
            self.assertNotIn("Diya Companion", status_out)
            self.assertNotIn("Shagun Points", status_out)

            # Test /tiers in arcade mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/tiers"
            }))
            tiers_out = sent_messages[-1]["text"]
            self.assertIn("Ordinal Legacy Arcade Milestone Ladder", tiers_out)
            self.assertIn("Arcade Rookie", tiers_out)
            self.assertIn("Pixel Warrior", tiers_out)
            self.assertIn("Combo Striker", tiers_out)
            self.assertIn("High Score Master", tiers_out)
            self.assertIn("Cyber Grandmaster", tiers_out)
            self.assertIn("Arcade Sovereign", tiers_out)
            self.assertNotIn("Diya Spark", tiers_out)
            self.assertNotIn("Rangoli Artisan", tiers_out)

            # Test /mydata in arcade mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/mydata"
            }))
            mydata_out = sent_messages[-1]["text"]
            self.assertIn("PLAYER ARCADE DOSSIER", mydata_out)
            self.assertIn("Affiliated Clan", mydata_out)
            self.assertIn("Energy Stamina", mydata_out)
            self.assertIn("Daily Booster", mydata_out)
            self.assertIn("Gaming Duo", mydata_out)
            self.assertIn("Squad Recruits", mydata_out)
            self.assertNotIn("Initiated House", mydata_out)
            self.assertNotIn("Diya Wicks", mydata_out)
            self.assertNotIn("Diya Companion", mydata_out)

            # Test /squad in arcade mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/squad"
            }))
            squad_out = sent_messages[-1]["text"]
            self.assertIn("Arcade Squad Invite Link", squad_out)
            self.assertIn(f"start=squad_{self.test_uid}", squad_out)
            self.assertIn("Gaming Duo", squad_out)

            # Test /start with squad_ referral parameter
            newbie_id = 99118822
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": newbie_id, "type": "private"},
                "from": {"id": newbie_id, "username": "arcade_recruit"},
                "text": f"/start squad_{self.test_uid}"
            }))
            self.assertTrue(len(sent_messages) > 0)
            conn = get_db_connection()
            ref_row = conn.execute("SELECT * FROM referrals WHERE referrer_id = ? AND referred_id = ?", (self.test_uid, newbie_id)).fetchone()
            conn.close()
            self.assertIsNotNone(ref_row)

        # 2. DIWALI MODE VERIFICATION
        set_active_festival("diwali")

        with patch("app.bot.send_telegram_message", side_effect=mock_send):
            # Test /help in diwali mode
            sent_messages.clear()
            run_coro(handle_bot_message({
                "chat": {"id": self.test_uid, "type": "private"},
                "from": {"id": self.test_uid, "username": "test_gamer"},
                "text": "/help"
            }))
            diwali_help = sent_messages[-1]["text"]
            self.assertIn("Chakri", diwali_help)
            self.assertIn("Rangoli", diwali_help)
            self.assertIn("Mithai", diwali_help)
            self.assertIn("Akhand Jyoti", diwali_help)

        # 3. Test _award_arcade_win updates tier atomically
        from app.arcade_engine import _award_arcade_win
        conn = get_db_connection()
        conn.execute("UPDATE users SET points_total = 498, tier_level = 0 WHERE telegram_id = ?", (self.test_uid,))
        conn.commit()
        conn.close()
        _award_arcade_win(self.test_uid, 5) # 498 + 5 = 503 -> Tier 1 (Pixel Warrior)
        conn = get_db_connection()
        u_after = conn.execute("SELECT points_total, tier_level FROM users WHERE telegram_id = ?", (self.test_uid,)).fetchone()
        conn.close()
        self.assertEqual(u_after["points_total"], 503)
        self.assertEqual(u_after["tier_level"], 1)

        # Reset back to arcade
        set_active_festival("arcade")

if __name__ == "__main__":
    unittest.main()
