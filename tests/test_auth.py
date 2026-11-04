import unittest
import sys
import os
import hashlib
import hmac
import urllib.parse
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.auth import verify_telegram_init_data
from app.config import settings

class TestAuth(unittest.TestCase):
    def test_dev_user_bypass(self):
        res = verify_telegram_init_data("dev_user_99999")
        self.assertEqual(res["user"]["id"], 99999)
        self.assertEqual(res["user"]["username"], "player_99999")

    def test_valid_hmac(self):
        token = settings.BOT_TOKEN
        params = {
            "auth_date": "1710000000",
            "query_id": "AAHdF6IQAAAAAN0XohD72r8V",
            "user": '{"id":12345,"first_name":"Diwali","username":"diwali_player"}'
        }
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
        
        params_with_hash = dict(params)
        params_with_hash["hash"] = computed_hash
        init_data_str = urllib.parse.urlencode(params_with_hash)
        
        verified = verify_telegram_init_data(init_data_str)
        self.assertEqual(verified["user"]["id"], 12345)

    def test_tampered_hmac(self):
        init_data_str = "user=%7B%22id%22%3A12345%7D&auth_date=1710000000&hash=fake_invalid_hash_value"
        with self.assertRaises(HTTPException) as ctx:
            verify_telegram_init_data(init_data_str)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_empty_init_data(self):
        with self.assertRaises(HTTPException) as ctx:
            verify_telegram_init_data("")
        self.assertEqual(ctx.exception.status_code, 400)

if __name__ == "__main__":
    unittest.main()
