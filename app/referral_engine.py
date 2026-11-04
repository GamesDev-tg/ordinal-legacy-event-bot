import datetime
from fastapi import HTTPException
from app.config import settings
from app.database import get_db_connection, calculate_tier

def process_referral_claim(referrer_id: int, referred_id: int) -> dict:
    if referrer_id == referred_id:
        raise HTTPException(status_code=400, detail="Cannot self-refer!")
    
    conn = get_db_connection()
    with conn:
        referrer = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (referrer_id,)).fetchone()
        if not referrer:
            raise HTTPException(status_code=404, detail="Referrer account does not exist.")
        
        existing_ref = conn.execute("SELECT * FROM referrals WHERE referred_id = ?", (referred_id,)).fetchone()
        if existing_ref:
            raise HTTPException(status_code=400, detail="You have already claimed a referral link.")
        
        comp_row = conn.execute(
            "SELECT * FROM referrals WHERE referrer_id = ? AND is_companion = 1",
            (referrer_id,)
        ).fetchone()
        
        is_companion = 1 if comp_row is None else 0
        points_to_award = 0
        
        if referrer["referral_points_earned"] < settings.MAX_REFERRAL_POINTS:
            points_to_award = 1
            new_user_points = referrer["points_total"] + 1
            new_ref_earned = referrer["referral_points_earned"] + 1
            new_tier = calculate_tier(new_user_points)
            
            conn.execute(
                "UPDATE users SET points_total = ?, referral_points_earned = ?, tier_level = ? WHERE telegram_id = ?",
                (new_user_points, new_ref_earned, new_tier, referrer_id)
            )
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + 1 WHERE id = 1")
            
        conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, is_companion, bonus_awarded) VALUES (?, ?, ?, ?)",
            (referrer_id, referred_id, is_companion, points_to_award)
        )
        
        referred_user = conn.execute("SELECT first_name, username FROM users WHERE telegram_id = ?", (referred_id,)).fetchone()
        if not referred_user:
            counts = conn.execute('''
                SELECT g.id, COUNT(u.id) as count 
                FROM (SELECT 1 as id UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) as g
                LEFT JOIN users u ON u.gharana_id = g.id
                GROUP BY g.id ORDER BY count ASC, g.id ASC
            ''').fetchall()
            assigned_gharana = counts[0]["id"] if counts else 1
            conn.execute(
                '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level)
                   VALUES (?, ?, ?, ?, 0, 10, 0)''',
                (referred_id, f"player_{referred_id}", f"Lampbearer_{referred_id}", assigned_gharana)
            )
            friend_name = f"Lampbearer_{referred_id}"
        else:
            friend_name = referred_user["first_name"] or referred_user["username"] or f"Player_{referred_id}"
        
        total_ref_earned = referrer["referral_points_earned"] + points_to_award
        
    conn.close()
    
    if is_companion == 1:
        msg = f"Diya Companion bond formed! +{points_to_award} Point added to inviter ({total_ref_earned}/{settings.MAX_REFERRAL_POINTS} capped points)."
    else:
        msg = f"Friend activated (+{points_to_award} Point added to inviter ({total_ref_earned}/{settings.MAX_REFERRAL_POINTS} capped points))!"
        
    return {
        "success": True,
        "is_companion": bool(is_companion),
        "referrer_awarded": bool(points_to_award > 0),
        "referral_points_earned": total_ref_earned,
        "points_awarded_to_referrer": points_to_award,
        "partner_name": friend_name,
        "message": msg
    }

def send_companion_wick_gift(sender_id: int) -> dict:
    today_str = datetime.date.today().isoformat()
    conn = get_db_connection()
    with conn:
        comp = conn.execute(
            '''SELECT CASE WHEN referrer_id = ? THEN referred_id ELSE referrer_id END AS partner_id
               FROM referrals 
               WHERE (referrer_id = ? OR referred_id = ?) AND is_companion = 1''',
            (sender_id, sender_id, sender_id)
        ).fetchone()
        
        if not comp:
            raise HTTPException(status_code=400, detail="You do not have a Diya Companion yet! Invite 1 friend first.")
            
        partner_id = comp["partner_id"]
        existing = conn.execute(
            "SELECT * FROM partner_wick_gifts WHERE sender_id = ? AND gift_date = ?",
            (sender_id, today_str)
        ).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="You have already sent a gift wick to your companion today!")
            
        p_user = conn.execute("SELECT diya_wicks FROM users WHERE telegram_id = ?", (partner_id,)).fetchone()
        cur_wicks = p_user["diya_wicks"] if p_user else 0
        new_wicks = min(settings.STAMINA_BANK_CAP, cur_wicks + 1)
        conn.execute("UPDATE users SET diya_wicks = ? WHERE telegram_id = ?", (new_wicks, partner_id))
        conn.execute(
            "INSERT INTO partner_wick_gifts (sender_id, receiver_id, gift_date) VALUES (?, ?, ?)",
            (sender_id, partner_id, today_str)
        )
    conn.close()
    
    return {"success": True, "message": "Sent 1 free Diya Wick to your companion!"}
