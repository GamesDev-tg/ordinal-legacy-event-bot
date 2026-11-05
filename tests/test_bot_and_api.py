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
        settings.BOT_TOKEN = "mock_bot_token_for_dev"
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

    def test_mydata_and_tier_rewards_ladder(self):
        from app.database import calculate_tier, get_tier_name, get_tier_reward
        self.assertEqual(calculate_tier(0), 0)
        self.assertEqual(calculate_tier(500), 1)
        self.assertEqual(calculate_tier(1500), 2)
        self.assertEqual(calculate_tier(2750), 3)
        self.assertEqual(calculate_tier(4000), 4)
        self.assertEqual(calculate_tier(5000), 5)

        self.assertIn("Coins", get_tier_reward(1))
        self.assertIn("Pearl", get_tier_reward(2))
        self.assertIn("Ticket", get_tier_reward(3))
        self.assertIn("Pet", get_tier_reward(4))
        self.assertIn("All Rewards", get_tier_reward(5))

        conn = get_db_connection()
        conn.execute("UPDATE users SET points_total = 3000, tier_level = 5, joined_groups = 1 WHERE telegram_id = ?", (self.user_id,))
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (self.user_id,)).fetchone()
        conn.close()
        self.assertEqual(u["points_total"], 3000)
        self.assertEqual(u["tier_level"], 5)
        self.assertEqual(u["joined_groups"], 1)

    def test_parse_timestamp_and_datetime_objects(self):
        import datetime
        from app.game_engine import _parse_timestamp, update_user_stamina, get_seconds_until_next_wick
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Test None
        dt_none = _parse_timestamp(None, now)
        self.assertEqual(dt_none, now)
        
        # Test native datetime object (as returned by psycopg2/Postgres)
        raw_dt = datetime.datetime(2026, 11, 5, 10, 0, 0)
        parsed = _parse_timestamp(raw_dt, now)
        self.assertEqual(parsed.year, 2026)
        self.assertIsNotNone(parsed.tzinfo)
        
        # Test ISO string
        iso_str = "2026-11-05T10:00:00+00:00"
        parsed_iso = _parse_timestamp(iso_str, now)
        self.assertEqual(parsed_iso.year, 2026)
        
        # Test standard SQL timestamp string
        sql_str = "2026-11-05 10:00:00.123456"
        parsed_sql = _parse_timestamp(sql_str, now)
        self.assertEqual(parsed_sql.year, 2026)

    def test_random_stamina_gap_refill(self):
        import datetime
        from app.game_engine import update_user_stamina, get_seconds_until_next_wick, get_random_wick_cooldown
        cd = get_random_wick_cooldown()
        self.assertGreaterEqual(cd, 60)
        self.assertLessEqual(cd, 180)

        conn = get_db_connection()
        past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=250)
        conn.execute("UPDATE users SET diya_wicks = 7, last_wick_regen = ?, wick_cooldown_seconds = 100 WHERE telegram_id = ?", (past_time.isoformat(), self.user_id))
        conn.commit()

        # After 250s with 100s initial cooldown, should gain wicks
        new_wicks = update_user_stamina(conn, self.user_id)
        self.assertGreater(new_wicks, 7)
        secs_remaining = get_seconds_until_next_wick(conn, self.user_id)
        self.assertGreaterEqual(secs_remaining, 0)
        self.assertLessEqual(secs_remaining, 180)
        conn.close()

def run_coro_sync(coro):
    while True:
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value

