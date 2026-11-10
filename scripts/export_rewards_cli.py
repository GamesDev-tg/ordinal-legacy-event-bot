import sys
import os
import csv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db_connection, get_tier_name

def generate_reward_reports(output_csv_path="final_rewards_report.csv"):
    conn = get_db_connection()
    
    print("=" * 65)
    print("   ORDINAL LEGACY EVENT BOT — FINAL REWARDS & TIER AUDIT")
    print("=" * 65)
    
    print("\n[1] PLAYER TIER BREAKDOWN:")
    rows = conn.execute('''
        SELECT 
            tier_level,
            COUNT(*) as count,
            MIN(points_total) as min_pts,
            MAX(points_total) as max_pts,
            ROUND(AVG(points_total), 1) as avg_pts
        FROM users
        GROUP BY tier_level
        ORDER BY tier_level DESC
    ''').fetchall()
    
    print(f"{'Tier':<8} {'Name':<24} {'Players':<10} {'Min':<8} {'Max':<8} {'Avg Pts':<10}")
    print("-" * 65)
    for r in rows:
        t = r["tier_level"]
        print(f"Tier {t:<3} {get_tier_name(t):<24} {r['count']:<10} {r['min_pts']:<8} {r['max_pts']:<8} {r['avg_pts']:<10}")
        
    print("\n[2] TOP 50 SOVEREIGNS (Rare Inscription + Sovereign Mukut):")
    sovereigns = conn.execute('''
        SELECT 
            ROW_NUMBER() OVER (ORDER BY points_total DESC, id ASC) as rank,
            telegram_id, username, first_name, points_total
        FROM users
        WHERE tier_level = 5
        ORDER BY points_total DESC, id ASC
        LIMIT 50
    ''').fetchall()
    
    print(f"{'Rank':<6} {'Telegram ID':<14} {'Username':<18} {'Points':<8}")
    print("-" * 50)
    for s in sovereigns:
        uname = f"@{s['username']}" if s['username'] else f"{s['first_name']}"
        print(f"#{s['rank']:<5} {s['telegram_id']:<14} {uname:<18} {s['points_total']:<8}")

    all_users = conn.execute('''
        SELECT 
            ROW_NUMBER() OVER (ORDER BY points_total DESC, id ASC) as rank,
            telegram_id, username, first_name, points_total, tier_level
        FROM users
        ORDER BY points_total DESC, id ASC
    ''').fetchall()
    conn.close()

    with open(output_csv_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Telegram ID", "Username", "First Name", "Points Total", "Tier Level", "Tier Name", "Reward Category", "Shares / Tickets"])
        
        for u in all_users:
            t = u["tier_level"]
            pts = u["points_total"]
            rank = u["rank"]
            t_name = get_tier_name(t)
            
            category = "Participation"
            shares = "0"
            if t == 5:
                category = "Top 50 Sovereign" if rank <= 50 else "Akhand Sovereign"
                shares = "4 Shares + Sovereign Mukut"
            elif t == 4:
                category = "Deep Mahant"
                shares = "2 Airdrop Shares"
            elif t == 3:
                category = "Spark Master"
                shares = "1 Airdrop Share"
            elif t == 2:
                tickets = min(10, max(1, pts // 100))
                category = "Rangoli Artisan"
                shares = f"{tickets} Raffle Tickets"
            elif t == 1:
                category = "Diya Sevak"
                shares = "Sticker Pack + Bronze Frame"
                
            writer.writerow([rank, u["telegram_id"], u["username"] or "", u["first_name"] or "", pts, t, t_name, category, shares])

    print(f"\n✅ Full CSV Export generated successfully: {output_csv_path}\n")

if __name__ == "__main__":
    generate_reward_reports()
