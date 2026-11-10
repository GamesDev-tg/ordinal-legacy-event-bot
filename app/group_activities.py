import json
import random
import datetime
import html
import re
from typing import Optional, Dict, Any, Tuple, List
from app.config import settings
from app.database import get_db_connection, is_postgres, calculate_tier
from app.cache import invalidate_event_cache

FESTIVE_TRIVIA_QUESTIONS = [
    {
        "question": "What does the sacred word 'Deepavali' literally translate to in Sanskrit?",
        "options": ["Festival of Fireworks", "Row of Sacred Lights", "Dance of Golden Sparks", "Triumph of Seasons"],
        "correct_idx": 1
    },
    {
        "question": "Which divine deity is revered on Dhanteras as the physician of the gods?",
        "options": ["Lord Dhanvantari", "Lord Indra", "Lord Agni", "Lord Varuna"],
        "correct_idx": 0
    },
    {
        "question": "What is the traditional oil most auspiciously poured into earthen Diyas during Diwali?",
        "options": ["Mustard or Sesame Oil", "Olive Oil", "Sunflower Oil", "Coconut Oil"],
        "correct_idx": 0
    },
    {
        "question": "In Hindu tradition, on which day of the 5-day Deepotsav is Bhai Dooj celebrated?",
        "options": ["1st Day", "2nd Day", "3rd Day", "5th Day"],
        "correct_idx": 3
    },
    {
        "question": "In Bitcoin & Ordinal theory, what is the smallest unit of Bitcoin inscribed with artifacts?",
        "options": ["Satoshi", "Gwei", "Finney", "Bit"],
        "correct_idx": 0
    },
    {
        "question": "What sacred geometric floor art welcomes prosperity at doorways during Deepotsav?",
        "options": ["Rangoli", "Madhubani", "Warli", "Mandala"],
        "correct_idx": 0
    },
    {
        "question": "Whose triumphant return to Ayodhya is commemorated by the lighting of Diwali lamps?",
        "options": ["Lord Rama & Sita", "Lord Krishna", "Sage Valmiki", "King Janaka"],
        "correct_idx": 0
    },
    {
        "question": "How many sparks are required to fully ignite the Maha Akhand Jyoti in Ordinal Legacy?",
        "options": ["50,000", "100,000", "200,000", "500,000"],
        "correct_idx": 2
    },
    {
        "question": "Which of our four sacred Gharanas represents the fierce cosmic element of Wind?",
        "options": ["Surya", "Agni", "Chandra", "Vayu"],
        "correct_idx": 3
    },
    {
        "question": "Which divine Goddess of wealth and prosperity is prominently worshipped on Diwali night?",
        "options": ["Goddess Lakshmi", "Goddess Saraswati", "Goddess Durga", "Goddess Kali"],
        "correct_idx": 0
    },
    {
        "question": "On Govardhan Puja, which miraculous divine deed is celebrated?",
        "options": ["Lifting of Govardhan Hill", "Creation of Ayodhya", "Ocean Churning", "Descent of Ganga"],
        "correct_idx": 0
    },
    {
        "question": "Which sacred Gharana in our festival channels the radiant dawn and life-giving sun?",
        "options": ["Surya", "Agni", "Chandra", "Vayu"],
        "correct_idx": 0
    }
]

def ensure_group_events_table():
    conn = get_db_connection()
    try:
        with conn:
            if is_postgres():
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS group_events (
                        id SERIAL PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        message_id BIGINT,
                        data_json TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_group_events_type ON group_events (event_type, is_active);
                ''')
            else:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS group_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        chat_id INTEGER NOT NULL,
                        message_id INTEGER,
                        data_json TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_group_events_type ON group_events (event_type, is_active);
                ''')
    except Exception as e:
        print(f"[ENSURE_GROUP_EVENTS_TABLE_ERROR]: {e}")
    finally:
        conn.close()

