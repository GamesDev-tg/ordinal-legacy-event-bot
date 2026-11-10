import random
import uuid
import secrets
import datetime
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException
from app.config import settings
from app.database import get_db_connection, calculate_tier, get_tier_name, get_stage_info, is_postgres

GHARANA_BOOST_DURATION_SECONDS = 600  # 10 minutes per Gharana
GHARANA_TOTAL_CYCLE_SECONDS = GHARANA_BOOST_DURATION_SECONDS * 4  # 2400 seconds (40 minutes for all 4 houses)

GHARANA_EMOJIS = {
    1: "☀️",
    2: "🔥",
    3: "🌙",
    4: "💨"
}

def get_final_rush_multiplier(user_gharana_id: int) -> Tuple[int, bool, bool]:
    from app.database import get_system_setting
    rush_active = (get_system_setting("final_rush_active", "0") == "1")
    boost = get_gharana_boost_status()
    is_boosted = (user_gharana_id == boost["active_gharana_id"])
    if rush_active:
        multiplier = 3 if is_boosted else 2
    else:
        multiplier = 2 if is_boosted else 1
    return multiplier, is_boosted, rush_active

def claim_final_rush_wicks(user_id: int) -> dict:
    from app.database import get_db_connection, get_system_setting, set_system_setting, get_all_admin_ids
    is_admin_user = (user_id in get_all_admin_ids())
    key = f"rush_claimed_{user_id}"
    if not is_admin_user and get_system_setting(key, ""):
        return {
            "success": False,
            "message": "⚠️ <b>Blessing Already Claimed</b>\n\nYou have already received your +5 Diya Wicks Final Rush blessing! Use them in games before midnight (12:00 AM IST)!"
        }
    
    conn = get_db_connection()
    try:
        with conn:
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT diya_wicks, first_name FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"success": False, "message": "❌ User record not found. Send /start to join first!"}
            
            curr = u["diya_wicks"]
            added = min(5, settings.STAMINA_BANK_CAP - curr)
            if added <= 0:
                return {
                    "success": False,
                    "message": f"🪔 Your Diya Wicks are already full ({curr}/{settings.STAMINA_BANK_CAP})! Play some games first with /chakri, /rangoli, /mithai or in the Mini App, then claim your +5 refill."
                }
            
            new_wicks = curr + added
            conn.execute("UPDATE users SET diya_wicks = ? WHERE telegram_id = ?", (new_wicks, user_id))
            if is_postgres():
                conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, "1"))
            else:
                try:
                    conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, "1"))
                except Exception:
                    conn.execute("UPDATE system_settings SET value = ? WHERE key = ?", ("1", key))
            from app.cache import delete_cache
            delete_cache(f"setting_{key}")
        return {
            "success": True,
            "added": added,
            "new_wicks": new_wicks,
            "message": (
                "🔥✨ <b>MAHA AARTI MIDNIGHT BLESSING CLAIMED!</b> ✨🔥\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>+{added} Diya Wicks</b> added to your lantern!\n"
                f"• Current Stamina: <b>{new_wicks}/{settings.STAMINA_BANK_CAP} Wicks</b>\n"
                "• <b>2X Sparks</b> on ALL games (3X when your Gharana surges!)\n\n"
                "⚡ <i>The event closes at 12:00 AM IST. Make your final run to Tier 4 Shubhuluk Pet now!</i>"
            )
        }
    finally:
        conn.close()