class TestBotAsync(unittest.TestCase):
    def setUp(self):
        self.test_db = os.path.join(tempfile.gettempdir(), f"test_bot_async_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = self.test_db
        settings.ADMIN_IDS = [999001]
        settings.BOT_TOKEN = "mock_bot_token_for_dev"
        from app.cache import clear_all_cache
        clear_all_cache()
        init_db()

    def tearDown(self):
        from app.cache import clear_all_cache
        clear_all_cache()
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_group_chatter_silence(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            group_msg = {
                "chat": {"id": -100987654321, "type": "supergroup"},
                "from": {"id": 111222, "username": "player1"},
                "text": "Hello everyone, good morning!"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(group_msg)
                mock_send.assert_not_called()
        run_coro_sync(_run())

    def test_non_admin_admins_denied(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            non_admin_admins = {
                "chat": {"id": 111222, "type": "private"},
                "from": {"id": 111222, "username": "player1"},
                "text": "/admins"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(non_admin_admins)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], 111222)
                self.assertIn("Access Denied", args[1])
        run_coro_sync(_run())

    def test_non_admin_adminhelp_denied(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            non_admin_help = {
                "chat": {"id": 111222, "type": "private"},
                "from": {"id": 111222, "username": "player1"},
                "text": "/adminhelp"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(non_admin_help)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], 111222)
                self.assertIn("Access Denied", args[1])
        run_coro_sync(_run())

    def test_admin_adminhelp_in_group_redirects(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            admin_id = 999001
            admin_group_call = {
                "chat": {"id": -100987654321, "type": "supergroup"},
                "from": {"id": admin_id, "username": "sudo_boss"},
                "text": "/adminhelp"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(admin_group_call)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], -100987654321)
                self.assertIn("in private chat", args[1])
                self.assertNotIn("ADMIN COMMAND CENTER", args[1])
        run_coro_sync(_run())

    def test_admin_adminhelp_in_dm(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            admin_id = 999001
            admin_dm_call = {
                "chat": {"id": admin_id, "type": "private"},
                "from": {"id": admin_id, "username": "sudo_boss"},
                "text": "/adminhelp"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(admin_dm_call)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], admin_id)
                self.assertIn("ADMIN COMMAND CENTER", args[1])
        run_coro_sync(_run())

    def test_group_command_with_at_suffix(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            admin_id = 999001
            settings.BOT_USERNAME = "OrdinalLegacyEventBot"
            conn = get_db_connection()
            conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id = ?", (admin_id,))
            conn.commit()
            conn.close()
            
            bot_suffix_call = {
                "chat": {"id": -100987654321, "type": "supergroup"},
                "from": {"id": admin_id, "username": "sudo_boss"},
                "text": "/status@OrdinalLegacyEventBot"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(bot_suffix_call)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], -100987654321)
                self.assertIn("Status Report", args[1])
        run_coro_sync(_run())

    def test_dm_only_commands_in_groups(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            group_game_call = {
                "chat": {"id": -100987654321, "type": "supergroup"},
                "from": {"id": 111222, "username": "player1"},
                "text": "/chakri"
            }
            with patch("app.bot.send_telegram_message", new_callable=AsyncMock) as mock_send:
                await handle_bot_message(group_game_call)
                mock_send.assert_called_once()
                args, _ = mock_send.call_args
                self.assertEqual(args[0], -100987654321)
                self.assertIn("in private chat", args[1])
                self.assertNotIn("CHAKRI WHIRL: SPARK HARVEST", args[1])
        run_coro_sync(_run())

    def test_button_click_guard_other_user(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            other_user_click = {
                "id": "cb_query_12345",
                "from": {"id": 888999, "username": "other_player"},
                "message": {"chat": {"id": -100987654321, "type": "supergroup"}},
                "data": "play_chakri:111222"
            }
            with patch("app.bot.answer_telegram_callback_query", new_callable=AsyncMock) as mock_ans, \
                 patch("app.bot.run_in_chat_chakri", new_callable=AsyncMock) as mock_chakri:
                await handle_bot_callback_query(other_user_click)
                mock_ans.assert_called_once()
                ans_args, ans_kwargs = mock_ans.call_args
                self.assertEqual(ans_args[0], "cb_query_12345")
                self.assertIn("belongs to another player", ans_kwargs.get("text", ""))
                self.assertTrue(ans_kwargs.get("show_alert", False))
                mock_chakri.assert_not_called()
        run_coro_sync(_run())

    def test_button_click_anti_spam(self):
        async def _run():
            from unittest.mock import patch, AsyncMock
            owner_click = {
                "id": "cb_query_99901",
                "from": {"id": 777666, "username": "speedy"},
                "message": {"chat": {"id": 777666, "type": "private"}},
                "data": "cmd_status:777666"
            }
            with patch("app.bot.answer_telegram_callback_query", new_callable=AsyncMock) as mock_ans, \
                 patch("app.bot.handle_bot_message", new_callable=AsyncMock) as mock_msg:
                await handle_bot_callback_query(owner_click)
                owner_click["id"] = "cb_query_99902"
                await handle_bot_callback_query(owner_click)
                last_call = mock_ans.call_args
                self.assertIn("wait a moment", last_call[1].get("text", ""))
        run_coro_sync(_run())

if __name__ == "__main__":
    unittest.main()
