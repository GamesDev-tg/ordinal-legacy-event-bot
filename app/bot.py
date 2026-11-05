import random
import json
import datetime
import secrets
import httpx
from typing import Dict, Any, Optional
from app.config import settings
from app.database import (
    get_db_connection, calculate_tier, get_tier_name, get_stage_info,
    generate_full_backup, reset_event_data
)
from app.referral_engine import process_referral_claim
from app.game_engine import claim_shubh_refill, update_user_stamina

async def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    if settings.BOT_TOKEN == "mock_bot_token_for_dev":
        try:
            print(f"[MOCK BOT] -> Chat {chat_id}: {text}")
        except Exception:
            pass
        return True
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"[TELEGRAM ERROR {resp.status_code}]: {resp.text}")
                # Fallback 1: remove parse_mode if entity parsing failed
                payload.pop("parse_mode", None)
                retry_resp = await client.post(url, json=payload)
                if retry_resp.status_code != 200:
                    # Fallback 2: remove reply_markup if web_app button URL invalid
                    payload.pop("reply_markup", None)
                    last_resp = await client.post(url, json=payload)
                    return last_resp.status_code == 200
                return retry_resp.status_code == 200
            return resp.status_code == 200
    except Exception as e:
        print(f"Failed to send telegram message: {e}")
        return False

async def send_telegram_document(chat_id: int, file_bytes: bytes, filename: str, caption: str):
    if settings.BOT_TOKEN == "mock_bot_token_for_dev":
        print(f"[MOCK BOT] -> Document {filename} to {chat_id}")
        return True
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
    files = {"document": (filename, file_bytes, "application/json")}
    data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "Markdown"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, data=data, files=files)
            return resp.status_code == 200
    except Exception as e:
        print(f"Failed to send telegram document: {e}")
        return False

async def sync_telegram_bot_commands() -> bool:
    """
    Registers all player commands with Telegram BotFather API using setMyCommands.
    Keeps admin commands private so normal players only see official festival features.
    """
    if settings.BOT_TOKEN == "mock_bot_token_for_dev":
        return True
    
    commands = [
        {"command": "start", "description": "Launch festival arena & start event"},
        {"command": "play", "description": "Choose & play mini-games (Chat/App)"},
        {"command": "chakri", "description": "Spin Chakri Whirl in chat (1-3 pts)"},
        {"command": "rangoli", "description": "Draw Rangoli pattern in chat (1-3 pts)"},
        {"command": "mithai", "description": "Feast on Mithai in chat (1-3 pts)"},
        {"command": "mydata", "description": "View your complete stats & tier rewards"},
        {"command": "status", "description": "View community Akhand Diya sparks"},
        {"command": "shubh", "description": "Claim daily Shubh Muhurat (+5 wicks & pts)"},
        {"command": "shagun", "description": "Get companion referral invite link"},
        {"command": "house", "description": "View your Gharana standing & rank"},
        {"command": "top", "description": "View top 10 lampbearers on leaderboard"},
        {"command": "gharanas", "description": "View all 4 Gharana house standings"},
        {"command": "tiers", "description": "View milestone ladder & rewards (Coins, Pearl...)"},
        {"command": "help", "description": "Show festival guide & all commands"}
    ]
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setMyCommands"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"commands": commands})
            return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception as e:
        print(f"Failed to set bot commands: {e}")
        return False

async def check_telegram_membership(user_id: int, chat_identifier: str) -> bool:
    """
    Check if user is a member/admin/creator of a Telegram channel or group.
    Returns True if confirmed member or admin. Returns False otherwise.
    """
    if settings.BOT_TOKEN == "mock_bot_token_for_dev" or user_id in settings.ADMIN_IDS:
        return True
    
    chat_handle = chat_identifier
    if "t.me/" in chat_identifier:
        chat_handle = "@" + chat_identifier.split("t.me/")[-1].strip("/")
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getChatMember"
    params = {"chat_id": chat_handle, "user_id": user_id}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
            if data.get("ok"):
                status = data.get("result", {}).get("status")
                return status in ("creator", "administrator", "member", "restricted")
            else:
                desc = data.get("description", "").lower()
                print(f"[MEMBERSHIP CHECK INFO] {chat_handle} for {user_id}: {data.get('description')}")
                return False
    except Exception as e:
        print(f"[MEMBERSHIP CHECK EXCEPTION]: {e}")
        return False

async def verify_user_all_groups(user_id: int) -> tuple[bool, list]:
    if user_id in settings.ADMIN_IDS:
        return True, []

    groups = [
        (settings.GROUP_NAME_1, settings.GROUP_LINK_1),
        (settings.GROUP_NAME_2, settings.GROUP_LINK_2),
        (settings.GROUP_NAME_3, settings.GROUP_LINK_3),
    ]
    unjoined = []
    for name, link in groups:
        is_member = await check_telegram_membership(user_id, link)
        if not is_member:
            unjoined.append((name, link))
    
    if unjoined:
        return False, unjoined
    return True, []