def create_flash_diya(chat_id: int, max_claims: int = 10) -> Tuple[int, str, dict]:
    ensure_group_events_table()
    data = {
        "max_claims": max_claims,
        "claimed_uids": [],
        "winners": []
    }
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            if is_postgres():
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('flash_diya', ?, ?, 1) RETURNING id",
                    (chat_id, json.dumps(data))
                )
                row = cur.fetchone()
                event_id = row[0] if row else 1
            else:
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('flash_diya', ?, ?, 1)",
                    (chat_id, json.dumps(data))
                )
                event_id = cur.lastrowid
    finally:
        conn.close()

    text = (
        "🪔✨ <b>MAHA AARTI: SACRED FLASH DIYA AWAKENED!</b> ✨🪔\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "A celestial flame has descended into @Ordinal_Legacy!\n\n"
        f"The first <b>{max_claims} Lampbearers</b> to light their diya will be blessed with:\n"
        "• <b>+1 Diya Wick 🪔</b> (Stamina refill)\n"
        "• <b>+5 Sparks 🔥</b> for the Akhand Jyoti Beacon!\n\n"
        f"👉 <i>Tap the button below to catch the flame! ({max_claims}/{max_claims} sparks remaining)</i>"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": f"🪔 Light the Sacred Diya ({max_claims} left)", "callback_data": f"claim_diya:{event_id}"}]
        ]
    }
    return event_id, text, keyboard

def record_event_message_id(event_id: int, message_id: int):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("UPDATE group_events SET message_id = ? WHERE id = ?", (message_id, event_id))
    except Exception as e:
        print(f"[RECORD EVENT MSG ID ERROR]: {e}")
    finally:
        conn.close()

def claim_flash_diya(event_id: int, user_id: int, first_name: str) -> dict:
    ensure_group_events_table()
    conn = get_db_connection()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()
    try:
        with conn:
            row = conn.execute("SELECT id, chat_id, message_id, data_json, is_active FROM group_events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return {"ok": False, "reason": "not_found", "message": "Sacred flame event not found."}

            if not row["is_active"]:
                return {"ok": False, "reason": "exhausted", "message": "All sacred sparks for this flash drop have already been claimed!"}

            data = json.loads(row["data_json"])
            claimed_uids = data.get("claimed_uids", [])
            if user_id in claimed_uids:
                return {"ok": False, "reason": "already_claimed", "message": "You have already caught this sacred flame!"}

            max_claims = data.get("max_claims", 10)
            if len(claimed_uids) >= max_claims:
                conn.execute("UPDATE group_events SET is_active = 0 WHERE id = ?", (event_id,))
                return {"ok": False, "reason": "exhausted", "message": "All sacred sparks for this flash drop have already been claimed!"}

            # Register user if new
            u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                from app.bot import register_user_if_new
                register_user_if_new(user_id, f"user_{user_id}", first_name)
                u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()

            # Record claim
            claimed_uids.append(user_id)
            safe_fn = re.sub(r'[\r\n\t]+', ' ', first_name).strip() if first_name else f"Lampbearer_{user_id}"
            data["claimed_uids"] = claimed_uids
            data.setdefault("winners", []).append({
                "id": user_id,
                "name": safe_fn,
                "claimed_at": now_iso
            })

            is_completed = (len(claimed_uids) >= max_claims)
            is_active_val = 0 if is_completed else 1
            conn.execute(
                "UPDATE group_events SET data_json = ?, is_active = ? WHERE id = ?",
                (json.dumps(data), is_active_val, event_id)
            )

            # Award +1 Diya Wick (capped at 10) and +5 points
            new_wicks = min(settings.STAMINA_BANK_CAP, (u["diya_wicks"] or 0) + 1)
            new_pts = (u["points_total"] or 0) + 5
            new_tier = calculate_tier(new_pts)
            if not u["last_wick_regen"]:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ?, last_wick_regen = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, now_iso, user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, user_id)
                )

            # Add +5 sparks to community beacon
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + 5 WHERE id = 1")
            
            invalidate_event_cache(user_id)

            remaining = max(0, max_claims - len(claimed_uids))
            return {
                "ok": True,
                "event_id": event_id,
                "chat_id": row["chat_id"],
                "message_id": row["message_id"],
                "remaining": remaining,
                "max_claims": max_claims,
                "is_completed": is_completed,
                "winners": data["winners"],
                "new_wicks": new_wicks,
                "new_pts": new_pts
            }
    finally:
        conn.close()