def get_gharana_boost_status(target_timestamp: Optional[float] = None) -> dict:
    """
    Computes the currently boosted Gharana with 2x points multiplier.
    Rotates every 10 minutes (600 seconds) equally across all 4 Gharanas:
    1: Surya (☀️) -> 2: Agni (🔥) -> 3: Chandra (🌙) -> 4: Vayu (💨) -> repeats.
    Guarantees 100% equal opportunity for all teams with zero bias.
    """
    import time
    now = target_timestamp if target_timestamp is not None else time.time()
    cycle_pos = int(now) % GHARANA_TOTAL_CYCLE_SECONDS
    active_idx = cycle_pos // GHARANA_BOOST_DURATION_SECONDS
    active_id = active_idx + 1
    seconds_remaining = GHARANA_BOOST_DURATION_SECONDS - (cycle_pos % GHARANA_BOOST_DURATION_SECONDS)
    next_id = (active_id % 4) + 1

    return {
        "active_gharana_id": active_id,
        "active_gharana_name": settings.GHARANAS.get(active_id, f"Gharana {active_id}"),
        "active_gharana_emoji": GHARANA_EMOJIS.get(active_id, "🪔"),
        "multiplier": 2,
        "seconds_remaining": seconds_remaining,
        "duration_seconds": GHARANA_BOOST_DURATION_SECONDS,
        "next_gharana_id": next_id,
        "next_gharana_name": settings.GHARANAS.get(next_id, f"Gharana {next_id}"),
        "next_gharana_emoji": GHARANA_EMOJIS.get(next_id, "🪔")
    }

def get_random_wick_cooldown() -> int:
    """Returns a random stamina refill duration between 1 to 3 minutes (60 to 180 seconds).
    During Final Rush, cut in half to 30 to 60 seconds for fast turbo stamina regeneration!"""
    from app.database import get_system_setting
    if get_system_setting("final_rush_active", "0") == "1":
        return random.randint(30, 60)
    return random.randint(60, 180)

