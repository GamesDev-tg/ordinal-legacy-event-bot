import unittest
from app.captcha_engine import (
    get_or_create_captcha, verify_captcha_answer,
    record_game_play_and_check_captcha, is_user_captcha_locked,
    lock_user_captcha, unlock_user_captcha
)

class TestCaptchaEngine(unittest.TestCase):
    def setUp(self):
        self.user_id = 888777
        unlock_user_captcha(self.user_id)

    def test_generate_and_solve_captcha(self):
        challenge = get_or_create_captcha(self.user_id)
        self.assertIn("question", challenge)
        self.assertEqual(len(challenge["options"]), 4)
        self.assertIn("token", challenge)
        
        correct_idx = challenge["correct_index"]
        token = challenge["token"]

        # Wrong answer should fail
        wrong_idx = (correct_idx + 1) % 4
        ok, msg = verify_captcha_answer(self.user_id, wrong_idx, token)
        self.assertFalse(ok)
        self.assertIn("Incorrect", msg)

        # Fresh challenge generated after failure
        fresh = get_or_create_captcha(self.user_id)
        ok_fresh, msg_fresh = verify_captcha_answer(self.user_id, fresh["correct_index"], fresh["token"])
        self.assertTrue(ok_fresh)
        self.assertIn("Passed", msg_fresh)

    def test_captcha_lock_and_unlock(self):
        lock_user_captcha(self.user_id)
        self.assertTrue(is_user_captcha_locked(self.user_id))
        
        unlock_user_captcha(self.user_id)
        self.assertFalse(is_user_captcha_locked(self.user_id))

    def test_periodic_play_triggers_captcha(self):
        # 14 plays should not trigger
        for _ in range(14):
            record_game_play_and_check_captcha(self.user_id)
        self.assertFalse(is_user_captcha_locked(self.user_id))

        # 15th play triggers
        triggered = record_game_play_and_check_captcha(self.user_id)
        self.assertTrue(triggered)
        self.assertTrue(is_user_captcha_locked(self.user_id))
