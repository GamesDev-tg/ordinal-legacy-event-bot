import unittest
import time
from app.cache import get_cache, set_cache, delete_cache, clear_all_cache

class TestCache(unittest.TestCase):
    def setUp(self):
        clear_all_cache()

    def tearDown(self):
        clear_all_cache()

    def test_cache_set_and_get(self):
        set_cache("test_key", {"points": 100, "user": "ram"}, ttl_seconds=5.0)
        cached = get_cache("test_key")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["points"], 100)
        self.assertEqual(cached["user"], "ram")

    def test_cache_delete(self):
        set_cache("del_key", "secret_value", ttl_seconds=10.0)
        self.assertEqual(get_cache("del_key"), "secret_value")
        delete_cache("del_key")
        self.assertIsNone(get_cache("del_key"))

    def test_cache_expiration(self):
        set_cache("short_key", "ephemeral", ttl_seconds=0.1)
        self.assertEqual(get_cache("short_key"), "ephemeral")
        time.sleep(0.15)
        self.assertIsNone(get_cache("short_key"))

if __name__ == "__main__":
    unittest.main()
