import unittest
import os
import random
import tempfile
import asyncio
import json
from unittest.mock import patch, AsyncMock
from app.config import settings
from app.database import get_db_connection, init_db
from app.group_activities import (
    ensure_group_events_table, create_flash_diya, claim_flash_diya,
    create_trivia_drop, answer_trivia_drop, get_gharana_clash_card
)
from app.bot import handle_bot_message, handle_bot_callback_query

def run_coro(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    except Exception as e:
        raise e

class TestGroupActivities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_group_act_{random.randint(10000, 99999)}.db")
        settings.DATABASE_PATH = cls.test_db
        settings.ADMIN_IDS = [1257427765]
        settings.BOT_TOKEN = "mock_token"
        init_db()
        ensure_group_events_table()

    def setUp(self):
        self.user_a = 881001
        self.user_b = 881002
        self.user_c = 881003
        self.user_d = 881004
        self.admin_id = 1257427765
        self.group_chat_id = -100987654321

        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM group_events WHERE chat_id = ?", (self.group_chat_id,))
            for uid in [self.user_a, self.user_b, self.user_c, self.user_d, self.admin_id]:
                conn.execute("DELETE FROM users WHERE telegram_id = ?", (uid,))
                conn.execute(
                    '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level, joined_groups)
                       VALUES (?, ?, ?, 1, 10, 5, 0, 1)''',
                    (uid, f"user_{uid}", f"Player_{uid}")
                )
        conn.close()

    def test_flash_diya_create_and_claims(self):
        # Create a 2-claim flash diya
        event_id, text, kb = create_flash_diya(self.group_chat_id, max_claims=2)
        self.assertGreater(event_id, 0)
        self.assertIn("MAHA AARTI", text)
        self.assertIn("Light the Sacred Diya", kb["inline_keyboard"][0][0]["text"])

        # Claim with User A
        res_a = claim_flash_diya(event_id, self.user_a, "Alice")
        self.assertTrue(res_a["ok"])
        self.assertEqual(res_a["remaining"], 1)
        self.assertFalse(res_a["is_completed"])
        self.assertEqual(res_a["new_wicks"], 6) # 5 + 1
        self.assertEqual(res_a["new_pts"], 15)  # 10 + 5

        # Duplicate claim by User A blocked
        res_dup = claim_flash_diya(event_id, self.user_a, "Alice")
        self.assertFalse(res_dup["ok"])
        self.assertEqual(res_dup["reason"], "already_claimed")

        # Claim with User B (exhausts event)
        res_b = claim_flash_diya(event_id, self.user_b, "Bob")
        self.assertTrue(res_b["ok"])
        self.assertEqual(res_b["remaining"], 0)
        self.assertTrue(res_b["is_completed"])
        self.assertEqual(len(res_b["winners"]), 2)

        # Claim with User C after exhaustion
        res_c = claim_flash_diya(event_id, self.user_c, "Charlie")
        self.assertFalse(res_c["ok"])
        self.assertEqual(res_c["reason"], "exhausted")

    def test_trivia_drop_and_answers(self):
        q = {
            "question": "What is the festival of lights called?",
            "options": ["Holi", "Deepavali", "Eid", "Navratri"],
            "correct_idx": 1
        }
        event_id, text, kb = create_trivia_drop(self.group_chat_id, question_override=q)
        self.assertGreater(event_id, 0)
        self.assertIn("SACRED FESTIVE TRIVIA", text)
        self.assertEqual(len(kb["inline_keyboard"][0]), 2)

        # Wrong answer with User A (chose option 0)
        res_wrong = answer_trivia_drop(event_id, self.user_a, "Alice", 0)
        self.assertFalse(res_wrong["ok"])
        self.assertEqual(res_wrong["reason"], "wrong")

        # Duplicate attempt by User A blocked
        res_dup = answer_trivia_drop(event_id, self.user_a, "Alice", 1)
        self.assertFalse(res_dup["ok"])
        self.assertEqual(res_dup["reason"], "already_attempted")

        # Correct answer with User B
        res_b = answer_trivia_drop(event_id, self.user_b, "Bob", 1)
        self.assertTrue(res_b["ok"])
        self.assertEqual(res_b["reason"], "correct")
        self.assertEqual(res_b["winner_rank"], 1)
        self.assertFalse(res_b["is_completed"])

        # Correct answer with User C
        res_c = answer_trivia_drop(event_id, self.user_c, "Charlie", 1)
        self.assertTrue(res_c["ok"])
        self.assertEqual(res_c["winner_rank"], 2)

        # Correct answer with User D (3rd winner completes it)
        res_d = answer_trivia_drop(event_id, self.user_d, "David", 1)
        self.assertTrue(res_d["ok"])
        self.assertEqual(res_d["winner_rank"], 3)
        self.assertTrue(res_d["is_completed"])

    def test_gharana_clash_card_content(self):
        card = get_gharana_clash_card()
        self.assertIn("GHARANA CLASH", card)
        self.assertIn("Surya Gharana", card)
        self.assertIn("Agni Gharana", card)
        self.assertIn("Chandra Gharana", card)
        self.assertIn("Vayu Gharana", card)
        self.assertIn("2X SURGE", card)

    @patch("app.bot.send_telegram_message", new_callable=AsyncMock)
    @patch("app.bot.send_telegram_message_with_id", new_callable=AsyncMock)
    @patch("app.bot.edit_telegram_message", new_callable=AsyncMock)
    @patch("app.bot.answer_telegram_callback_query", new_callable=AsyncMock)
    @patch("app.bot.send_bot_log", new_callable=AsyncMock)
    def test_bot_group_commands_and_callbacks(self, mock_log, mock_ans, mock_edit, mock_send_id, mock_send):
        mock_send_id.return_value = (True, 999999)
        mock_send.return_value = True
        mock_edit.return_value = True
        mock_ans.return_value = True

        # 1. /clash in group
        msg_clash = {
            "chat": {"id": self.group_chat_id, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": "/clash"
        }
        run_coro(handle_bot_message(msg_clash))

        # 2. Non-admin denied /dropdiya
        msg_denied = {
            "chat": {"id": self.group_chat_id, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.user_a, "first_name": "Alice"},
            "text": "/dropdiya"
        }
        run_coro(handle_bot_message(msg_denied))

        # 3. Admin authorized /dropdiya
        msg_admin = {
            "chat": {"id": self.group_chat_id, "type": "supergroup", "username": "Ordinal_Legacy", "title": "Ordinal Legacy"},
            "from": {"id": self.admin_id, "first_name": "Admin"},
            "text": "/dropdiya"
        }
        run_coro(handle_bot_message(msg_admin))

        # 4. Callback query claim_diya works without owner_id guard
        event_id, _, _ = create_flash_diya(self.group_chat_id, max_claims=5)
        cb_query = {
            "id": "cb_test_diya_1",
            "from": {"id": self.user_a, "first_name": "Alice"},
            "message": {"chat": {"id": self.group_chat_id, "type": "supergroup"}, "message_id": 555},
            "data": f"claim_diya:{event_id}"
        }
        run_coro(handle_bot_callback_query(cb_query))

        # User B can also claim without owner_id guard blocking
        cb_query_b = {
            "id": "cb_test_diya_2",
            "from": {"id": self.user_b, "first_name": "Bob"},
            "message": {"chat": {"id": self.group_chat_id, "type": "supergroup"}, "message_id": 555},
            "data": f"claim_diya:{event_id}"
        }
        run_coro(handle_bot_callback_query(cb_query_b))