def create_trivia_drop(chat_id: int, question_override: Optional[dict] = None) -> Tuple[int, str, dict]:
    ensure_group_events_table()
    chosen = question_override if question_override else random.choice(FESTIVE_TRIVIA_QUESTIONS)
    data = {
        "question": chosen["question"],
        "options": chosen["options"],
        "correct_idx": chosen["correct_idx"],
        "attempts": {}, # uid -> chosen_idx
        "winners": []   # max 3 winners
    }
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            if is_postgres():
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('trivia', ?, ?, 1) RETURNING id",
                    (chat_id, json.dumps(data))
                )
                row = cur.fetchone()
                event_id = row[0] if row else 1
            else:
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('trivia', ?, ?, 1)",
                    (chat_id, json.dumps(data))
                )
                event_id = cur.lastrowid
    finally:
        conn.close()

    q_text = html.escape(chosen["question"])
    text = (
        "🏮✨ <b>SACRED FESTIVE TRIVIA FLASH!</b> ✨🏮\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Test your Deepotsav wisdom, Lampbearers!\n"
        "The first <b>3 correct answers</b> win <b>+1 Diya Wick 🪔</b> and <b>+2 Sparks 🔥</b>!\n\n"
        f"❓ <b>Question</b>:\n<b>{q_text}</b>\n\n"
        "<i>Rules: 1 attempt per player • First 3 correct answers win!</i>"
    )
    btn_letters = ["A", "B", "C", "D"]
    rows = []
    # 2x2 grid for buttons
    row1 = []
    row2 = []
    for idx, opt in enumerate(chosen["options"]):
        btn_text = f"{btn_letters[idx]}. {opt}"
        cb_data = f"trivia_ans:{event_id}:{idx}"
        if idx < 2:
            row1.append({"text": btn_text, "callback_data": cb_data})
        else:
            row2.append({"text": btn_text, "callback_data": cb_data})
    rows.append(row1)
    if row2:
        rows.append(row2)

    return event_id, text, {"inline_keyboard": rows}

def answer_trivia_drop(event_id: int, user_id: int, first_name: str, chosen_idx: int) -> dict:
    ensure_group_events_table()
    conn = get_db_connection()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()
    try:
        with conn:
            row = conn.execute("SELECT id, chat_id, message_id, data_json, is_active FROM group_events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return {"ok": False, "reason": "not_found", "message": "Trivia event not found."}

            data = json.loads(row["data_json"])
            attempts = data.get("attempts", {})
            if str(user_id) in attempts:
                return {"ok": False, "reason": "already_attempted", "message": "You have already used your 1 attempt for this trivia!"}

            if not row["is_active"] or len(data.get("winners", [])) >= 3:
                return {"ok": False, "reason": "closed", "message": "This trivia has ended! The top 3 winners have already claimed their rewards."}

            # Record attempt
            attempts[str(user_id)] = chosen_idx
            data["attempts"] = attempts

            correct_idx = data.get("correct_idx", 0)
            if chosen_idx != correct_idx:
                conn.execute("UPDATE group_events SET data_json = ? WHERE id = ?", (json.dumps(data), event_id))
                return {
                    "ok": False,
                    "reason": "wrong",
                    "message": "❌ Incorrect! May the sacred jyoti grant you wisdom for the next flash!"
                }

            # Correct answer!
            # Register user if new
            u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                from app.bot import register_user_if_new
                register_user_if_new(user_id, f"user_{user_id}", first_name)
                u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()

            safe_fn = re.sub(r'[\r\n\t]+', ' ', first_name).strip() if first_name else f"Lampbearer_{user_id}"
            winners = data.get("winners", [])
            winner_rank = len(winners) + 1
            winners.append({
                "id": user_id,
                "name": safe_fn,
                "rank": winner_rank,
                "answered_at": now_iso
            })
            data["winners"] = winners

            is_completed = (len(winners) >= 3)
            is_active_val = 0 if is_completed else 1
            conn.execute(
                "UPDATE group_events SET data_json = ?, is_active = ? WHERE id = ?",
                (json.dumps(data), is_active_val, event_id)
            )

            # Award +1 Wick (capped at 10) and +2 sparks
            new_wicks = min(settings.STAMINA_BANK_CAP, (u["diya_wicks"] or 0) + 1)
            new_pts = (u["points_total"] or 0) + 2
            new_tier = calculate_tier(new_pts)
            if not u["last_wick_regen"]:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ?, last_wick_regen = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, now_iso, user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, user_id)
                )

            # Add +2 sparks to community beacon
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + 2 WHERE id = 1")
            invalidate_event_cache(user_id)

            correct_answer_text = data["options"][correct_idx]
            return {
                "ok": True,
                "reason": "correct",
                "message": f"🎉 Correct answer! (+1 Diya Wick & +2 Sparks awarded! You placed #{winner_rank})",
                "event_id": event_id,
                "chat_id": row["chat_id"],
                "message_id": row["message_id"],
                "winner_rank": winner_rank,
                "is_completed": is_completed,
                "winners": winners,
                "correct_answer": correct_answer_text,
                "question": data["question"]
            }
    finally:
        conn.close()

