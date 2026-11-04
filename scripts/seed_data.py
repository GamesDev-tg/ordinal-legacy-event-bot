import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_connection, init_db, calculate_tier
from app.config import settings

def seed_sample_data():
    init_db()
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM partner_wick_gifts")
        conn.execute("DELETE FROM referrals")
        conn.execute("DELETE FROM game_sessions")
        conn.execute("DELETE FROM users")
        conn.execute("UPDATE community_state SET total_sparks = 0, current_stage = 0 WHERE id = 1")
        
        sample_users = [
            (1001, "shiva_lord", "Shiva", 1, 820),
            (1002, "arjun_crypto", "Arjun", 1, 760),
            (1003, "kavita_sol", "Kavita", 2, 610),
            (1004, "rahul_btc", "Rahul", 2, 560),
            (1005, "priya_ord", "Priya", 3, 420),
            (1006, "amit_eth", "Amit", 3, 390),
            (1007, "sneha_diya", "Sneha", 4, 250),
            (1008, "vikram_spk", "Vikram", 4, 140),
            (1009, "anita_fest", "Anita", 1, 90),
            (1010, "rohan_test", "Rohan", 2, 45)
        ]
        
        total_sparks = 0
        for uid, uname, fname, gid, pts in sample_users:
            tier = calculate_tier(pts)
            conn.execute(
                '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level)
                   VALUES (?, ?, ?, ?, ?, 10, ?)''',
                (uid, uname, fname, gid, pts, tier)
            )
            total_sparks += pts
            
        conn.execute(
            '''INSERT INTO referrals (referrer_id, referred_id, is_companion, bonus_awarded)
               VALUES (1001, 1002, 1, 1)'''
        )
        conn.execute(
            '''INSERT INTO referrals (referrer_id, referred_id, is_companion, bonus_awarded)
               VALUES (1001, 1003, 0, 1)'''
        )
        conn.execute("UPDATE community_state SET total_sparks = ? WHERE id = 1", (total_sparks,))
        
    conn.close()
    print(f"Seeded {len(sample_users)} users. Total sparks: {total_sparks}")

if __name__ == "__main__":
    seed_sample_data()
