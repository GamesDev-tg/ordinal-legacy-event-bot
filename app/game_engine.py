import random
import uuid
import secrets
import datetime
from fastapi import HTTPException
from app.config import settings
from app.database import get_db_connection, calculate_tier, get_tier_name, get_stage_info

def get_random_wick_cooldown() -> int:
    """Returns a random stamina refill duration between 1 to 3 minutes (60 to 180 seconds)."""
    return random.randint(60, 180)

def _parse_timestamp(val, default_dt: datetime.datetime) -> datetime.datetime:
    if not val:
        return default_dt
    if isinstance(val, datetime.datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=datetime.timezone.utc)
        return val
    if isinstance(val, str):
        try:
            dt = datetime.datetime.fromisoformat(val)
        except Exception:
            try:
                dt = datetime.datetime.strptime(val.split('.')[0], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return default_dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    return default_dt

def update_user_stamina(conn, telegram_id: int) -> int:
    try:
        user = conn.execute("SELECT diya_wicks, last_wick_regen, wick_cooldown_seconds FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    except Exception:
        user = conn.execute("SELECT diya_wicks, last_wick_regen FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()

    if not user:
        return 0
    
    current_wicks = user["diya_wicks"]
    now = datetime.datetime.now(datetime.timezone.utc)
    
    if current_wicks >= settings.STAMINA_BANK_CAP:
        return current_wicks
    
    last_regen = _parse_timestamp(user["last_wick_regen"], now)
    try:
        cooldown = user["wick_cooldown_seconds"] or get_random_wick_cooldown()
    except (IndexError, KeyError):
        cooldown = get_random_wick_cooldown()

    elapsed_seconds = (now - last_regen).total_seconds()
    if elapsed_seconds < cooldown:
        return current_wicks

    # Progressively award wicks for each random 1-3 minute window passed
    gained = 0
    temp_wicks = current_wicks
    curr_cooldown = cooldown
    rem_elapsed = elapsed_seconds

    while rem_elapsed >= curr_cooldown and temp_wicks < settings.STAMINA_BANK_CAP:
        rem_elapsed -= curr_cooldown
        temp_wicks += 1
        gained += 1
        curr_cooldown = get_random_wick_cooldown()

    if gained > 0:
        if temp_wicks >= settings.STAMINA_BANK_CAP:
            new_regen_time = now
            next_cooldown = get_random_wick_cooldown()
        else:
            new_regen_time = now - datetime.timedelta(seconds=rem_elapsed)
            next_cooldown = curr_cooldown
        
        try:
            conn.execute(
                "UPDATE users SET diya_wicks = ?, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?",
                (temp_wicks, new_regen_time.isoformat(), next_cooldown, telegram_id)
            )
        except Exception:
            conn.execute(
                "UPDATE users SET diya_wicks = ?, last_wick_regen = ? WHERE telegram_id = ?",
                (temp_wicks, new_regen_time.isoformat(), telegram_id)
            )
        return temp_wicks

    return current_wicks

def get_seconds_until_next_wick(conn, telegram_id: int) -> int:
    try:
        user = conn.execute("SELECT diya_wicks, last_wick_regen, wick_cooldown_seconds FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    except Exception:
        user = conn.execute("SELECT diya_wicks, last_wick_regen FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()

    if not user or user["diya_wicks"] >= settings.STAMINA_BANK_CAP:
        return 0
    
    now = datetime.datetime.now(datetime.timezone.utc)
    last_regen = _parse_timestamp(user["last_wick_regen"], now)
    try:
        cooldown = user["wick_cooldown_seconds"] or 120
    except (IndexError, KeyError):
        cooldown = 120

    elapsed_seconds = (now - last_regen).total_seconds()
    remaining = cooldown - elapsed_seconds
    return max(0, int(remaining))

def claim_shubh_refill(telegram_id: int) -> dict:
    today_str = datetime.date.today().isoformat()
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db_connection()
    with conn:
        update_user_stamina(conn, telegram_id)
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        if user["shubh_refill_date"] == today_str:
            raise HTTPException(status_code=400, detail="You have already claimed today's Shubh Muhurat refill! Come back tomorrow.")
            
        current_wicks = user["diya_wicks"]
        new_wicks = min(settings.STAMINA_BANK_CAP, current_wicks + 5)
        added_wicks = new_wicks - current_wicks
        
        bonus_points = 5
        new_points = user["points_total"] + bonus_points
        new_tier = calculate_tier(new_points)
        
        conn.execute(
            "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ?, shubh_refill_date = ?, last_wick_regen = ? WHERE telegram_id = ?",
            (new_wicks, new_points, new_tier, today_str, now_str, telegram_id)
        )
        conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (bonus_points,))
    conn.close()
    
    return {
        "success": True,
        "wicks_added": added_wicks,
        "wicks_total": new_wicks,
        "points_added": bonus_points,
        "points_total": new_points,
        "tier_level": new_tier,
        "message": f"✨ Shubh Muhurat Blessing! Received +{added_wicks} Diya Wicks and +{bonus_points} Festive Sparks! Score: {new_points} Pts."
    }

def start_game_session(telegram_id: int, game_type: int) -> dict:
    conn = get_db_connection()
    with conn:
        wicks = update_user_stamina(conn, telegram_id)
        if wicks < 1:
            raise HTTPException(status_code=400, detail="Out of Diya Wicks! Wait for stamina regeneration.")
        
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        next_cd = get_random_wick_cooldown()
        if wicks == settings.STAMINA_BANK_CAP:
            try:
                conn.execute(
                    "UPDATE users SET diya_wicks = diya_wicks - 1, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?",
                    (now_str, next_cd, telegram_id)
                )
            except Exception:
                conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1, last_wick_regen = ? WHERE telegram_id = ?", (now_str, telegram_id))
        else:
            conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1 WHERE telegram_id = ?", (telegram_id,))
        
        session_id = str(uuid.uuid4())
        seed = secrets.token_hex(6)
        nonce = secrets.token_hex(16)
        
        conn.execute(
            '''INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, duration_ms, is_valid)
               VALUES (?, ?, ?, ?, ?, 0, 0, 0)''',
            (session_id, telegram_id, game_type, seed, nonce)
        )
    conn.close()
    
    return {
        "session_id": session_id,
        "seed": seed,
        "nonce": nonce,
        "wicks_remaining": wicks - 1
    }

def finish_game_session(telegram_id: int, session_id: str, nonce: str, raw_score: int, duration_ms: int) -> dict:
    if raw_score not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Invalid score! Scores are strictly in the 1–3 point range.")
    
    min_ms = settings.MIN_GAME_DURATION_SECONDS * 1000
    if duration_ms < min_ms:
        raise HTTPException(status_code=400, detail=f"Game run too fast ({duration_ms}ms < {min_ms}ms). Input rejected.")
    
    conn = get_db_connection()
    with conn:
        session = conn.execute(
            "SELECT * FROM game_sessions WHERE id = ? AND telegram_id = ? AND nonce = ?",
            (session_id, telegram_id, nonce)
        ).fetchone()
        
        if not session:
            raise HTTPException(status_code=404, detail="Game session or nonce not found or mismatched.")
        
        if session["is_valid"] != 0:
            raise HTTPException(status_code=400, detail="Replay attack detected! Session already finished.")
        
        conn.execute(
            "UPDATE game_sessions SET score_awarded = ?, duration_ms = ?, is_valid = 1 WHERE id = ?",
            (raw_score, duration_ms, session_id)
        )
        
        user = conn.execute("SELECT points_total, tier_level FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        old_points = user["points_total"]
        old_tier = user["tier_level"]
        new_points = old_points + raw_score
        new_tier = calculate_tier(new_points)
        tier_unlocked = new_tier > old_tier
        
        conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_points, new_tier, telegram_id))
        conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (raw_score,))
        
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        comm_total = comm["total_sparks"]
        
        new_stage, _ = get_stage_info(comm_total)
        conn.execute("UPDATE community_state SET current_stage = ? WHERE id = 1", (new_stage,))
        
    conn.close()
    
    return {
        "success": True,
        "points_awarded": raw_score,
        "new_user_total": new_points,
        "community_total": comm_total,
        "tier_unlocked": tier_unlocked,
        "new_tier_level": new_tier,
        "tier_name": get_tier_name(new_tier)
    }