def get_gharana_clash_card() -> str:
    from app.game_engine import get_gharana_boost_status
    conn = get_db_connection()
    try:
        rows = conn.execute('''
            SELECT u.gharana_id, COUNT(u.id) as members, COALESCE(SUM(u.points_total), 0) as total_pts, COALESCE(AVG(u.points_total), 0) as avg_pts
            FROM users u GROUP BY u.gharana_id
        ''').fetchall()
        
        found = {r["gharana_id"]: r for r in rows}
        complete = []
        emblems = {1: "☀️ Surya", 2: "🔥 Agni", 3: "🌙 Chandra", 4: "💨 Vayu"}
        for gid in [1, 2, 3, 4]:
            if gid in found:
                complete.append({
                    "id": gid,
                    "name": emblems[gid],
                    "members": found[gid]["members"],
                    "total_pts": found[gid]["total_pts"],
                    "avg_pts": float(found[gid]["avg_pts"] or 0)
                })
            else:
                complete.append({
                    "id": gid,
                    "name": emblems[gid],
                    "members": 0,
                    "total_pts": 0,
                    "avg_pts": 0.0
                })
        
        # Sort by total points first, then average
        sorted_gharanas = sorted(complete, key=lambda g: (g["total_pts"], g["avg_pts"]), reverse=True)
    finally:
        conn.close()

    boost = get_gharana_boost_status()
    boost_gid = boost.get("active_gharana_id", 1)
    rem_min = max(0, boost.get("remaining_seconds", 0) // 60)
    rem_sec = max(0, boost.get("remaining_seconds", 0) % 60)
    boost_name = emblems.get(boost_gid, "House")

    medals = ["🥇", "🥈", "🥉", "✨"]
    leaderboard_lines = []
    for idx, g in enumerate(sorted_gharanas):
        is_boosted = (g["id"] == boost_gid)
        boost_tag = " ⚡ [2X SURGE ACTIVE]" if is_boosted else ""
        leaderboard_lines.append(
            f"{medals[idx]} <b>#{idx+1}. {g['name']} Gharana{boost_tag}</b>\n"
            f"   • Total Sparks: <b>{g['total_pts']:,}</b> | Avg: <b>{round(g['avg_pts'], 1)} pts</b> ({g['members']} players)"
        )

    return (
        "⚔️🔥 <b>GHARANA CLASH OF THE SACRED FLAMES</b> 🔥⚔️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Active 2X Surge</b>: <b>{boost_name} Gharana</b>\n"
        f"⏳ <b>Surge Window</b>: {rem_min}m {rem_sec:02d}s remaining before next house rotation!\n\n"
        "🏰 <b>Current House Standings</b>:\n\n" +
        "\n\n".join(leaderboard_lines) +
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🪔 <i>Play mini-games in the bot or mini app to score sparks for your Gharana!</i>"
    )


def create_golden_box_drop(chat_id: int, max_claims: int = 5) -> Tuple[int, str, dict]:
    ensure_group_events_table()
    data = {
        "max_claims": max_claims,
        "claimed_uids": [],
        "winners": []
    }
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            if is_postgres():
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('golden_box', ?, ?, 1) RETURNING id",
                    (chat_id, json.dumps(data))
                )
                row = cur.fetchone()
                event_id = row[0] if row else 1
            else:
                cur.execute(
                    "INSERT INTO group_events (event_type, chat_id, data_json, is_active) VALUES ('golden_box', ?, ?, 1)",
                    (chat_id, json.dumps(data))
                )
                event_id = cur.lastrowid
    finally:
        conn.close()

    text = (
        "🎁✨ <b>MAHA DEEPOTSAV: SACRED GOLDEN BOX DROPPED!</b> ✨🎁\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "A celestial golden chest has appeared in @Ordinal_Legacy!\n\n"
        f"The first <b>{max_claims} Lampbearers</b> to open it will unlock randomized divine blessings:\n"
        "• 🌟 <b>Golden Jackpot (20%)</b>: +5 Diya Wicks & +25 Sparks!\n"
        "• 🔮 <b>Pearl Fortune (40%)</b>: +3 Diya Wicks & +15 Sparks!\n"
        "• 🪙 <b>Silver Shagun (40%)</b>: +2 Diya Wicks & +10 Sparks!\n\n"
        f"👉 <i>Tap below to unlock your lucky chest! ({max_claims}/{max_claims} gifts remaining)</i>"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": f"🎁 Open Sacred Box ({max_claims} left)", "callback_data": f"open_box:{event_id}"}]
        ]
    }
    return event_id, text, keyboard