def register_user_if_new(telegram_id: int, username: str, first_name: str) -> dict:
    conn = get_db_connection()
    with conn:
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not user:
            counts = conn.execute('''
                SELECT g.id, COUNT(u.id) as count 
                FROM (SELECT 1 as id UNION SELECT 2 UNION SELECT 3 UNION SELECT 4) as g
                LEFT JOIN users u ON u.gharana_id = g.id
                GROUP BY g.id ORDER BY count ASC, g.id ASC
            ''').fetchall()
            assigned_gharana = counts[0]["id"] if counts else random.randint(1, 4)
            
            conn.execute(
                '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level, joined_groups)
                   VALUES (?, ?, ?, ?, 0, 10, 0, 0)''',
                (telegram_id, username, first_name, assigned_gharana)
            )
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return dict(user)

def execute_in_chat_game(user_id: int, game_type: int) -> dict:
    conn = get_db_connection()
    try:
        with conn:
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT diya_wicks, points_total, tier_level, gharana_id, joined_groups FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"error": "User not found. Send /start first!"}
            if not u["joined_groups"] and settings.BOT_TOKEN != "mock_bot_token_for_dev":
                return {"error": "You must join all 3 official community groups and verify first! Send /start."}
            if u["diya_wicks"] < 1:
                return {"error": "Out of Diya Wicks! Claim your daily /shubh refill or wait 3 mins for regeneration."}

            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if u["diya_wicks"] >= settings.STAMINA_BANK_CAP:
                conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1, last_wick_regen = ? WHERE telegram_id = ?", (now_str, user_id))
            else:
                conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1 WHERE telegram_id = ?", (user_id,))
            
            # Fair scoring: 3 points (45%), 2 points (40%), 1 point (15%)
            roll = random.random()
            score = 3 if roll < 0.45 else (2 if roll < 0.85 else 1)
            
            new_pts = u["points_total"] + score
            new_tier = calculate_tier(new_pts)
            
            conn.execute(
                "UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?",
                (new_pts, new_tier, user_id)
            )
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (score,))
            
            # Record game session
            sess_id = f"bot_{secrets.token_hex(8)}"
            nonce = secrets.token_hex(8)
            conn.execute(
                '''INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, duration_ms, is_valid)
                   VALUES (?, ?, ?, 'bot_in_chat', ?, ?, 15000, 1)''',
                (sess_id, user_id, game_type, nonce, score)
            )
            
            comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            comm_total = comm["total_sparks"] if comm else 0
            new_wicks = u["diya_wicks"] - 1
        
        return {
            "success": True,
            "score": score,
            "new_pts": new_pts,
            "new_tier": new_tier,
            "tier_name": get_tier_name(new_tier),
            "new_wicks": new_wicks,
            "community_total": comm_total
        }
    except Exception as e:
        print(f"[EXECUTE IN CHAT GAME ERROR]: {e}")
        return {"error": f"Failed to execute game: {str(e)}"}
    finally:
        conn.close()

async def run_in_chat_chakri(chat_id: int, user_id: int):
    try:
        res = execute_in_chat_game(user_id, 1)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "✨ Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}]]}
            )
            return
        score = res["score"]
        sparks = "✨" * (score * 4)
        msg = (
            f"🌀 *CHAKRI WHIRL: SPARK HARVEST!* 🌀\n\n"
            f"You placed the Sacred Golden Ground Chakri on the courtyard stone.\n"
            f"💥 *FZZZZZZT!* It spins at blazing speed, throwing golden flares into the night sky!\n"
            f"{sparks}\n\n"
            f"🏆 *Score Awarded*: `+{score} Hard Sparks`\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "🌀 Spin Chakri Again", "callback_data": "play_chakri"},
                 {"text": "🌸 Draw Rangoli", "callback_data": "play_rangoli"}],
                [{"text": "🍬 Taste Mithai", "callback_data": "play_mithai"},
                 {"text": "🪔 Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "📊 View My Status", "callback_data": "cmd_status"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Chakri*: {str(e)}")

async def run_in_chat_rangoli(chat_id: int, user_id: int):
    try:
        res = execute_in_chat_game(user_id, 2)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "✨ Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}]]}
            )
            return
        score = res["score"]
        msg = (
            f"🌸 *RANGOLI COLOR SYMPHONY!* 🌸\n\n"
            f"You traced the eight-fold lotus pattern with vibrant herbal powders: Vermilion, Haldi & Indigo!\n"
            f"🪔 The divine diya illuminates the courtyard in sacred geometric harmony.\n\n"
            f"🏆 *Score Awarded*: `+{score} Hard Sparks`\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "🌸 Draw Rangoli Again", "callback_data": "play_rangoli"},
                 {"text": "🌀 Spin Chakri", "callback_data": "play_chakri"}],
                [{"text": "🍬 Taste Mithai", "callback_data": "play_mithai"},
                 {"text": "🪔 Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "📊 View My Status", "callback_data": "cmd_status"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Rangoli*: {str(e)}")

async def run_in_chat_mithai(chat_id: int, user_id: int):
    try:
        res = execute_in_chat_game(user_id, 3)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "✨ Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}]]}
            )
            return
        score = res["score"]
        msg = (
            f"🍬 *MITHAI DROP FEAST!* 🍬\n\n"
            f"You gathered the auspicious Diwali Prasad: Motichoor Laddoos, Kaju Katlis & Gulab Jamuns!\n"
            f"✨ Sweet blessings and prosperity shower upon your Gharana.\n\n"
            f"🏆 *Score Awarded*: `+{score} Hard Sparks`\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "🍬 Feast Mithai Again", "callback_data": "play_mithai"},
                 {"text": "🌀 Spin Chakri", "callback_data": "play_chakri"}],
                [{"text": "🌸 Draw Rangoli", "callback_data": "play_rangoli"},
                 {"text": "🪔 Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "📊 View My Status", "callback_data": "cmd_status"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Mithai*: {str(e)}")

async def handle_bot_message(message: Dict[str, Any]):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    text = message.get("text", "").strip()
    
    if not chat_id or not user_id:
        return
    
    username = from_user.get("username", "")
    first_name = from_user.get("first_name", "Lampbearer")
    try:
        user = register_user_if_new(user_id, username, first_name)
    except Exception as e:
        print(f"[REGISTRATION ERROR]: {e}")
        user = {"gharana_id": 1, "points_total": 0, "tier_level": 0, "diya_wicks": 10, "joined_groups": 0}

    # Reset gate test command
    if text in ("/resetgate", "/testgate"):
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 0 WHERE telegram_id = ?", (user_id,))
        conn.close()
        await send_telegram_message(chat_id, "🔄 Group verification gate reset to 0! Send /start now to see the 3 group join buttons.")
        return

    # Mandatory 3 Group Links Gate before entering the game (Applies to all users)
    if not user.get("joined_groups", 0) and text not in ("/verify", "verify") and not text.startswith("/bypassverify"):
        gate_text = (
            f"🪔 *Welcome to Ordinal Legacy Maha Deepotsav, {first_name}!* 🪔\n\n"
            f"Before entering the sacred arena, you must join our 3 official community groups:\n\n"
            f"1️⃣ {settings.GROUP_NAME_1}\n"
            f"2️⃣ {settings.GROUP_NAME_2}\n"
            f"3️⃣ {settings.GROUP_NAME_3}\n\n"
            f"👉 Tap each button below to join, then tap *Verify & Enter Arena*!"
        )
        gate_keyboard = {
            "inline_keyboard": [
                [{"text": f"1️⃣ Join {settings.GROUP_NAME_1}", "url": settings.GROUP_LINK_1}],
                [{"text": f"2️⃣ Join {settings.GROUP_NAME_2}", "url": settings.GROUP_LINK_2}],
                [{"text": f"3️⃣ Join {settings.GROUP_NAME_3}", "url": settings.GROUP_LINK_3}],
                [{"text": "✅ Verify & Enter Arena", "callback_data": "verify_groups"}]
            ]
        }
        await send_telegram_message(chat_id, gate_text, gate_keyboard)
        return

    if text.startswith("/bypassverify"):
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        parts = text.split()
        target_uid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else user_id
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id = ?", (target_uid,))
        conn.close()
        await send_telegram_message(chat_id, f"✅ User `{target_uid}` manually verified! Send /start now.")
        return

    if text in ("/verify", "verify"):
        is_ok, unjoined = await verify_user_all_groups(user_id)
        if not is_ok:
            unjoined_items = "\n".join([f"• {name}" for name, link in unjoined])
            warn_text = (
                f"⚠️ *Verification Incomplete!*\n\n"
                f"We couldn't confirm your membership in:\n"
                f"{unjoined_items}\n\n"
                f"👉 Please join the group(s) above using the buttons below, then tap *Verify & Enter Arena* again!"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": f"👉 Join {name}", "url": link}] for name, link in unjoined
                ] + [[{"text": "✅ Verify & Enter Arena", "callback_data": "verify_groups"}]]
            }
            await send_telegram_message(chat_id, warn_text, kb)
            return

        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id = ?", (user_id,))
            u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        conn.close()
        await send_telegram_message(
            chat_id,
            f"✅ *Verification Confirmed! Welcome to the Deepotsav Arena!* 🎉\n\n"
            f"Initiated into: *{settings.GHARANAS.get(u['gharana_id'], 'Surya Gharana')}*\n"
            f"• Points: *{u['points_total']} Pts*\n"
            f"• Wicks: *{u['diya_wicks']}/10*\n\n"
            f"Choose how you want to play:",
            {
                "inline_keyboard": [
                    [{"text": "🪔 Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                    [{"text": "🎮 Play Mini-Games in Chat", "callback_data": "menu_play"}],
                    [{"text": "🌀 Chakri", "callback_data": "play_chakri"},
                     {"text": "🌸 Rangoli", "callback_data": "play_rangoli"},
                     {"text": "🍬 Mithai", "callback_data": "play_mithai"}],
                    [{"text": "✨ Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}]
                ]
            }
        )
        return
    
    if text.startswith("/start"):
        parts = text.split()
        ref_payload = parts[1] if len(parts) > 1 else None
        
        if ref_payload and ref_payload.startswith("shagun_"):
            try:
                referrer_id = int(ref_payload.replace("shagun_", ""))
                process_referral_claim(referrer_id, user_id)
            except Exception:
                pass
                
        welcome_text = (
            f"🪔 *Welcome to Ordinal Legacy Maha Deepotsav, {first_name}!* 🪔\n\n"
            f"You have been initiated into the *{settings.GHARANAS[user['gharana_id']]}*!\n"
            f"Our sacred goal is to unite and collect *{settings.GLOBAL_MILESTONE_TARGET:,} Sparks* to ignite the community *Akhand Diya*.\n\n"
            f"🎮 *Mini-Games*: Earn 1 to 3 hard points per play.\n"
            f"🤝 *Diya Companion*: Invite 1 friend as your bonded companion for daily free wicks!\n"
            f"✨ *Additional Friends*: Earn +1 minimum point per friend.\n\n"
            f"Tap the button below to launch the festival arena:"
        )
        
        webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "🪔 Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": webapp_url}}],
                [{"text": "🎮 Play Mini-Games in Chat", "callback_data": "menu_play"}],
                [{"text": "🌀 Chakri", "callback_data": "play_chakri"},
                 {"text": "🌸 Rangoli", "callback_data": "play_rangoli"},
                 {"text": "🍬 Mithai", "callback_data": "play_mithai"}],
                [{"text": "👤 My Dossier & Rewards", "callback_data": "cmd_mydata"},
                 {"text": "🎁 Rewards Ladder", "callback_data": "cmd_tiers"}],
                [{"text": "🎁 My Shagun Invite Link", "callback_data": "cmd_shagun"},
                 {"text": "✨ Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}],
                [{"text": "📊 Community Progress", "callback_data": "cmd_status"},
                 {"text": "🏰 Gharanas Leaderboard", "callback_data": "cmd_gharanas"}]
            ]
        }
        await send_telegram_message(chat_id, welcome_text, keyboard)
        return

    elif text == "/play":
        play_text = (
            f"🎮 *Maha Deepotsav Festival Arena: Choose How to Play!*\n\n"
            f"Every run consumes *1 Diya Wick* (max 10, regenerates 1 every 3m).\n"
            f"Earn *1 to 3 hard sparks* per run to ignite the 200,000 Akhand Diya!\n\n"
            f"Select an in-chat game or launch the full Mini-App:"
        )
        play_kb = {
            "inline_keyboard": [
                [{"text": "🪔 Launch Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "🌀 Chakri Whirl (In-Chat)", "callback_data": "play_chakri"},
                 {"text": "🌸 Rangoli Pattern (In-Chat)", "callback_data": "play_rangoli"}],
                [{"text": "🍬 Mithai Feast (In-Chat)", "callback_data": "play_mithai"}],
                [{"text": "✨ Claim Shubh Refill (+5)", "callback_data": "cmd_shubh"},
                 {"text": "👤 My Data & Rewards", "callback_data": "cmd_mydata"}]
            ]
        }
        await send_telegram_message(chat_id, play_text, play_kb)
        return

    elif text == "/chakri":
        await run_in_chat_chakri(chat_id, user_id)
        return

    elif text == "/rangoli":
        await run_in_chat_rangoli(chat_id, user_id)
        return

    elif text == "/mithai":
        await run_in_chat_mithai(chat_id, user_id)
        return

    elif text == "/status":
        conn = get_db_connection()
        update_user_stamina(conn, user_id)
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        u = conn.execute("SELECT points_total, tier_level, diya_wicks, referral_points_earned FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        comp_row = conn.execute(
            '''SELECT u.first_name, u.username, u.tier_level
               FROM referrals r
               JOIN users u ON u.telegram_id = (
                   CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END
               )
               WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1''',
            (user_id, user_id, user_id)
        ).fetchone()
        conn.close()
        
        stage_num, stage_name = get_stage_info(comm["total_sparks"])
        tier_name = get_tier_name(u["tier_level"])
        companion_text = f"*{comp_row['first_name'] or comp_row['username']}* ({get_tier_name(comp_row['tier_level'])})" if comp_row else "_None yet (Invite 1 friend!)_"
        
        status_msg = (
            f"🪔 *Maha Deepotsav Status Report*\n\n"
            f"🔥 *Community Sparks*: `{comm['total_sparks']:,}` / `{settings.GLOBAL_MILESTONE_TARGET:,}`\n"
            f"🌟 *Current Stage*: {stage_name}\n\n"
            f"👤 *Your Profile*:\n"
            f"• Points: *{u['points_total']}*\n"
            f"• Tier: *{tier_name}* (Tier {u['tier_level']})\n"
            f"• Diya Wicks: *{u['diya_wicks']}/10*\n"
            f"• Diya Companion: {companion_text}\n"
            f"• Shagun Points: *{u['referral_points_earned']}/{settings.MAX_REFERRAL_POINTS}*"
        )
        await send_telegram_message(chat_id, status_msg)
        return

    elif text == "/shagun":
        invite_link = f"https://t.me/{settings.BOT_USERNAME}?start=shagun_{user_id}"
        shagun_msg = (
            f"🎁 *Your Diwali Shagun Invite Link:*\n`{invite_link}`\n\n"
            f"• Your *1st active friend* becomes your bonded *Diya Companion*!\n"
            f"• You can exchange daily free Diya Wicks with your companion.\n"
            f"• Extra friends grant *+1 point each* (up to 15 points max)."
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "📲 Share Invite Link", "url": f"https://t.me/share/url?url={invite_link}&text=Join%20me%20in%20the%20Ordinal%20Legacy%20Diwali%20Maha%20Deepotsav!"}]
            ]
        }
        await send_telegram_message(chat_id, shagun_msg, keyboard)
        return

    elif text == "/shubh":
        try:
            res = claim_shubh_refill(user_id)
            await send_telegram_message(chat_id, f"✨ *{res['message']}*")
        except Exception as e:
            await send_telegram_message(chat_id, f"⚠️ {getattr(e, 'detail', str(e))}")
        return

    elif text in ("/widget", "/akhand"):
        conn = get_db_connection()
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        users_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        top_gharanas = conn.execute('''
            SELECT u.gharana_id, COUNT(u.id) as members, AVG(u.points_total) as avg_pts
            FROM users u GROUP BY u.gharana_id
        ''').fetchall()
        conn.close()

        sparks = comm["total_sparks"]
        target = settings.GLOBAL_MILESTONE_TARGET
        pct = min(100.0, (sparks / target) * 100)
        bars = int(pct // 10)
        progress_bar = "🔥" * bars + "▫️" * (10 - bars)
        stage_num, stage_name = get_stage_info(sparks)

        sorted_gharanas = sorted(top_gharanas, key=lambda g: float(g["avg_pts"] or 0), reverse=True)
        gharanas_txt = "\n".join([f"• *{settings.GHARANAS.get(g['gharana_id'])}*: {round(float(g['avg_pts'] or 0), 1)} avg pts ({g['members']} players)" for g in sorted_gharanas])

        widget_msg = (
            f"🪔 *ORDINAL LEGACY: MAHA DEEPOTSAV* 🪔\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 *Akhand Jyoti Community Beacon*\n\n"
            f"🔥 *Sparks Awakened*: `{sparks:,}` / `{target:,}` ({pct:.1f}%)\n"
            f"[{progress_bar}]\n"
            f"📍 *Milestone*: {stage_name}\n"
            f"👥 *Lampbearers Joined*: `{users_count:,}`\n\n"
            f"🏰 *Gharana Standings (Avg Points)*:\n{gharanas_txt}\n\n"
            f"⚡ *Play 3 Diwali Mini-Games* | Earn hard 1–3 points\n"
            f"🤝 *Bind a Diya Companion* for daily wick gifts!"
        )
        webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "🪔 Enter Festival Arena & Light the Flame", "web_app": {"url": webapp_url}}]
            ]
        }
        await send_telegram_message(chat_id, widget_msg, keyboard)
        return

    elif text in ("/gharanas", "/leaderboard"):
        conn = get_db_connection()
        rows = conn.execute('''
            SELECT u.gharana_id, COUNT(u.id) as members, SUM(u.points_total) as pts, AVG(u.points_total) as avg_pts
            FROM users u GROUP BY u.gharana_id
        ''').fetchall()
        conn.close()

        sorted_rows = sorted(rows, key=lambda r: (float(r["avg_pts"] or 0), r["pts"] or 0), reverse=True)
        msg = "🏰 *Maha Deepotsav Gharana Standings:*\n\n"
        for idx, r in enumerate(sorted_rows, 1):
            g_name = settings.GHARANAS.get(r["gharana_id"], f"Gharana {r['gharana_id']}")
            avg_p = round(float(r["avg_pts"] or 0), 1)
            msg += f"*{idx}. {g_name}*\n   • Avg: *{avg_p} Pts* | Total: `{r['pts'] or 0:,} Sparks` | Members: {r['members']}\n\n"
        msg += "_All houses cooperate to ignite the 200,000 Akhand Diya while vying for house honor!_"
        await send_telegram_message(chat_id, msg)
        return

    elif text.startswith("/add"):
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
            
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
            await send_telegram_message(chat_id, "Usage: `/add <telegram_id> <points>`")
            return
            
        target_id = int(parts[1])
        pts = int(parts[2])
        
        conn = get_db_connection()
        with conn:
            target = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not target:
                conn.close()
                await send_telegram_message(chat_id, f"User `{target_id}` not found.")
                return
                
            new_pts = max(0, target["points_total"] + pts)
            new_tier = calculate_tier(new_pts)
            
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, target_id))
            comm_row = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            cur_comm = comm_row["total_sparks"] if comm_row else 0
            new_comm = max(0, cur_comm + pts)
            conn.execute("UPDATE community_state SET total_sparks = ? WHERE id = 1", (new_comm,))
            comm_total = new_comm
        conn.close()
        
        await send_telegram_message(
            chat_id,
            f"✅ *Admin Update*: Added {pts} points to `{target_id}`.\n"
            f"• New User Score: *{new_pts}* ({get_tier_name(new_tier)})\n"
            f"• Community Total: *{comm_total:,} Sparks*"
        )
        return

    elif text.startswith("/query"):
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        
        query_str = text[len("/query"):].strip()
        if not query_str:
            await send_telegram_message(chat_id, "Usage:\n`/query SELECT telegram_id, points_total FROM users LIMIT 5;`\n`/query UPDATE users SET diya_wicks = 10 WHERE telegram_id = 123456;`")
            return
        
        upper_q = query_str.upper()
        if not (upper_q.startswith("SELECT") or upper_q.startswith("UPDATE")):
            await send_telegram_message(chat_id, "⚠️ Only `SELECT` and `UPDATE` queries are permitted.")
            return
        
        forbidden = ["DROP", "ALTER", "ATTACH", "DETACH", "PRAGMA", "VACUUM"]
        if any(f" {kw} " in f" {upper_q} " for kw in forbidden):
            await send_telegram_message(chat_id, "⛔ Destructive keywords are blocked.")
            return
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            if upper_q.startswith("SELECT"):
                cur.execute(query_str)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(10)
                if not rows:
                    await send_telegram_message(chat_id, "ℹ️ Query returned 0 rows.")
                else:
                    col_headers = " | ".join(cols[:5])
                    resp_txt = f"📊 *Query Result ({len(rows)} rows preview):*\n`{col_headers}`\n" + ("—" * 28) + "\n"
                    for r in rows:
                        row_vals = [str(r[i]) for i in range(min(5, len(cols)))]
                        resp_txt += "`" + " | ".join(row_vals) + "`\n"
                    if len(cols) > 5:
                        resp_txt += f"_(Showing 5 of {len(cols)} columns)_\n"
                    await send_telegram_message(chat_id, resp_txt)
            else:
                with conn:
                    cur.execute(query_str)
                    affected = cur.rowcount
                await send_telegram_message(chat_id, f"✅ *Update Executed*: `{affected}` rows affected.")
        except Exception as e:
            await send_telegram_message(chat_id, f"❌ *Query Error*: `{str(e)}`")
        finally:
            conn.close()
        return

    elif text.startswith(("/findtier", "/tierusers")):
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) not in range(6):
            await send_telegram_message(chat_id, "Usage: `/findtier <0-5>`\nExample: `/findtier 5` to view Akhand Sovereigns.")
            return
        
        target_tier = int(parts[1])
        conn = get_db_connection()
        rows = conn.execute('''
            SELECT telegram_id, username, first_name, gharana_id, points_total, diya_wicks
            FROM users
            WHERE tier_level = ?
            ORDER BY points_total DESC, id ASC
            LIMIT 25
        ''', (target_tier,)).fetchall()
        total_count = conn.execute("SELECT COUNT(*) as c FROM users WHERE tier_level = ?", (target_tier,)).fetchone()["c"]
        conn.close()
        
        tier_name = get_tier_name(target_tier)
        msg = f"🏆 *Tier {target_tier}: {tier_name} Players* (Total: {total_count})\n\n"
        if not rows:
            msg += "_No players in this tier yet._"
        else:
            for idx, r in enumerate(rows, 1):
                u_name = f"@{r['username']}" if r['username'] else (r['first_name'] or f"User_{r['telegram_id']}")
                g_name = settings.GHARANAS.get(r['gharana_id'], "")
                msg += f"*{idx}.* {u_name} (`{r['telegram_id']}`)\n   • Points: *{r['points_total']}* | {g_name} | Wicks: {r['diya_wicks']}\n"
            if total_count > 25:
                msg += f"\n_Showing top 25 of {total_count} players._"
        await send_telegram_message(chat_id, msg)
        return

    elif text.startswith("/user"):
        parts = text.split()
        if len(parts) < 2:
            await send_telegram_message(chat_id, "Usage: `/user <telegram_id or username>`")
            return
        
        target = parts[1].lstrip("@")
        conn = get_db_connection()
        if target.isdigit():
            u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (int(target),)).fetchone()
        else:
            u = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (target,)).fetchone()
            
        if not u:
            conn.close()
            await send_telegram_message(chat_id, f"❌ Player `{parts[1]}` not found.")
            return
            
        tid = u["telegram_id"]
        comp_row = conn.execute('''
            SELECT u.telegram_id, u.first_name, u.username, u.tier_level
            FROM referrals r
            JOIN users u ON u.telegram_id = (
                CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END
            )
            WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1
        ''', (tid, tid, tid)).fetchone()
        
        total_refs = conn.execute("SELECT COUNT(*) as c FROM referrals WHERE referrer_id = ?", (tid,)).fetchone()["c"]
        games_count = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND is_valid = 1", (tid,)).fetchone()["c"]
        three_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND score_awarded = 3 AND is_valid = 1", (tid,)).fetchone()["c"]
        conn.close()
        
        comp_str = f"{comp_row['first_name'] or comp_row['username']} (`{comp_row['telegram_id']}`)" if comp_row else "None"
        g_name = settings.GHARANAS.get(u["gharana_id"], "Unknown")
        
        profile_msg = (
            f"👤 *Player Profile: {u['first_name'] or u['username']}*\n\n"
            f"• Telegram ID: `{u['telegram_id']}`\n"
            f"• Username: @{u['username'] or 'N/A'}\n"
            f"• Gharana: *{g_name}*\n"
            f"• Hard Points: *{u['points_total']} Pts*\n"
            f"• Tier: *{get_tier_name(u['tier_level'])}* (Tier {u['tier_level']})\n"
            f"• Diya Wicks: *{u['diya_wicks']}/10*\n"
            f"• Diya Companion: *{comp_str}*\n"
            f"• Friends Invited: *{total_refs}* (Points earned: {u['referral_points_earned']}/{settings.MAX_REFERRAL_POINTS})\n"
            f"• Completed Runs: *{games_count}* (Flawless 3-pt runs: {three_pts})\n"
            f"• Joined: `{u['created_at']}`"
        )
        await send_telegram_message(chat_id, profile_msg)
        return

    elif text in ("/top", "/topusers"):
        conn = get_db_connection()
        rows = conn.execute('''
            SELECT telegram_id, username, first_name, gharana_id, points_total, tier_level
            FROM users
            ORDER BY points_total DESC, id ASC
            LIMIT 10
        ''').fetchall()
        conn.close()
        
        msg = "🌟 *Maha Deepotsav Top 10 Lampbearers:*\n\n"
        medals = ["🥇", "🥈", "🥉"] + ["✨"] * 7
        for idx, r in enumerate(rows):
            raw_name = f"@{r['username']}" if r['username'] else (r['first_name'] or f"User_{r['telegram_id']}")
            safe_name = str(raw_name).replace("_", "\\_").replace("*", "\\*")
            g_name = settings.GHARANAS.get(r['gharana_id'], "")
            msg += f"{medals[idx]} *#{idx+1}. {safe_name}* — *{r['points_total']} Pts*\n   _{get_tier_name(r['tier_level'])} • {g_name}_\n\n"
        await send_telegram_message(chat_id, msg)
        return

    elif text.startswith("/resetwicks"):
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: `/resetwicks <telegram_id>`")
            return
        target_id = int(parts[1])
        conn = get_db_connection()
        with conn:
            u = conn.execute("SELECT first_name FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not u:
                conn.close()
                await send_telegram_message(chat_id, f"❌ Player `{target_id}` not found.")
                return
            conn.execute("UPDATE users SET diya_wicks = ? WHERE telegram_id = ?", (settings.STAMINA_BANK_CAP, target_id))
        conn.close()
        await send_telegram_message(chat_id, f"✅ Restored full Diya Wicks (10/10) for `{target_id}` ({u['first_name']}).")
        return

    elif text == "/backup":
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        snap = generate_full_backup()
        json_bytes = json.dumps(snap, default=str, indent=2).encode("utf-8")
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"ordinal_event_backup_{now_str}.json"
        caption = (
            f"📦 *Ordinal Event Complete Database Backup*\n\n"
            f"• *Timestamp*: `{snap['timestamp_utc']}`\n"
            f"• *Registered Users*: `{snap['total_users']:,}`\n"
            f"• *Referral Bonds*: `{snap['total_referrals']:,}`\n"
            f"• *Game Sessions*: `{snap['total_games']:,}`\n"
            f"• *Akhand Sparks*: `{snap['community_sparks']:,}`\n\n"
            f"🛡️ _Complete JSON snapshot generated with zero data loss._"
        )
        sent = await send_telegram_document(chat_id, json_bytes, filename, caption)
        if not sent:
            await send_telegram_message(chat_id, "⚠️ Backup generated but failed to transmit document. Check server logs.")
        return

    elif text.startswith("/resetevent"):
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) < 2 or parts[1].upper() != "CONFIRM":
            warn_msg = (
                f"⚠️ *CAUTION: Event Reset Requested!*\n\n"
                f"This will reset all player scores to 0, refill wicks to 10, clear game session history, "
                f"and reset community milestone sparks to Stage 0 for a brand new event run.\n\n"
                f"_All user registrations and Gharana house memberships will be preserved._\n\n"
                f"👉 To execute, type:\n`/resetevent CONFIRM`"
            )
            await send_telegram_message(chat_id, warn_msg)
            return

        # Automatic safety backup first
        snap = generate_full_backup()
        json_bytes = json.dumps(snap, default=str, indent=2).encode("utf-8")
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        await send_telegram_document(
            chat_id,
            json_bytes,
            f"pre_reset_backup_{now_str}.json",
            "🛡️ *Pre-Reset Safety Backup Attached*\n_Snapshot saved before event scores were reset._"
        )

        # Perform reset
        reset_event_data()
        await send_telegram_message(
            chat_id,
            f"🔄 *Event Reset Complete!*\n\n"
            f"• All player scores reset to *0 Pts* (Tier 0: Diya Spark)\n"
            f"• All player Diya Wicks reset to *10/10*\n"
            f"• Daily Shubh Refills reset for all users\n"
            f"• Community Akhand Diya reset to *0 Sparks (Stage 0)*\n"
            f"• Gameplay history cleared for fresh event cycle\n\n"
            f"✨ The new event arena is ready for participants!"
        )
        return

    elif text == "/stats":
        conn = get_db_connection()
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        total_runs = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE is_valid = 1").fetchone()["c"]
        three_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 3 AND is_valid = 1").fetchone()["c"]
        two_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 2 AND is_valid = 1").fetchone()["c"]
        one_pt = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 1 AND is_valid = 1").fetchone()["c"]
        companions = conn.execute("SELECT COUNT(*) as c FROM referrals WHERE is_companion = 1").fetchone()["c"]
        wick_gifts = conn.execute("SELECT COUNT(*) as c FROM partner_wick_gifts").fetchone()["c"]
        conn.close()
        
        sparks = comm["total_sparks"]
        target = settings.GLOBAL_MILESTONE_TARGET
        pct = min(100.0, (sparks / target) * 100)
        stage_num, stage_name = get_stage_info(sparks)
        
        stats_msg = (
            f"📊 *Maha Deepotsav Global Statistics*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪔 *Akhand Diya Progress*: `{sparks:,}` / `{target:,}` ({pct:.1f}%)\n"
            f"📍 *Current Stage*: {stage_name}\n"
            f"👥 *Total Lampbearers*: `{total_users:,}`\n"
            f"🎮 *Total Game Runs*: `{total_runs:,}`\n"
            f"   • Flawless (3 Pts): `{three_pts:,}`\n"
            f"   • Skilled (2 Pts): `{two_pts:,}`\n"
            f"   • Base (1 Pt): `{one_pt:,}`\n"
            f"🤝 *Bonded Companions*: `{companions:,}` pairs\n"
            f"🎁 *Companion Wicks Exchanged*: `{wick_gifts:,}`\n"
        )
        await send_telegram_message(chat_id, stats_msg)
        return

    elif text in ("/house", "/mygharana"):
        gid = user["gharana_id"]
        g_name = settings.GHARANAS.get(gid, "Unknown")
        mantras = {
            1: ("Surya Gharana", "☀️", "Lighting the Path of Eternal Truth!"),
            2: ("Agni Gharana", "🔥", "The Pure Cleansing Fire of Transformation!"),
            3: ("Chandra Gharana", "🌙", "The Soothing Luminescence of Sacred Wisdom!"),
            4: ("Vayu Gharana", "💨", "The Unstoppable Current of Swift Victory!")
        }
        info = mantras.get(gid, (g_name, "🪔", "Light the eternal flame!"))
        
        conn = get_db_connection()
        row = conn.execute('''
            SELECT COUNT(*) as members, SUM(points_total) as pts, AVG(points_total) as avg_pts
            FROM users WHERE gharana_id = ?
        ''', (gid,)).fetchone()
        rank_rows = conn.execute('''
            SELECT gharana_id, AVG(points_total) as avg_pts
            FROM users GROUP BY gharana_id
        ''').fetchall()
        conn.close()
        
        sorted_ranks = sorted(rank_rows, key=lambda r: float(r["avg_pts"] or 0), reverse=True)
        house_rank = 1
        for idx, r in enumerate(sorted_ranks, 1):
            if r["gharana_id"] == gid:
                house_rank = idx
                break
                
        avg_house_pts = round(float(row['avg_pts'] or 0.0), 1)
        msg = (
            f"{info[1]} *Your Sacred House: {info[0]}*\n\n"
            f"📜 *House Motto*: _{info[2]}_\n"
            f"🏆 *House Standing*: Rank #{house_rank} of 4\n"
            f"👥 *House Members*: `{row['members']:,}`\n"
            f"⚡ *House Average*: *{avg_house_pts} Pts/member*\n"
            f"🔥 *Total House Sparks*: `{row['pts'] or 0:,}`\n\n"
            f"_Compete with honor and awaken the Akhand Diya for all!_"
        )
        await send_telegram_message(chat_id, msg)
        return

    elif text == "/tiers":
        ladder_text = (
            f"🏆 *Maha Deepotsav Milestone Rewards:*\n\n"
            f"• *Tier 0: Diya Spark (0–249 Pts)* — Welcome Badge\n"
            f"• *Tier 1: Diya Sevak (250 Pts)* — 🪙 Coins\n"
            f"• *Tier 2: Rangoli Artisan (700 Pts)* — 🔮 Pearl\n"
            f"• *Tier 3: Spark Master (1,350 Pts)* — 🎟 Ticket\n"
            f"• *Tier 4: Deep Mahant (2,100 Pts)* — 🧪 Enchant\n"
            f"• *Tier 5: Akhand Sovereign (3,000+ Pts)* — 🐾 Pet (+ All Rewards: 🪙 Coins, 🔮 Pearl, 🎟 Ticket, 🧪 Enchant, 🐾 Pet)\n\n"
            f"_Earn 1 to 3 hard sparks per mini-game run to ascend the ladder!_"
        )
        await send_telegram_message(chat_id, ladder_text)
        return

    elif text in ("/mydata", "/profile", "/data"):
        conn = get_db_connection()
        update_user_stamina(conn, user_id)
        u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        
        comp_row = conn.execute(
            '''SELECT u.first_name, u.username, u.tier_level
               FROM referrals r
               JOIN users u ON u.telegram_id = (
                   CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END
               )
               WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1''',
            (user_id, user_id, user_id)
        ).fetchone()
        
        total_refs = conn.execute("SELECT COUNT(*) as c FROM referrals WHERE referrer_id = ?", (user_id,)).fetchone()["c"]
        total_runs = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND is_valid = 1", (user_id,)).fetchone()["c"]
        three_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND score_awarded = 3 AND is_valid = 1", (user_id,)).fetchone()["c"]
        two_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND score_awarded = 2 AND is_valid = 1", (user_id,)).fetchone()["c"]
        one_pt = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE telegram_id = ? AND score_awarded = 1 AND is_valid = 1", (user_id,)).fetchone()["c"]
        conn.close()
        
        tier = u["tier_level"]
        pts = u["points_total"]
        tier_name = get_tier_name(tier)
        g_name = settings.GHARANAS.get(u["gharana_id"], "Surya Gharana")
        
        # Build reward progression
        rewards_status = []
        for t in [1, 2, 3, 4, 5]:
            req_pts = settings.TIER_THRESHOLDS[t]
            rew_sym = settings.TIER_REWARDS[t]
            if pts >= req_pts:
                rewards_status.append(f"• {rew_sym}: ✅ *Unlocked*")
            else:
                diff = req_pts - pts
                rewards_status.append(f"• {rew_sym}: 🔒 _({diff:,} more pts needed)_")
        rew_text = "\n".join(rewards_status)
        
        comp_str = f"*{comp_row['first_name'] or comp_row['username']}*" if comp_row else "_None yet (Use /shagun)_"
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        shubh_status = "✅ Claimed today" if u["shubh_refill_date"] == today_str else "✨ Available now (/shubh)"
        
        mydata_msg = (
            f"👤 *PLAYER EVENT DOSSIER: {first_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 *Telegram ID*: `{user_id}`\n"
            f"🏷 *Username*: @{username or 'N/A'}\n"
            f"🏰 *Initiated House*: *{g_name}*\n"
            f"🛡 *Official Gate*: {'✅ Verified Member' if u['joined_groups'] else '⚠️ Unverified'}\n\n"
            f"🔥 *Sparks Contributed*: *{pts:,} Sparks*\n"
            f"🏆 *Current Rank Tier*: *{tier_name} (Tier {tier})*\n\n"
            f"🎁 *Reward Milestones:*\n"
            f"{rew_text}\n\n"
            f"🪔 *Diya Wicks*: *{u['diya_wicks']}/10*\n"
            f"⚡ *Stamina Speed*: 1 wick every 3 minutes\n"
            f"✨ *Daily Shubh Muhurat*: {shubh_status}\n\n"
            f"🎮 *Festival Gameplay:*\n"
            f"• Completed Runs: *{total_runs}*\n"
            f"  - Flawless (3 Pts): `{three_pts}`\n"
            f"  - Skilled (2 Pts): `{two_pts}`\n"
            f"  - Base (1 Pt): `{one_pt}`\n\n"
            f"🤝 *Community Bonds:*\n"
            f"• Diya Companion: {comp_str}\n"
            f"• Friends Invited: *{total_refs}* ({u['referral_points_earned']}/{settings.MAX_REFERRAL_POINTS} pts)"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "🎮 Play Mini-Games", "callback_data": "menu_play"},
                 {"text": "🪔 Launch Mini-App", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "🎁 Invite Friends", "callback_data": "cmd_shagun"},
                 {"text": "✨ Daily Refill", "callback_data": "cmd_shubh"}]
            ]
        }
        await send_telegram_message(chat_id, mydata_msg, kb)
        return

    elif text == "/syncbot":
        if user_id not in settings.ADMIN_IDS:
            await send_telegram_message(chat_id, "⛔ *Unauthorized*: Admin privileges required.")
            return
        ok = await sync_telegram_bot_commands()
        if ok:
            await send_telegram_message(chat_id, "✅ *Telegram Bot Commands Synchronized!* All 14 player commands are now visible in the Telegram menu button.")
        else:
            await send_telegram_message(chat_id, "⚠️ Failed to sync commands. Check bot token or server logs.")
        return

    else:
        help_text = (
            f"🪔 *Ordinal Legacy Event Bot Commands:*\n\n"
            f"🎮 *Festival Games:*\n"
            f"/play — Choose games menu (Chat or Mini-App)\n"
            f"/chakri — Spin Chakri Whirl in chat (1 wick, 1-3 pts)\n"
            f"/rangoli — Draw Rangoli in chat (1 wick, 1-3 pts)\n"
            f"/mithai — Feast on Mithai in chat (1 wick, 1-3 pts)\n\n"
            f"🌟 *Event & Profile:*\n"
            f"/mydata — View your complete score, stats & unlocked rewards\n"
            f"/start — Launch festival arena and mini-games\n"
            f"/status — View your points, stamina wicks, and flame stage\n"
            f"/house — View your Gharana house motto, ranking, and avg score\n"
            f"/top — View Top 10 Lampbearers on the leaderboard\n"
            f"/shagun — Get your companion referral link\n"
            f"/shubh — Claim your daily Shubh Muhurat refill (+5 wicks & pts)\n"
            f"/widget — View or generate the pinned channel Akhand Diya widget\n"
            f"/gharanas — View live Gharana house standings\n"
            f"/tiers — View milestone ladder & rewards (Coins, Pearl...)\n"
            f"/findtier <0-5> — View players in a specific reward tier\n"
            f"/user <id/@username> — Inspect user profile details\n"
            f"/stats — View global event metrics and statistics\n"
            f"/help — Show this command menu\n"
        )
        if user_id in settings.ADMIN_IDS:
            help_text += (
                f"\n👑 *Admin Commands:*\n"
                f"`/syncbot` — Synchronize public commands with Telegram BotFather\n"
                f"`/backup` — Download complete database snapshot (.json)\n"
                f"`/resetevent` — Reset scores & sparks for new event cycle\n"
                f"`/query SELECT ...` — Query database\n"
                f"`/query UPDATE ...` — Update database values\n"
                f"`/add <user_id> <points>` — Manually adjust points\n"
                f"`/resetwicks <user_id>` — Restore full wicks (10/10)\n"
            )
        await send_telegram_message(chat_id, help_text)

async def handle_bot_callback_query(callback_query: Dict[str, Any]):
    from_user = callback_query.get("from", {})
    user_id = from_user.get("id")
    chat = callback_query.get("message", {}).get("chat", {})
    chat_id = chat.get("id") or user_id
    data = callback_query.get("data", "")

    if not user_id or not chat_id:
        return

    if data == "verify_groups":
        is_ok, unjoined = await verify_user_all_groups(user_id)
        if not is_ok:
            unjoined_items = "\n".join([f"• {name}" for name, link in unjoined])
            warn_text = (
                f"⚠️ *Verification Incomplete!*\n\n"
                f"We couldn't confirm your membership in:\n"
                f"{unjoined_items}\n\n"
                f"👉 Please join the group(s) above using the buttons below, then tap *Verify & Enter Arena* again!"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": f"👉 Join {name}", "url": link}] for name, link in unjoined
                ] + [[{"text": "✅ Verify & Enter Arena", "callback_data": "verify_groups"}]]
            }
            await send_telegram_message(chat_id, warn_text, kb)
            return

        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE users SET joined_groups = 1 WHERE telegram_id = ?", (user_id,))
            u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        conn.close()
        
        gid = u["gharana_id"] if u else 1
        g_name = settings.GHARANAS.get(gid, "Surya Gharana")
        await send_telegram_message(
            chat_id,
            f"✅ *Verification Confirmed! Welcome to the Arena!* 🎉\n\n"
            f"You are officially initiated into the *{g_name}*!\n"
            f"• Points: *{u['points_total']} Pts*\n"
            f"• Wicks: *{u['diya_wicks']}/10*\n\n"
            f"Choose how you want to play:",
            {
                "inline_keyboard": [
                    [{"text": "🪔 Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                    [{"text": "🎮 Play Mini-Games in Chat", "callback_data": "menu_play"}],
                    [{"text": "🌀 Chakri", "callback_data": "play_chakri"},
                     {"text": "🌸 Rangoli", "callback_data": "play_rangoli"},
                     {"text": "🍬 Mithai", "callback_data": "play_mithai"}],
                    [{"text": "✨ Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": "cmd_shubh"}],
                    [{"text": "🎁 My Shagun Invite Link", "callback_data": "cmd_shagun"}]
                ]
            }
        )
        return

    elif data == "menu_play":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/play"}
        await handle_bot_message(fake_msg)
    elif data == "play_chakri":
        await run_in_chat_chakri(chat_id, user_id)
    elif data == "play_rangoli":
        await run_in_chat_rangoli(chat_id, user_id)
    elif data == "play_mithai":
        await run_in_chat_mithai(chat_id, user_id)

    elif data == "cmd_shagun":
        invite_link = f"https://t.me/{settings.BOT_USERNAME}?start=shagun_{user_id}"
        shagun_msg = (
            f"🎁 *Your Diwali Shagun Invite Link:*\n`{invite_link}`\n\n"
            f"• Your *1st active friend* becomes your bonded *Diya Companion*!\n"
            f"• You can exchange daily free Diya Wicks with your companion.\n"
            f"• Extra friends grant *+1 point each* (up to 15 points max)."
        )
        await send_telegram_message(chat_id, shagun_msg)
    elif data == "cmd_status":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/status"}
        await handle_bot_message(fake_msg)
    elif data == "cmd_mydata":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/mydata"}
        await handle_bot_message(fake_msg)
    elif data == "cmd_shubh":
        try:
            res = claim_shubh_refill(user_id)
            await send_telegram_message(chat_id, f"✨ *{res['message']}*")
        except Exception as e:
            await send_telegram_message(chat_id, f"⚠️ {getattr(e, 'detail', str(e))}")
    elif data == "cmd_gharanas":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/gharanas"}
        await handle_bot_message(fake_msg)
    elif data == "cmd_tiers":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/tiers"}
        await handle_bot_message(fake_msg)