def _parse_timestamp(val, default_dt: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
    if not val:
        return default_dt
    if isinstance(val, datetime.datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=datetime.timezone.utc)
        return val.astimezone(datetime.timezone.utc)
    if isinstance(val, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)
        except Exception:
            return default_dt
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return default_dt
        val_clean = val.replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(val_clean)
        except Exception:
            try:
                clean_part = val_clean.split('.')[0].split('+')[0]
                if 'T' in clean_part:
                    dt = datetime.datetime.strptime(clean_part, "%Y-%m-%dT%H:%M:%S")
                else:
                    dt = datetime.datetime.strptime(clean_part, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    f_val = float(val)
                    return datetime.datetime.fromtimestamp(f_val, tz=datetime.timezone.utc)
                except Exception:
                    return default_dt
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
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
    
    try:
        cooldown = int(user["wick_cooldown_seconds"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        cooldown = 0
    if cooldown < 60 or cooldown > 180:
        cooldown = get_random_wick_cooldown()

    last_regen = _parse_timestamp(user["last_wick_regen"], None)
    if last_regen is not None:
        if last_regen.tzinfo is None:
            last_regen = last_regen.replace(tzinfo=datetime.timezone.utc)
        else:
            last_regen = last_regen.astimezone(datetime.timezone.utc)

    # SELF-HEALING: If last_wick_regen is missing, invalid, or corrupted
    if last_regen is None:
        temp_wicks = min(settings.STAMINA_BANK_CAP, current_wicks + 1)
        next_cd = get_random_wick_cooldown()
        now_str = now.isoformat()
        try:
            conn.execute(
                "UPDATE users SET diya_wicks = ?, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?",
                (temp_wicks, now_str, next_cd, telegram_id)
            )
        except Exception:
            conn.execute(
                "UPDATE users SET diya_wicks = ?, last_wick_regen = ? WHERE telegram_id = ?",
                (temp_wicks, now_str, telegram_id)
            )
        try:
            conn.commit()
        except Exception:
            pass
        return temp_wicks

    # CLOCK SKEW / TIMEZONE PROTECTION:
    # If last_regen is recorded in the future, clamp it
    if last_regen > now:
        last_regen = now - datetime.timedelta(seconds=cooldown)

    elapsed_seconds = max(0.0, (now - last_regen).total_seconds())
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
        try:
            conn.commit()
        except Exception:
            pass
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
    parsed_last = _parse_timestamp(user["last_wick_regen"], None)
    try:
        cooldown = int(user["wick_cooldown_seconds"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        cooldown = 0
    if cooldown < 60 or cooldown > 180:
        cooldown = 120

    if parsed_last is None or parsed_last > now:
        return cooldown

    elapsed_seconds = max(0.0, (now - parsed_last).total_seconds())
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
            
        from app.database import get_all_admin_ids
        is_admin_user = (telegram_id in get_all_admin_ids())
        if not is_admin_user and user["shubh_refill_date"] == today_str:
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
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        comm_total = comm["total_sparks"] if comm else 0
        new_stage, _ = get_stage_info(comm_total)
        conn.execute("UPDATE community_state SET current_stage = ? WHERE id = 1", (new_stage,))
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
        u_row = conn.execute("SELECT last_wick_regen FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        raw_regen = u_row["last_wick_regen"] if u_row else None
        if wicks >= settings.STAMINA_BANK_CAP or not raw_regen:
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
        
        user = conn.execute("SELECT points_total, tier_level, gharana_id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        old_points = user["points_total"]
        old_tier = user["tier_level"]
        u_gharana = user["gharana_id"]

        # Calculate 2x Gharana Boost & Final Rush
        boost = get_gharana_boost_status()
        multiplier, is_boosted, is_rush = get_final_rush_multiplier(u_gharana)
        awarded_points = raw_score * multiplier

        try:
            conn.execute(
                "UPDATE game_sessions SET score_awarded = ?, bonus_multiplier = ?, duration_ms = ?, is_valid = 1 WHERE id = ?",
                (raw_score, multiplier, duration_ms, session_id)
            )
        except Exception:
            conn.execute(
                "UPDATE game_sessions SET score_awarded = ?, duration_ms = ?, is_valid = 1 WHERE id = ?",
                (raw_score, duration_ms, session_id)
            )

        new_points = old_points + awarded_points
        new_tier = calculate_tier(new_points)
        tier_unlocked = new_tier > old_tier
        
        conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_points, new_tier, telegram_id))
        conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (awarded_points,))
        
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        comm_total = comm["total_sparks"]
        
        new_stage, stage_name = get_stage_info(comm_total)
        conn.execute("UPDATE community_state SET current_stage = ? WHERE id = 1", (new_stage,))
        
    conn.close()
    
    return {
        "success": True,
        "points_awarded": awarded_points,
        "base_score": raw_score,
        "is_boosted": is_boosted,
        "multiplier": multiplier,
        "is_rush": is_rush,
        "active_gharana_boost": boost,
        "new_user_total": new_points,
        "community_total": comm_total,
        "tier_unlocked": tier_unlocked,
        "new_tier_level": new_tier,
        "tier_name": get_tier_name(new_tier),
        "new_stage": new_stage,
        "stage_description": stage_name
    }

COMMUNITY_GIFT_DAILY_LIMIT = 5
COMMUNITY_GIFT_COOLDOWN_SECONDS = 7200  # 2 hours

def ensure_community_gifts_table():
    from app.database import get_db_connection, is_postgres
    conn = get_db_connection()
    try:
        with conn:
            if is_postgres():
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_community_gifts (
                        id SERIAL PRIMARY KEY,
                        sender_id BIGINT NOT NULL,
                        receiver_id BIGINT NOT NULL,
                        gift_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_comm_gifts_sender ON user_community_gifts (sender_id, gift_date);
                    CREATE INDEX IF NOT EXISTS idx_comm_gifts_pair ON user_community_gifts (sender_id, receiver_id, gift_date);
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_comm_gifts_pair_unique ON user_community_gifts (sender_id, receiver_id, gift_date);
                ''')
            else:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_community_gifts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender_id INTEGER NOT NULL,
                        receiver_id INTEGER NOT NULL,
                        gift_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_comm_gifts_sender ON user_community_gifts (sender_id, gift_date);
                    CREATE INDEX IF NOT EXISTS idx_comm_gifts_pair ON user_community_gifts (sender_id, receiver_id, gift_date);
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_comm_gifts_pair_unique ON user_community_gifts (sender_id, receiver_id, gift_date);
                ''')
    except Exception as e:
        print(f"[ENSURE_GIFTS_TABLE_ERROR]: {e}")
    finally:
        conn.close()

def get_user_gift_status(sender_id: int) -> dict:
    """
    Returns current daily gift quota usage and cooldown status for sender_id.
    """
    import datetime
    from app.database import get_db_connection
    today_str = datetime.date.today().isoformat()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    conn = get_db_connection()
    try:
        try:
            daily_count = conn.execute(
                "SELECT COUNT(*) as c FROM user_community_gifts WHERE sender_id = ? AND gift_date = ?",
                (sender_id, today_str)
            ).fetchone()["c"]
        except Exception as e:
            if "user_community_gifts" in str(e):
                ensure_community_gifts_table()
                daily_count = conn.execute(
                    "SELECT COUNT(*) as c FROM user_community_gifts WHERE sender_id = ? AND gift_date = ?",
                    (sender_id, today_str)
                ).fetchone()["c"]
            else:
                raise
        
        last_gift = conn.execute(
            "SELECT created_at FROM user_community_gifts WHERE sender_id = ? ORDER BY id DESC LIMIT 1",
            (sender_id,)
        ).fetchone()
        
        cooldown_remaining_seconds = 0
        if last_gift:
            last_dt = _parse_timestamp(last_gift["created_at"], now_utc)
            if last_dt:
                elapsed = (now_utc - last_dt).total_seconds()
                if elapsed < COMMUNITY_GIFT_COOLDOWN_SECONDS:
                    cooldown_remaining_seconds = max(0, int(COMMUNITY_GIFT_COOLDOWN_SECONDS - elapsed))
                
        return {
            "daily_limit": COMMUNITY_GIFT_DAILY_LIMIT,
            "gifts_used_today": daily_count,
            "gifts_remaining_today": max(0, COMMUNITY_GIFT_DAILY_LIMIT - daily_count),
            "cooldown_remaining_seconds": cooldown_remaining_seconds,
            "can_gift": (daily_count < COMMUNITY_GIFT_DAILY_LIMIT and cooldown_remaining_seconds == 0)
        }
    finally:
        conn.close()

def execute_community_gift(sender_id: int, target_identifier: str = "", reply_to_id: Optional[int] = None) -> dict:
    """
    Executes gifting 1 Diya Wick from sender_id to recipient.
    Enforces:
    - 5 gifts limit per user per day
    - 2 hours cooldown between gifts
    - 1 gift per recipient per day
    - No self-gifting
    - Recipient must be registered
    - Recipient wick cap check
    """
    import datetime
    import html
    from app.database import get_db_connection
    from app.cache import invalidate_event_cache
    
    target_id = None
    if target_identifier:
        clean = str(target_identifier).strip().lstrip("@")
        if clean.isdigit():
            target_id = int(clean)
        else:
            conn = get_db_connection()
            row = conn.execute("SELECT telegram_id FROM users WHERE LOWER(username) = LOWER(?)", (clean,)).fetchone()
            conn.close()
            if row:
                target_id = row["telegram_id"]
            else:
                return {
                    "success": False,
                    "error": f"❌ Player <b>@{clean}</b> was not found in the festival registry. They must register with @OrdinalLegacyEventBot first!"
                }
    elif reply_to_id and int(reply_to_id) > 0:
        target_id = int(reply_to_id)
    
    if not target_id:
        return {
            "success": False,
            "error": "👉 <b>How to Gift:</b> Reply to any player's message with <code>/gifts</code> or type <code>/gifts &lt;user_id&gt;</code>."
        }
        
    if sender_id == target_id:
        return {
            "success": False,
            "error": "❌ You cannot send a Diya gift to yourself! Share your gifts with fellow Lampbearers in @Ordinal_Legacy."
        }
        
    today_str = datetime.date.today().isoformat()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()
    
    conn = get_db_connection()
    try:
        with conn:
            # Check receiver exists
            receiver = conn.execute("SELECT first_name, username, diya_wicks, last_wick_regen FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not receiver:
                return {
                    "success": False,
                    "error": f"❌ Player <code>{target_id}</code> has not registered for the event yet! Ask them to send /start to @OrdinalLegacyEventBot first."
                }
                
            # Check sender daily quota
            try:
                daily_count = conn.execute(
                    "SELECT COUNT(*) as c FROM user_community_gifts WHERE sender_id = ? AND gift_date = ?",
                    (sender_id, today_str)
                ).fetchone()["c"]
            except Exception as e:
                if "user_community_gifts" in str(e):
                    ensure_community_gifts_table()
                    daily_count = conn.execute(
                        "SELECT COUNT(*) as c FROM user_community_gifts WHERE sender_id = ? AND gift_date = ?",
                        (sender_id, today_str)
                    ).fetchone()["c"]
                else:
                    raise
            
            from app.database import get_all_admin_ids
            is_admin_sender = (sender_id in get_all_admin_ids())

            if not is_admin_sender:
                if daily_count >= COMMUNITY_GIFT_DAILY_LIMIT:
                    return {
                        "success": False,
                        "error": f"⏳ <b>Daily Limit Reached</b>: You have used all <b>{COMMUNITY_GIFT_DAILY_LIMIT} gifts</b> today! Your allowance resets tomorrow at midnight UTC."
                    }
                    
                # Check 2-hour cooldown
                last_gift = conn.execute(
                    "SELECT created_at FROM user_community_gifts WHERE sender_id = ? ORDER BY id DESC LIMIT 1",
                    (sender_id,)
                ).fetchone()
                
                if last_gift:
                    last_dt = _parse_timestamp(last_gift["created_at"], now_utc)
                    if last_dt:
                        elapsed = (now_utc - last_dt).total_seconds()
                        if elapsed < COMMUNITY_GIFT_COOLDOWN_SECONDS:
                            rem = int(COMMUNITY_GIFT_COOLDOWN_SECONDS - elapsed)
                            h = rem // 3600
                            m = (rem % 3600) // 60
                            s = rem % 60
                            time_str = f"{h}h {m}m" if h > 0 else f"{m}m {s}s"
                            return {
                                "success": False,
                                "error": f"⏳ <b>Gift Cooldown Active</b>: Please wait <b>{time_str}</b> before sending your next gift! (2-hour cooldown applies between each gift)."
                            }
                        
                # Check once per day per recipient
                already_gifted = conn.execute(
                    "SELECT id FROM user_community_gifts WHERE sender_id = ? AND receiver_id = ? AND gift_date = ?",
                    (sender_id, target_id, today_str)
                ).fetchone()
                
                r_name = receiver["first_name"] or f"Player_{target_id}"
                if already_gifted:
                    return {
                        "success": False,
                        "error": f"⚠️ You have already gifted <b>{html.escape(r_name)}</b> today! You can only gift each player once per day. Share your gift with someone else!"
                    }
            else:
                r_name = receiver["first_name"] or f"Player_{target_id}" 
                
            # Check recipient stamina capacity
            update_user_stamina(conn, target_id)
            receiver = conn.execute("SELECT first_name, username, diya_wicks, last_wick_regen FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if receiver["diya_wicks"] >= settings.STAMINA_BANK_CAP:
                return {
                    "success": False,
                    "error": f"🪔 <b>{html.escape(r_name)}</b> already has maximum Diya Wicks (<b>10/10</b>)! Send your gift to someone who needs stamina."
                }
                
            # Grant +1 Diya Wick to recipient
            new_wicks = min(settings.STAMINA_BANK_CAP, receiver["diya_wicks"] + 1)
            if not receiver["last_wick_regen"]:
                conn.execute("UPDATE users SET diya_wicks = ?, last_wick_regen = ? WHERE telegram_id = ?", (new_wicks, now_iso, target_id))
            else:
                conn.execute("UPDATE users SET diya_wicks = ? WHERE telegram_id = ?", (new_wicks, target_id))
            
            # Record gift transaction
            conn.execute(
                "INSERT INTO user_community_gifts (sender_id, receiver_id, gift_date, created_at) VALUES (?, ?, ?, ?)",
                (sender_id, target_id, today_str, now_iso)
            )
            
            # Invalidate cache for receiver and sender
            invalidate_event_cache(target_id)
            invalidate_event_cache(sender_id)
            
            new_used = daily_count + 1
            rem_today = max(0, COMMUNITY_GIFT_DAILY_LIMIT - new_used)
            
            return {
                "success": True,
                "receiver_id": target_id,
                "receiver_name": r_name,
                "receiver_wicks": new_wicks,
                "gifts_used_today": new_used,
                "gifts_remaining_today": rem_today
            }
    finally:
        conn.close()