def claim_golden_box(event_id: int, user_id: int, first_name: str) -> dict:
    ensure_group_events_table()
    conn = get_db_connection()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()
    try:
        with conn:
            row = conn.execute("SELECT id, chat_id, message_id, data_json, is_active FROM group_events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return {"ok": False, "reason": "not_found", "message": "Sacred Golden Box event not found."}

            if not row["is_active"]:
                return {"ok": False, "reason": "exhausted", "message": "All lucky gifts in this Golden Box have already been claimed!"}

            data = json.loads(row["data_json"])
            claimed_uids = data.get("claimed_uids", [])
            if user_id in claimed_uids:
                return {"ok": False, "reason": "already_claimed", "message": "You have already opened this Golden Box!"}

            max_claims = data.get("max_claims", 5)
            if len(claimed_uids) >= max_claims:
                conn.execute("UPDATE group_events SET is_active = 0 WHERE id = ?", (event_id,))
                return {"ok": False, "reason": "exhausted", "message": "All lucky gifts in this Golden Box have already been claimed!"}

            roll = random.random()
            if roll < 0.20:
                reward_tier = "🌟 Golden Jackpot"
                wicks_awarded = 5
                pts_awarded = 25
            elif roll < 0.60:
                reward_tier = "🔮 Pearl Fortune"
                wicks_awarded = 3
                pts_awarded = 15
            else:
                reward_tier = "🪙 Silver Shagun"
                wicks_awarded = 2
                pts_awarded = 10

            u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                from app.bot import register_user_if_new
                register_user_if_new(user_id, f"user_{user_id}", first_name)
                u = conn.execute("SELECT points_total, diya_wicks, tier_level, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()

            claimed_uids.append(user_id)
            safe_fn = re.sub(r'[\r\n\t]+', ' ', first_name).strip() if first_name else f"Player_{user_id}"
            data["claimed_uids"] = claimed_uids
            data.setdefault("winners", []).append({
                "id": user_id,
                "name": safe_fn,
                "reward": reward_tier,
                "wicks": wicks_awarded,
                "sparks": pts_awarded,
                "claimed_at": now_iso
            })

            is_completed = (len(claimed_uids) >= max_claims)
            is_active_val = 0 if is_completed else 1
            conn.execute(
                "UPDATE group_events SET data_json = ?, is_active = ? WHERE id = ?",
                (json.dumps(data), is_active_val, event_id)
            )

            curr_wicks = u["diya_wicks"] or 0
            new_wicks = min(settings.STAMINA_BANK_CAP, curr_wicks + wicks_awarded)
            new_pts = min(5000, (u["points_total"] or 0) + pts_awarded)
            new_tier = calculate_tier(new_pts)

            if not u["last_wick_regen"]:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ?, last_wick_regen = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, now_iso, user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ? WHERE telegram_id = ?",
                    (new_wicks, new_pts, new_tier, user_id)
                )

            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (pts_awarded,))
            invalidate_event_cache(user_id)

            remaining = max(0, max_claims - len(claimed_uids))
            return {
                "ok": True,
                "event_id": event_id,
                "chat_id": row["chat_id"],
                "message_id": row["message_id"],
                "remaining": remaining,
                "max_claims": max_claims,
                "is_completed": is_completed,
                "reward_tier": reward_tier,
                "wicks_awarded": wicks_awarded,
                "pts_awarded": pts_awarded,
                "winners": data["winners"],
                "new_wicks": new_wicks,
                "new_pts": new_pts
            }
    finally:
        conn.close()

