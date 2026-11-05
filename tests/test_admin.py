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
from app.routes.admin_routes import (
    api_admin_add_points, api_tier_distribution, api_export_rewards,
    api_admin_query, api_users_by_tier, api_admin_reset_wicks, api_admin_stats,
    api_admin_reset_event, api_admin_backup
)
from app.models import AdminAddPointsRequest, AdminQueryRequest, AdminResetEventRequest

class TestAdmin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = os.path.join(tempfile.gettempdir(), f"test_admin_{random.randint(10000, 99999)}.db")
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
        self.admin_id = 999001
        self.non_admin_id = 999002
        self.target_user = random.randint(100000, 900000)
        register_user_if_new(self.target_user, f"target_{self.target_user}", "Target")

    def test_admin_add_points_and_tier_update(self):
        req = AdminAddPointsRequest(
            admin_telegram_id=self.admin_id,
            target_telegram_id=self.target_user,
            points_to_add=500
        )
        res = api_admin_add_points(req)
        self.assertTrue(res.success)
        self.assertEqual(res.new_total, 500)
        self.assertEqual(res.new_tier, 1)

    def test_unauthorized_admin_rejected(self):
        req = AdminAddPointsRequest(
            admin_telegram_id=self.non_admin_id,
            target_telegram_id=self.target_user,
            points_to_add=50
        )
        with self.assertRaises(HTTPException) as ctx:
            api_admin_add_points(req)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_tier_distribution_and_export(self):
        dist = api_tier_distribution(self.admin_id)
        self.assertTrue(dist["success"])
        self.assertGreaterEqual(len(dist["distribution"]), 1)

        rewards = api_export_rewards(self.admin_id)
        self.assertGreaterEqual(len(rewards), 1)

    def test_admin_query_select(self):
        req = AdminQueryRequest(
            admin_telegram_id=self.admin_id,
            query="SELECT telegram_id, points_total FROM users WHERE telegram_id = " + str(self.target_user)
        )
        res = api_admin_query(req)
        self.assertTrue(res.success)
        self.assertEqual(res.query_type, "SELECT")
        self.assertIn("telegram_id", res.columns)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["telegram_id"], self.target_user)

    def test_admin_query_update(self):
        req = AdminQueryRequest(
            admin_telegram_id=self.admin_id,
            query=f"UPDATE users SET diya_wicks = 7 WHERE telegram_id = {self.target_user}"
        )
        res = api_admin_query(req)
        self.assertTrue(res.success)
        self.assertEqual(res.query_type, "UPDATE")
        self.assertEqual(res.rows_affected, 1)

    def test_admin_query_blocked_keywords(self):
        req = AdminQueryRequest(
            admin_telegram_id=self.admin_id,
            query="DROP TABLE users;"
        )
        with self.assertRaises(HTTPException) as ctx:
            api_admin_query(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Only SELECT and UPDATE", ctx.exception.detail)

    def test_admin_users_by_tier(self):
        res = api_users_by_tier(self.admin_id, tier_level=0)
        self.assertTrue(res.success)
        self.assertEqual(res.tier_level, 0)
        self.assertGreaterEqual(res.total_users, 1)

    def test_admin_reset_wicks(self):
        res = api_admin_reset_wicks(self.admin_id, self.target_user)
        self.assertTrue(res["success"])
        self.assertEqual(res["wicks"], settings.STAMINA_BANK_CAP)

    def test_admin_stats(self):
        res = api_admin_stats(self.admin_id)
        self.assertTrue(res["success"])
        self.assertIn("total_users", res)
        self.assertIn("community_sparks", res)
        self.assertIn("progress_pct", res)

    def test_admin_backup(self):
        res = api_admin_backup(self.admin_id)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.total_users, 1)
        self.assertIn("users", res.backup_data)
        self.assertIn("community_state", res.backup_data)

    def test_admin_reset_event(self):
        # First ensure target user has some points
        req = AdminAddPointsRequest(admin_telegram_id=self.admin_id, target_telegram_id=self.target_user, points_to_add=150)
        api_admin_add_points(req)

        # Unconfirmed reset should fail
        with self.assertRaises(HTTPException):
            api_admin_reset_event(AdminResetEventRequest(admin_telegram_id=self.admin_id, confirm=False))

        # Confirmed reset should succeed
        res = api_admin_reset_event(AdminResetEventRequest(admin_telegram_id=self.admin_id, confirm=True))
        self.assertTrue(res.success)

        # Verify target user points are 0 and wicks are 10
        conn = get_db_connection()
        user = conn.execute("SELECT points_total, diya_wicks, tier_level FROM users WHERE telegram_id = ?", (self.target_user,)).fetchone()
        comm = conn.execute("SELECT total_sparks, current_stage FROM community_state WHERE id = 1").fetchone()
        conn.close()

        self.assertEqual(user["points_total"], 0)
        self.assertEqual(user["tier_level"], 0)
        self.assertEqual(user["diya_wicks"], 10)
        self.assertEqual(comm["total_sparks"], 0)
        self.assertEqual(comm["current_stage"], 0)

    def test_dynamic_admins_and_settings(self):
        from app.database import (
            get_all_admin_ids, add_admin_id, remove_admin_id,
            get_system_setting, set_system_setting, restore_from_backup_data,
            generate_full_backup
        )
        # Test settings
        set_system_setting("test_key", "test_val")
        self.assertEqual(get_system_setting("test_key"), "test_val")

        # Test add/remove admin
        new_adm = 888123
        self.assertNotIn(new_adm, get_all_admin_ids())
        added = add_admin_id(new_adm)
        self.assertTrue(added)
        self.assertIn(new_adm, get_all_admin_ids())

        # Cannot remove super admin
        super_adm = 1257427765
        self.assertFalse(remove_admin_id(super_adm))

        # Can remove added admin
        self.assertTrue(remove_admin_id(new_adm))
        self.assertNotIn(new_adm, get_all_admin_ids())

        # Test backup & restore
        backup = generate_full_backup()
        self.assertIn("users", backup["data"])
        restored = restore_from_backup_data(backup)
        self.assertTrue(restored["success"])

    def test_purge_dummy_data(self):
        from app.database import purge_dummy_data
        conn = get_db_connection()
        # insert a dummy user
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (111222, 'test_dummy', 'Test Dummy')")
        conn.commit()
        conn.close()

        res = purge_dummy_data()
        self.assertTrue(res["success"])

        conn = get_db_connection()
        dummy = conn.execute("SELECT * FROM users WHERE telegram_id = 111222").fetchone()
        conn.close()
        self.assertIsNone(dummy)

if __name__ == "__main__":
    unittest.main()