def claim_deepotsav_offering(user_id: int, first_name: str) -> dict:
    from app.database import get_system_setting, get_all_admin_ids
    is_admin_user = (user_id in get_all_admin_ids())
    key = f"deepotsav_offered_{user_id}"
    if not is_admin_user and get_system_setting(key, ""):
        return {
            "success": False,
            "message": "🪔 <b>Sacred Flame Already Offered</b>\n\nYou have already placed your Diya on the Maha Akhand Jyoti altar tonight! Thank you for illuminating our community."
        }
    
    conn = get_db_connection()
    try:
        with conn:
            from app.game_engine import update_user_stamina
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT diya_wicks, points_total, tier_level FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"success": False, "message": "❌ User record not found. Send /start to join first!"}
            
            new_wicks = min(settings.STAMINA_BANK_CAP, (u["diya_wicks"] or 0) + 1)
            new_pts = min(5000, (u["points_total"] or 0) + 10)
            new_tier = calculate_tier(new_pts)
            
            conn.execute(
                "UPDATE users SET diya_wicks = ?, points_total = ?, tier_level = ? WHERE telegram_id = ?",
                (new_wicks, new_pts, new_tier, user_id)
            )
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + 25 WHERE id = 1")
            
            if is_postgres():
                conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, "1"))
            else:
                try:
                    conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, "1"))
                except Exception:
                    conn.execute("UPDATE system_settings SET value = ? WHERE key = ?", ("1", key))
            
            from app.cache import delete_cache
            delete_cache(f"setting_{key}")
            invalidate_event_cache(user_id)
            
        return {
            "success": True,
            "message": (
                "🪔✨ <b>MAHA DEEPOTSAV FLAME OFFERING ACCEPTED!</b> ✨🪔\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Your sacred Diya has been placed upon the Maha Akhand Jyoti altar!\n\n"
                "• <b>+1 Diya Wick 🪔</b> (Lantern stamina)\n"
                f"• <b>+10 Personal Points ⚡</b> (Current: {new_pts}/5,000 Pts)\n"
                "• <b>+25 Sparks 🔥</b> offered to the community Akhand Beacon!\n\n"
                "<i>May the divine light guide you to Tier 5 Sovereign glory before midnight!</i>"
            )
        }
    finally:
        conn.close()
