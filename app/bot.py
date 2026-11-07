import random
import json
import datetime
import time
import secrets
import re
import html
import httpx
import asyncio
import queue
import threading
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List
from app.enums import ParseMode
from app.config import settings

_IS_BROADCASTING = False

_async_http_client: Optional[httpx.AsyncClient] = None

def get_async_http_client() -> httpx.AsyncClient:
    global _async_http_client
    if _async_http_client is None or getattr(_async_http_client, "is_closed", False):
        limits = httpx.Limits(max_keepalive_connections=50, max_connections=100, keepalive_expiry=60.0)
        _async_http_client = httpx.AsyncClient(timeout=10.0, limits=limits)
    return _async_http_client
from app.database import (
    get_db_connection, calculate_tier, get_tier_name, get_stage_info,
    generate_full_backup, reset_event_data, get_all_admin_ids, add_admin_id,
    remove_admin_id, get_effective_logs_chat_id, get_effective_backup_chat_id,
    set_system_setting, get_system_setting, restore_from_backup_data,
    purge_dummy_data, reset_scores_keep_users, refill_all_users_wicks,
    reset_all_shubh_refills
)
from app.referral_engine import process_referral_claim
from app.game_engine import claim_shubh_refill, update_user_stamina
from app.cache import get_cache, set_cache, delete_cache

ALLOWED_HTML_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote", "tg-spoiler"}

def remove_html_tags(text: Any) -> str:
    """Removes all HTML tags from the given string, leaving clean plain text."""
    if text is None:
        return ""
    return re.sub(r'<[^>]*>', '', str(text))

def sanitize_telegram_html(text: Any) -> str:
    """
    Sanitizes HTML for Telegram Bot API:
    - Removes any unsupported/disallowed HTML tags (e.g. <br>, <p>, <div>, <user_id>, etc.)
    - Preserves supported Telegram formatting tags (<b>, <i>, <u>, <s>, <code>, <pre>, <a>, <blockquote>)
    """
    if text is None:
        return ""
    
    def replace_tag(match):
        full_tag = match.group(0)
        tag_name = match.group(1).lower()
        if tag_name in ALLOWED_HTML_TAGS:
            return full_tag
        return ""

    return re.sub(r'<\/?([a-zA-Z0-9\-]+)(?:\s+[^>]*?)?\/?>', replace_tag, str(text))

def format_to_telegram_html(text: Any) -> str:
    """
    Converts text formatted with Markdown (*bold*, `code`, [link](url)) into valid Telegram HTML
    while removing any illegal HTML tags.
    Preserves clean underscores in usernames like @Demonlord_X_02.
    """
    if text is None:
        return ""
    
    s = str(text)
    
    # Clean up accidental escaped underscores so usernames stay clean and clickable
    s = s.replace(r"\_", "_")

    # 1. Convert markdown links: [text](http...) -> <a href="http...">text</a>
    s = re.sub(r'\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)', r'<a href="\2">\1</a>', s)
    
    # 2. Convert inline code: `code` -> <code>code</code>
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    
    # 3. Convert bold: *bold* -> <b>bold</b>
    s = re.sub(r'(?<!\w)\*([^\*\n]+)\*(?!\w)', r'<b>\1</b>', s)

    # 4. Convert italics: _italic_ -> <i>italic</i> (when isolated by spaces/boundaries)
    s = re.sub(r'(?<!\w)_([^_ \n]+)_(?!\w)', r'<i>\1</i>', s)
    
    # 5. Sanitize any unsupported HTML tags
    s = sanitize_telegram_html(s)
    
    return s

def is_mock_token() -> bool:
    tok = (settings.BOT_TOKEN or "").lower()
    return "mock" in tok or tok == "test"

def is_admin(user_id: int) -> bool:
    return user_id in get_all_admin_ids()

def is_user_verified_for_games(user_id: int) -> bool:
    """Checks if user has verified official group membership before playing mini-games."""
    if is_admin(user_id):
        return True
    cached_v = get_cache(f"verified_{user_id}")
    if cached_v is not None:
        return bool(cached_v)
    conn = get_db_connection()
    row = conn.execute("SELECT joined_groups FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    conn.close()
    is_v = bool(row and row["joined_groups"])
    if is_v:
        set_cache(f"verified_{user_id}", True, ttl_seconds=300.0)
    return is_v

def escape_md(text: Any) -> str:
    """Escapes HTML entities safely for Telegram messages while preserving underscores in usernames."""
    if text is None:
        return ""
    s = str(text).replace(r"\_", "_").replace(r"\*", "*")
    return html.escape(s)

_BOT_LOG_QUEUE = queue.Queue(maxsize=3000)
_LOG_WORKER_STARTED = False
_LOG_WORKER_LOCK = threading.Lock()

def _bot_log_worker():
    """
    Dedicated background worker for streaming logs to Telegram Log GC / Store Channel.
    - Non-blocking: API requests and bot commands return in <0.1ms without waiting for Telegram HTTP.
    - Throttling & Batching: batches rapid logs and respects Telegram's 1 msg/sec group limit.
    - Handles HTTP 429 backoff gracefully without failing user operations.
    """
    with httpx.Client(timeout=8.0) as client:
        while True:
            try:
                item = _BOT_LOG_QUEUE.get()
                if item is None:
                    break
                
                logs_chat = get_effective_logs_chat_id() or get_effective_backup_chat_id()
                if logs_chat and not is_mock_token():
                    # Batch up to 3 pending logs if more are waiting in queue
                    batched = [item]
                    while not _BOT_LOG_QUEUE.empty() and len(batched) < 3:
                        try:
                            batched.append(_BOT_LOG_QUEUE.get_nowait())
                        except queue.Empty:
                            break
                    
                    combined_body = "\n\n".join([format_to_telegram_html(b) for b in batched])
                    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": logs_chat, 
                        "text": f"📋 <b>[EVENT BOT LOG]</b>\n{combined_body}", 
                        "parse_mode": ParseMode.HTML.value
                    }
                    try:
                        res = client.post(url, json=payload)
                        if res.status_code == 429:
                            try:
                                retry_after = int(res.json().get("parameters", {}).get("retry_after", 3))
                            except Exception:
                                retry_after = 3
                            time.sleep(retry_after)
                            client.post(url, json=payload)
                        elif res.status_code != 200:
                            plain_body = "\n\n".join([remove_html_tags(b) for b in batched])
                            payload["text"] = f"📋 [EVENT BOT LOG]\n{plain_body}"
                            payload.pop("parse_mode", None)
                            client.post(url, json=payload)
                    except Exception as e:
                        print(f"[BOT LOG WORKER ERROR]: {e}")
                
                _BOT_LOG_QUEUE.task_done()
                time.sleep(0.4)
            except Exception as outer_e:
                print(f"[BOT LOG WORKER LOOP ERROR]: {outer_e}")
                time.sleep(1.0)

def ensure_log_worker_started():
    global _LOG_WORKER_STARTED
    if not _LOG_WORKER_STARTED:
        with _LOG_WORKER_LOCK:
            if not _LOG_WORKER_STARTED:
                t = threading.Thread(target=_bot_log_worker, name="BotLogWorker", daemon=True)
                t.start()
                _LOG_WORKER_STARTED = True

def send_bot_log_sync(text: str):
    try:
        print(f"[BOT LOG]: {text}")
    except Exception:
        try:
            print(f"[BOT LOG]: {text.encode('ascii', 'replace').decode('ascii')}")
        except Exception:
            pass
    logs_chat = get_effective_logs_chat_id() or get_effective_backup_chat_id()
    if logs_chat and not is_mock_token():
        ensure_log_worker_started()
        try:
            _BOT_LOG_QUEUE.put_nowait(text)
        except queue.Full:
            pass

async def send_bot_log(text: str):
    send_bot_log_sync(text)

async def dispatch_backup_snapshot(reason: str = "Manual Admin Snapshot", target_chat_id: Optional[int] = None) -> bool:
    snap = generate_full_backup()
    json_bytes = json.dumps(snap, default=str, indent=2).encode("utf-8")
    now = datetime.datetime.now(datetime.timezone.utc)
    now_str = now.strftime("%Y%m%d_%H%M%S")
    filename = f"ordinal_event_backup_{now_str}.json"
    
    caption = (
        f"🛡️ *MAHA DEEPOTSAV DATA RECOVERY SNAPSHOT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Trigger*: {reason}\n"
        f"👥 *Total Players*: `{snap['total_users']:,}`\n"
        f"🔥 *Community Sparks*: `{snap['community_sparks']:,}`\n"
        f"🎮 *Valid Game Runs*: `{snap['total_games']:,}`\n"
        f"🤝 *Referral Bonds*: `{snap['total_referrals']:,}`\n"
        f"⏰ *Timestamp*: `{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`\n\n"
        f"_Automated recovery snapshot created with zero data loss._"
    )
    
    dest_chats = set()
    configured_backup = get_effective_backup_chat_id()
    if configured_backup:
        dest_chats.add(configured_backup)
    if target_chat_id:
        dest_chats.add(target_chat_id)
        
    sent_any = False
    for cid in dest_chats:
        ok = await send_telegram_document(cid, json_bytes, filename, caption)
        if ok:
            sent_any = True
            
    # Update timestamp in system_settings
    set_system_setting("last_backup_time", now.isoformat())
    await send_bot_log(f"📦 *Data Recovery Snapshot Dispatched*: Reason: `{reason}`. Saved `{snap['total_users']}` users, `{snap['community_sparks']}` sparks.")
    return sent_any

_last_backup_check_time = 0

async def check_and_trigger_auto_backup() -> bool:
    global _last_backup_check_time
    import time
    now_ts = time.time()
    if now_ts - _last_backup_check_time < 300:
        return False
    _last_backup_check_time = now_ts

    backup_chat = get_effective_backup_chat_id()
    if not backup_chat:
        return False
    
    last_str = get_system_setting("last_backup_time")
    now = datetime.datetime.now(datetime.timezone.utc)
    if last_str:
        try:
            last_dt = datetime.datetime.fromisoformat(last_str)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
            if (now - last_dt).total_seconds() < 6 * 3600:
                return False
        except Exception:
            pass
            
    return await dispatch_backup_snapshot(reason="Automated 6-Hour Recovery Cycle")

_last_ref_reconcile_time = 0

def check_and_trigger_referral_reconciliation():
    global _last_ref_reconcile_time
    now = time.time()
    if now - _last_ref_reconcile_time > 300:
        _last_ref_reconcile_time = now
        from app.referral_engine import reconcile_all_referrals
        try:
            res = reconcile_all_referrals()
            if res.get("synced_users", 0) > 0:
                print(f"[REFERRAL JOB]: Auto-reconciled {res['synced_users']} user accounts.")
        except Exception as e:
            print(f"[REFERRAL JOB ERROR]: {e}")

async def send_telegram_message(
    chat_id: int, 
    text: str, 
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = ParseMode.HTML.value
):
    if is_mock_token():
        try:
            print(f"[MOCK BOT] -> Chat {chat_id}: {text}")
        except Exception:
            pass
        return True
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    
    if parse_mode in (ParseMode.HTML.value, "HTML"):
        formatted_text = format_to_telegram_html(text)
    else:
        formatted_text = text

    payload = {"chat_id": chat_id, "text": formatted_text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        client = get_async_http_client()
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            print(f"[TELEGRAM ERROR {resp.status_code}]: {resp.text}")
            # Fallback 1: remove all HTML tags completely and drop parse_mode
            payload["text"] = remove_html_tags(text)
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

async def send_telegram_message_with_id(
    chat_id: int, 
    text: str, 
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = ParseMode.HTML.value
) -> Tuple[bool, Optional[int]]:
    if is_mock_token():
        try:
            print(f"[MOCK BOT] -> Chat {chat_id}: {text}")
        except Exception:
            pass
        return True, 999999
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    formatted_text = format_to_telegram_html(text) if parse_mode in (ParseMode.HTML.value, "HTML") else text
    payload = {"chat_id": chat_id, "text": formatted_text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        client = get_async_http_client()
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            msg_id = resp.json().get("result", {}).get("message_id")
            return True, msg_id
        return False, None
    except Exception as e:
        print(f"[SEND TELEGRAM WITH ID ERROR]: {e}")
        return False, None

async def edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[Dict[str, Any]] = None,
    parse_mode: Optional[str] = ParseMode.HTML.value
) -> bool:
    if is_mock_token():
        return True
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/editMessageText"
    formatted_text = format_to_telegram_html(text) if parse_mode in (ParseMode.HTML.value, "HTML") else text
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": formatted_text,
        "parse_mode": parse_mode
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        client = get_async_http_client()
        resp = await client.post(url, json=payload)
        return resp.status_code == 200
    except Exception as e:
        print(f"[EDIT TELEGRAM MESSAGE ERROR]: {e}")
        return False

async def send_telegram_document(chat_id: int, file_bytes: bytes, filename: str, caption: str):
    if is_mock_token():
        print(f"[MOCK BOT] -> Document {filename} to {chat_id}")
        return True
    
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
    files = {"document": (filename, file_bytes, "application/json")}
    formatted_caption = format_to_telegram_html(caption)
    data = {"chat_id": str(chat_id), "caption": formatted_caption, "parse_mode": ParseMode.HTML.value}
    try:
        client = get_async_http_client()
        resp = await client.post(url, data=data, files=files)
        if resp.status_code != 200:
            data["caption"] = remove_html_tags(caption)
            data.pop("parse_mode", None)
            retry_resp = await client.post(url, data=data, files=files)
            return retry_resp.status_code == 200
        return resp.status_code == 200
    except Exception as e:
        print(f"Failed to send telegram document: {e}")
        return False

# In-memory anti-spam rate limiter for button clicks
_BUTTON_CLICK_COOLDOWN: Dict[int, float] = {}

async def answer_telegram_callback_query(callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> bool:
    """Answers a Telegram callback query to clear button loading spinners and optionally show alert."""
    if is_mock_token() or not callback_query_id:
        return True
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    try:
        client = get_async_http_client()
        resp = await client.post(url, json=payload)
        return resp.status_code == 200
    except Exception as e:
        print(f"Failed to answer telegram callback query: {e}")
        return False

async def sync_telegram_bot_commands() -> bool:
    """
    Registers all player commands with Telegram BotFather API using setMyCommands.
    Keeps admin commands private so normal players only see official festival features.
    """
    if is_mock_token():
        return True
    
    commands = [
        {"command": "start", "description": "Launch festival arena and start event"},
        {"command": "play", "description": "Choose and play mini-games (Chat/App)"},
        {"command": "chakri", "description": "Spin Chakri Whirl in chat (1-3 pts)"},
        {"command": "rangoli", "description": "Draw Rangoli pattern in chat (1-3 pts)"},
        {"command": "mithai", "description": "Feast on Mithai in chat (1-3 pts)"},
        {"command": "mydata", "description": "View your stats and tier rewards"},
        {"command": "status", "description": "View community Akhand Diya sparks"},
        {"command": "shubh", "description": "Claim daily Shubh refill (+5 wicks & pts)"},
        {"command": "shagun", "description": "Get companion referral invite link"},
        {"command": "house", "description": "View your Gharana standing and rank"},
        {"command": "boost", "description": "View 10-min 2x Gharana Surge schedule"},
        {"command": "top", "description": "View top 10 lampbearers on leaderboard"},
        {"command": "gharanas", "description": "View all 4 Gharana house standings"},
        {"command": "tiers", "description": "View milestone ladder and rewards"},
        {"command": "help", "description": "Show festival guide and commands"}
    ]
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setMyCommands"
    try:
        client = get_async_http_client()
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
    if is_mock_token() or is_admin(user_id):
        return True
    
    chat_handle = chat_identifier.strip()
    if "t.me/" in chat_handle:
        chat_handle = "@" + chat_handle.split("t.me/")[-1].strip("/")
    if not chat_handle.startswith("@") and not str(chat_handle).startswith("-100"):
        chat_handle = "@" + chat_handle

    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getChatMember"
    params = {"chat_id": chat_handle, "user_id": user_id}
    try:
        client = get_async_http_client()
        resp = await client.get(url, params=params)
        data = resp.json()
        if data.get("ok"):
            status = data.get("result", {}).get("status")
            if status in ("creator", "administrator", "member", "restricted"):
                return True
            
            # If status is left or kicked, check if the bot is even an administrator in this group.
            # If the bot is NOT an administrator, getChatMember is unreliable and Telegram forbids
            # non-admin bots from accessing group participant statuses.
            bot_check_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getChatAdministrators"
            admin_resp = await client.get(bot_check_url, params={"chat_id": chat_handle})
            admin_data = admin_resp.json()
            if not admin_data.get("ok"):
                print(f"[MEMBERSHIP PASS] Permitted {chat_handle} for {user_id} (bot lacks admin access to verify)")
                return True
            
            admins = admin_data.get("result", [])
            bot_is_admin = any(
                a.get("user", {}).get("is_bot") and 
                a.get("user", {}).get("username", "").lower() == (settings.BOT_USERNAME or "ordinallegacyeventbot").lower() 
                for a in admins
            )
            if not bot_is_admin:
                print(f"[MEMBERSHIP PASS] Permitted {chat_handle} for {user_id} (bot is not group admin)")
                return True
            
            return False
        else:
            desc = data.get("description", "").lower()
            print(f"[MEMBERSHIP CHECK INFO] {chat_handle} for {user_id}: {data.get('description')}")
            bypass_errors = [
                "chat not found", "not a member", "forbidden", "not enough rights",
                "inaccessible", "admin_required", "administrator rights", "channel_private",
                "user not found", "participant_id_invalid", "method is available only",
                "user_not_participant", "user is not a member", "chat_admin_required",
                "bot is not a member", "peer_id_invalid", "bad request: user_not_participant"
            ]
            if any(err in desc for err in bypass_errors) or "ordinallegacyeventinfo" in chat_handle.lower():
                print(f"[MEMBERSHIP PASS] Permitted {chat_handle} for {user_id} (API bypass: {desc})")
                return True
            return False
    except Exception as e:
        print(f"[MEMBERSHIP CHECK EXCEPTION]: {e}")
        return True

async def verify_user_all_groups(user_id: int) -> tuple[bool, list]:
    if is_admin(user_id):
        return True, []

    groups = [
        (settings.GROUP_NAME_1, settings.GROUP_LINK_1),
        (settings.GROUP_NAME_2, settings.GROUP_LINK_2),
        (settings.GROUP_NAME_3, settings.GROUP_LINK_3),
    ]
    unjoined = []
    results = await asyncio.gather(
        *(check_telegram_membership(user_id, link) for _, link in groups),
        return_exceptions=True
    )
    for (name, link), res in zip(groups, results):
        if res is not True:
            unjoined.append((name, link))
    
    if unjoined:
        return False, unjoined
    return True, []

def register_user_if_new(telegram_id: int, username: str, first_name: str) -> dict:
    cache_key = f"reg_user_{telegram_id}"
    cached = get_cache(cache_key)
    if cached is not None and (not username or cached.get("username") == username):
        return cached
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
            
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            from app.game_engine import get_random_wick_cooldown
            init_cd = get_random_wick_cooldown()
            try:
                conn.execute(
                    '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level, joined_groups, last_wick_regen, wick_cooldown_seconds)
                       VALUES (?, ?, ?, ?, 0, 10, 0, 0, ?, ?)''',
                    (telegram_id, username, first_name, assigned_gharana, now_iso, init_cd)
                )
            except Exception:
                conn.execute(
                    '''INSERT INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks, tier_level, joined_groups, last_wick_regen)
                       VALUES (?, ?, ?, ?, 0, 10, 0, 0, ?)''',
                    (telegram_id, username, first_name, assigned_gharana, now_iso)
                )
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        else:
            # Dynamically update username or first_name if changed or missing
            need_update = False
            cur_username = user["username"] or ""
            cur_first_name = user["first_name"] or ""
            if username and username != cur_username:
                cur_username = username
                need_update = True
            if first_name and first_name != cur_first_name and first_name != "Lampbearer":
                cur_first_name = first_name
                need_update = True
            if need_update:
                conn.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                    (cur_username, cur_first_name, telegram_id)
                )
                user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        res_user = dict(user)
    conn.close()
    set_cache(cache_key, res_user, ttl_seconds=60.0)
    return res_user

def execute_in_chat_game(user_id: int, game_type: int) -> dict:
    conn = get_db_connection()
    try:
        with conn:
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT diya_wicks, points_total, tier_level, gharana_id, joined_groups, last_wick_regen FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"error": "User not found. Send /start first!"}
            if not u["joined_groups"] and not is_admin(user_id) and not is_mock_token():
                return {"error": "You must join all 3 official community groups and verify first! Send /start."}
            if u["diya_wicks"] < 1:
                return {"error": "Out of Diya Wicks! Claim your daily /shubh refill or wait 1–3 mins for stamina regeneration."}

            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if u["diya_wicks"] >= settings.STAMINA_BANK_CAP or not u["last_wick_regen"]:
                from app.game_engine import get_random_wick_cooldown
                next_cd = get_random_wick_cooldown()
                try:
                    conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?", (now_str, next_cd, user_id))
                except Exception:
                    conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1, last_wick_regen = ? WHERE telegram_id = ?", (now_str, user_id))
            else:
                conn.execute("UPDATE users SET diya_wicks = diya_wicks - 1 WHERE telegram_id = ?", (user_id,))
            
            # Fair scoring: 3 points (45%), 2 points (40%), 1 point (15%)
            roll = random.random()
            base_score = 3 if roll < 0.45 else (2 if roll < 0.85 else 1)
            
            # Check active Gharana 2x Boost
            from app.game_engine import get_gharana_boost_status
            boost = get_gharana_boost_status()
            is_boosted = (u["gharana_id"] == boost["active_gharana_id"])
            multiplier = 2 if is_boosted else 1
            awarded_score = base_score * multiplier
            
            new_pts = u["points_total"] + awarded_score
            new_tier = calculate_tier(new_pts)
            
            conn.execute(
                "UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?",
                (new_pts, new_tier, user_id)
            )
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (awarded_score,))
            
            # Record game session (base_score 1-3 preserves CHECK constraint; multiplier recorded in bonus_multiplier)
            sess_id = f"bot_{secrets.token_hex(8)}"
            nonce = secrets.token_hex(8)
            try:
                conn.execute(
                    '''INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, bonus_multiplier, duration_ms, is_valid)
                       VALUES (?, ?, ?, 'bot_in_chat', ?, ?, ?, 15000, 1)''',
                    (sess_id, user_id, game_type, nonce, base_score, multiplier)
                )
            except Exception:
                conn.execute(
                    '''INSERT INTO game_sessions (id, telegram_id, game_type, seed, nonce, score_awarded, duration_ms, is_valid)
                       VALUES (?, ?, ?, 'bot_in_chat', ?, ?, 15000, 1)''',
                    (sess_id, user_id, game_type, nonce, base_score)
                )
            
            comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            comm_total = comm["total_sparks"] if comm else 0
            new_stage, _ = get_stage_info(comm_total)
            conn.execute("UPDATE community_state SET current_stage = ? WHERE id = 1", (new_stage,))
            new_wicks = u["diya_wicks"] - 1

        from app.cache import invalidate_event_cache
        invalidate_event_cache(user_id)
        
        return {
            "success": True,
            "score": awarded_score,
            "base_score": base_score,
            "is_boosted": is_boosted,
            "multiplier": multiplier,
            "active_boost": boost,
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

def is_ordinal_legacy_group(chat: dict) -> bool:
    if not chat or chat.get("type") == "private":
        return False
    username = (chat.get("username") or "").lower().lstrip("@")
    if username in ("ordinal_legacy", "ordinallegacy"):
        return True
    title = (chat.get("title") or "").lower()
    if "ordinal_legacy" in title or "ordinal legacy" in title or "common discussion" in title or ("ordinal" in title and "legacy" in title):
        return True
    cid = str(chat.get("id", ""))
    cfg_id = str(getattr(settings, "ORDINAL_LEGACY_CHAT_ID", "") or "")
    if cfg_id and cid == cfg_id:
        return True
    glink_handle = (getattr(settings, "GROUP_LINK_3", "") or "").split("t.me/")[-1].strip("/").lower()
    if glink_handle and (glink_handle == username or glink_handle in cid):
        return True
    return False

async def send_captcha_prompt(chat_id: int, user_id: int, reason: str = ""):
    from app.captcha_engine import get_or_create_captcha
    challenge = get_or_create_captcha(user_id)
    token = challenge.get("short_token") or challenge["token"]
    opts = challenge["options"]
    row1 = [
        {"text": opts[0], "callback_data": f"cpa:{user_id}:0:{token}"},
        {"text": opts[1], "callback_data": f"cpa:{user_id}:1:{token}"}
    ]
    row2 = [
        {"text": opts[2], "callback_data": f"cpa:{user_id}:2:{token}"},
        {"text": opts[3], "callback_data": f"cpa:{user_id}:3:{token}"}
    ]
    header = "🔒 *Sacred Jyoti Human Verification*\n\n"
    if reason:
        header += f"_{reason}_\n\n"
    header += f"{challenge['question']}\n\n👉 *Tap the correct option below to verify human presence:*"
    await send_telegram_message(chat_id, header, {"inline_keyboard": [row1, row2]})

async def run_in_chat_chakri(chat_id: int, user_id: int):
    from app.database import is_event_paused
    if is_event_paused() and not is_admin(user_id):
        await send_telegram_message(
            chat_id,
            "⏳ <b>Festival Arena Paused for Score Auditing</b>\n\n"
            "The festival arena has been temporarily paused by administrators for final score auditing and winner verification.\n\n"
            "• You can still view your final dossier and rank via /mydata and /top!\n"
            "• Stay tuned for the official winners and reward distribution announcement!"
        )
        return
    if not is_user_verified_for_games(user_id):
        gate_text = (
            "⚠️ <b>Verification Required!</b>\n\n"
            "Active membership in all 3 official community groups is required to play festival mini-games.\n\n"
            "👉 Please join the groups below and tap <b>Verify & Enter Arena</b>:"
        )
        gate_kb = {
            "inline_keyboard": [
                [{"text": f"1. Join {settings.GROUP_NAME_1}", "url": settings.GROUP_LINK_1}],
                [{"text": f"2. Join {settings.GROUP_NAME_2}", "url": settings.GROUP_LINK_2}],
                [{"text": f"3. Join {settings.GROUP_NAME_3}", "url": settings.GROUP_LINK_3}],
                [{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, gate_text, gate_kb)
        return
    from app.captcha_engine import is_user_captcha_locked, record_game_play_and_check_captcha
    if is_user_captcha_locked(user_id):
        await send_captcha_prompt(chat_id, user_id, "Automated action prevention: Please verify human presence.")
        return
    try:
        res = execute_in_chat_game(user_id, 1)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": f"cmd_shubh:{user_id}"}]]}
            )
            return
        score = res["score"]
        sparks = "✨" * (score * 3)
        boost_info = res.get("active_boost", {})
        if res.get("is_boosted"):
            boost_header = f"⚡ *MAHA GHARANA 2X SURGE APPLIED!* ⚡\n_Divine blessings! Your house {boost_info.get('active_gharana_name')} receives 2X Sparks!_\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks` ⚡ *(Base: +{res['base_score']} × 2 Boost!)*"
        else:
            rem_m = max(1, boost_info.get("seconds_remaining", 0) // 60)
            boost_header = f"⚡ *Active 2x House*: {boost_info.get('active_gharana_emoji', '')} {boost_info.get('active_gharana_name', '')} ({rem_m}m remaining)\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks`"

        msg = (
            f"🌀 *CHAKRI WHIRL: SPARK HARVEST!* 🌀\n\n"
            f"{boost_header}"
            f"You placed the Sacred Golden Ground Chakri on the courtyard stone.\n"
            f"💥 *FZZZZZZT!* It spins at blazing speed, throwing golden flares into the night sky!\n"
            f"{sparks}\n\n"
            f"{score_text}\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "Spin Chakri Again", "callback_data": f"play_chakri:{user_id}"},
                 {"text": "Draw Rangoli", "callback_data": f"play_rangoli:{user_id}"}],
                [{"text": "Taste Mithai", "callback_data": f"play_mithai:{user_id}"},
                 {"text": "Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "View My Status", "callback_data": f"cmd_status:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
        await send_bot_log(f"🌀 Player `{user_id}` spun Chakri Whirl (+{score} Sparks). Total: {res['new_pts']} Pts | Community: {res['community_total']:,} Sparks")
        if record_game_play_and_check_captcha(user_id):
            await send_captcha_prompt(chat_id, user_id, "Routine security check: Please solve this sacred verification before your next turn:")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Chakri*: {str(e)}")

async def run_in_chat_rangoli(chat_id: int, user_id: int):
    from app.database import is_event_paused
    if is_event_paused() and not is_admin(user_id):
        await send_telegram_message(
            chat_id,
            "⏳ <b>Festival Arena Paused for Score Auditing</b>\n\n"
            "The festival arena has been temporarily paused by administrators for final score auditing and winner verification.\n\n"
            "• You can still view your final dossier and rank via /mydata and /top!\n"
            "• Stay tuned for the official winners and reward distribution announcement!"
        )
        return
    if not is_user_verified_for_games(user_id):
        gate_text = (
            "⚠️ <b>Verification Required!</b>\n\n"
            "Active membership in all 3 official community groups is required to play festival mini-games.\n\n"
            "👉 Please join the groups below and tap <b>Verify & Enter Arena</b>:"
        )
        gate_kb = {
            "inline_keyboard": [
                [{"text": f"1. Join {settings.GROUP_NAME_1}", "url": settings.GROUP_LINK_1}],
                [{"text": f"2. Join {settings.GROUP_NAME_2}", "url": settings.GROUP_LINK_2}],
                [{"text": f"3. Join {settings.GROUP_NAME_3}", "url": settings.GROUP_LINK_3}],
                [{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, gate_text, gate_kb)
        return
    from app.captcha_engine import is_user_captcha_locked, record_game_play_and_check_captcha
    if is_user_captcha_locked(user_id):
        await send_captcha_prompt(chat_id, user_id, "Automated action prevention: Please verify human presence.")
        return
    try:
        res = execute_in_chat_game(user_id, 2)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": f"cmd_shubh:{user_id}"}]]}
            )
            return
        score = res["score"]
        boost_info = res.get("active_boost", {})
        if res.get("is_boosted"):
            boost_header = f"⚡ *MAHA GHARANA 2X SURGE APPLIED!* ⚡\n_Divine blessings! Your house {boost_info.get('active_gharana_name')} receives 2X Sparks!_\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks` ⚡ *(Base: +{res['base_score']} × 2 Boost!)*"
        else:
            rem_m = max(1, boost_info.get("seconds_remaining", 0) // 60)
            boost_header = f"⚡ *Active 2x House*: {boost_info.get('active_gharana_emoji', '')} {boost_info.get('active_gharana_name', '')} ({rem_m}m remaining)\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks`"

        msg = (
            f"🌸 *RANGOLI COLOR SYMPHONY!* 🌸\n\n"
            f"{boost_header}"
            f"You traced the eight-fold lotus pattern with vibrant herbal powders: Vermilion, Haldi & Indigo!\n"
            f"🪔 The divine diya illuminates the courtyard in sacred geometric harmony.\n\n"
            f"{score_text}\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "Draw Rangoli Again", "callback_data": f"play_rangoli:{user_id}"},
                 {"text": "Spin Chakri", "callback_data": f"play_chakri:{user_id}"}],
                [{"text": "Taste Mithai", "callback_data": f"play_mithai:{user_id}"},
                 {"text": "Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "View My Status", "callback_data": f"cmd_status:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
        await send_bot_log(f"🌸 Player `{user_id}` traced Rangoli (+{score} Sparks). Total: {res['new_pts']} Pts | Community: {res['community_total']:,} Sparks")
        if record_game_play_and_check_captcha(user_id):
            await send_captcha_prompt(chat_id, user_id, "Routine security check: Please solve this sacred verification before your next turn:")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Rangoli*: {str(e)}")

async def run_in_chat_mithai(chat_id: int, user_id: int):
    from app.database import is_event_paused
    if is_event_paused() and not is_admin(user_id):
        await send_telegram_message(
            chat_id,
            "⏳ <b>Festival Arena Paused for Score Auditing</b>\n\n"
            "The festival arena has been temporarily paused by administrators for final score auditing and winner verification.\n\n"
            "• You can still view your final dossier and rank via /mydata and /top!\n"
            "• Stay tuned for the official winners and reward distribution announcement!"
        )
        return
    if not is_user_verified_for_games(user_id):
        gate_text = (
            "⚠️ <b>Verification Required!</b>\n\n"
            "Active membership in all 3 official community groups is required to play festival mini-games.\n\n"
            "👉 Please join the groups below and tap <b>Verify & Enter Arena</b>:"
        )
        gate_kb = {
            "inline_keyboard": [
                [{"text": f"1. Join {settings.GROUP_NAME_1}", "url": settings.GROUP_LINK_1}],
                [{"text": f"2. Join {settings.GROUP_NAME_2}", "url": settings.GROUP_LINK_2}],
                [{"text": f"3. Join {settings.GROUP_NAME_3}", "url": settings.GROUP_LINK_3}],
                [{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, gate_text, gate_kb)
        return
    from app.captcha_engine import is_user_captcha_locked, record_game_play_and_check_captcha
    if is_user_captcha_locked(user_id):
        await send_captcha_prompt(chat_id, user_id, "Automated action prevention: Please verify human presence.")
        return
    try:
        res = execute_in_chat_game(user_id, 3)
        if "error" in res:
            await send_telegram_message(
                chat_id,
                f"⚠️ *{res['error']}*",
                {"inline_keyboard": [[{"text": "Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": f"cmd_shubh:{user_id}"}]]}
            )
            return
        score = res["score"]
        boost_info = res.get("active_boost", {})
        if res.get("is_boosted"):
            boost_header = f"⚡ *MAHA GHARANA 2X SURGE APPLIED!* ⚡\n_Divine blessings! Your house {boost_info.get('active_gharana_name')} receives 2X Sparks!_\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks` ⚡ *(Base: +{res['base_score']} × 2 Boost!)*"
        else:
            rem_m = max(1, boost_info.get("seconds_remaining", 0) // 60)
            boost_header = f"⚡ *Active 2x House*: {boost_info.get('active_gharana_emoji', '')} {boost_info.get('active_gharana_name', '')} ({rem_m}m remaining)\n\n"
            score_text = f"🏆 *Score Awarded*: `+{score} Hard Sparks`"

        msg = (
            f"🍬 *MITHAI DROP FEAST!* 🍬\n\n"
            f"{boost_header}"
            f"You gathered the auspicious Diwali Prasad: Motichoor Laddoos, Kaju Katlis & Gulab Jamuns!\n"
            f"✨ Sweet blessings and prosperity shower upon your Gharana.\n\n"
            f"{score_text}\n"
            f"👤 *Your Total*: *{res['new_pts']} Pts* ({res['tier_name']})\n"
            f"🪔 *Diya Wicks Remaining*: *{res['new_wicks']}/10*\n"
            f"🔥 *Community Akhand Diya*: `{res['community_total']:,} Sparks`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "Feast Mithai Again", "callback_data": f"play_mithai:{user_id}"},
                 {"text": "Spin Chakri", "callback_data": f"play_chakri:{user_id}"}],
                [{"text": "Draw Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                 {"text": "Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "View My Status", "callback_data": f"cmd_status:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, msg, kb)
        await send_bot_log(f"🍬 Player `{user_id}` caught Mithai (+{score} Sparks). Total: {res['new_pts']} Pts | Community: {res['community_total']:,} Sparks")
        if record_game_play_and_check_captcha(user_id):
            await send_captcha_prompt(chat_id, user_id, "Routine security check: Please solve this sacred verification before your next turn:")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ *Error playing Mithai*: {str(e)}")

async def handle_bot_message(message: Dict[str, Any]):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    is_private = (chat_type == "private")
    from_user = message.get("from", {})
    user_id = from_user.get("id")
    text = message.get("text", "").strip()
    doc = message.get("document")
    
    if not chat_id or not user_id:
        return

    if not is_private and is_ordinal_legacy_group(chat):
        set_system_setting("ordinal_legacy_group_chat_id", str(chat_id))

    # Ignore service messages, chat member joins/leaves, or empty text without document
    if not text and not doc:
        return

    # Ignore service notifications when bot or user joins/leaves groups
    if (message.get("new_chat_members") or message.get("new_chat_participant") or 
        message.get("left_chat_member") or message.get("left_chat_participant") or 
        message.get("group_chat_created") or message.get("supergroup_chat_created") or
        message.get("channel_chat_created") or message.get("pinned_message")):
        return

    # In groups/supergroups/channels: NEVER reply to regular chat chatter! Only explicit slash commands.
    if not is_private and not text.startswith("/"):
        return

    # Normalize group commands with bot username suffix and lower-case command token
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd_part = parts[0]
        rest_part = f" {parts[1]}" if len(parts) > 1 else ""
        if "@" in cmd_part:
            cmd_name, at_target = cmd_part.split("@", 1)
            bot_user = (settings.BOT_USERNAME or "OrdinalLegacyEventBot").lstrip("@").lower()
            target_clean = at_target.lstrip("@").lower()
            if bot_user and target_clean != bot_user and "ordinal" not in target_clean:
                # Command targeted at another bot in the group; ignore silently
                return
            text = f"{cmd_name.lower()}{rest_part}".strip()
        else:
            text = f"{cmd_part.lower()}{rest_part}".strip()

    # Guard: in groups, only public community readouts are allowed for regular members.
    # Authorized administrators are allowed to execute administrative & event management commands directly in groups.
    # Regular users running personal, interactive, game, help, or admin commands are directed to DM to avoid group spam.
    if not is_private and text.startswith("/"):
        cmd_head = text.split()[0].lower()
        ALLOWED_GROUP_COMMANDS = {
            "/top", "/tops", "/topusers", "/status", "/gharanas", "/leaderboard", 
            "/tiers", "/stats", "/captcha", "/testcaptcha", "/eventstatus", "/pausestatus",
            "/adminstats", "/userstats", "/playerstats", "/eventstats", "/boost",
            "/gifts", "/gift", "/clash", "/gharanaclash"
        }
        ADMIN_COMMANDS = {
            "/admin", "/adminhelp", "/admins", "/addadmin", "/deladmin",
            "/userinfo", "/user", "/setpoints", "/addpoints", "/add",
            "/setwicks", "/resetwicks", "/refillallwicks", "/resetallwicks",
            "/setgharana", "/bypassverify", "/unverify", "/setcaptcha",
            "/unlockcaptcha", "/clearcaptcha", "/unlockallcaptcha",
            "/deleteuser", "/broadcast", "/setsparks", "/settarget",
            "/setlogschat", "/setlogs", "/setlog", "/setbackupchat", "/setbackup", "/getchats", "/testlog", "/testlogs",
            "/backup", "/snapshot", "/restore",
            "/stopevent", "/pauseevent", "/resumeevent", "/startevent", "/unpauseevent",
            "/eventstatus", "/pausestatus", "/auditscores", "/tierusers", "/tierplayers",
            "/findtier", "/exportrewards",
            "/adminstats", "/userstats", "/playerstats", "/eventstats",
            "/resetscores", "/resetpoints", "/resetshubh", "/resetallshubh",
            "/resetevent", "/cleandummy", "/purgedummy", "/syncreferrals",
            "/resetreferrals", "/query", "/syncbot",
            "/dropdiya", "/flashdiya", "/droptrivia", "/riddle"
        }
        is_user_admin = is_admin(user_id)
        if cmd_head in ADMIN_COMMANDS:
            if not is_user_admin:
                await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
                await send_bot_log(f"🚨 *Security Alert*: Unauthorized user `{user_id}` attempted `{cmd_head}` in group.")
                return
            # Authorized administrator running admin command in group: allowed to proceed
        elif cmd_head in ALLOWED_GROUP_COMMANDS:
            # Public community readout allowed in group for all members
            pass
        else:
            # Check if this command belongs to this bot at all
            ALL_KNOWN_BOT_COMMANDS = {
                "/start", "/play", "/chakri", "/rangoli", "/mithai",
                "/mydata", "/profile", "/data", "/shubh", "/shagun",
                "/help", "/commands", "/menu", "/house", "/mygharana",
                "/akhand", "/widget", "/verify", "/resetgate", "/testgate",
                "/gifts", "/gift", "/clash", "/gharanaclash"
            }
            if cmd_head not in ALL_KNOWN_BOT_COMMANDS:
                # Silently ignore commands intended for other bots or group admins (/price, /ban, /buy, etc.)
                return

            bot_user = settings.BOT_USERNAME or "OrdinalLegacyEventBot"
            await send_telegram_message(
                chat_id,
                f"👉 Please use `{cmd_head}` in private chat with [@{bot_user}](https://t.me/{bot_user}) to avoid group spam."
            )
            return
    
    username = from_user.get("username", "")
    first_name = from_user.get("first_name", "Lampbearer")
    try:
        user = register_user_if_new(user_id, username, first_name)
    except Exception as e:
        print(f"[REGISTRATION ERROR]: {e}")
        user = {"gharana_id": 1, "points_total": 0, "tier_level": 0, "diya_wicks": 10, "joined_groups": 0}

    # 1. Non-blocking background 6-hour automatic backup check & periodic referral reconciliation job
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(check_and_trigger_auto_backup())
        loop.run_in_executor(None, check_and_trigger_referral_reconciliation)
    except (RuntimeError, Exception):
        pass

    # 2. Early Referral Capture: process referral parameters immediately upon /start, /shagun or /bind
    # This ensures new players who click invite links have their referral recorded BEFORE any group gate!
    if text.startswith(("/start", "/shagun", "/bind")):
        parts = text.split()
        if len(parts) > 1:
            ref_payload = parts[1].strip()
            referrer_id = None
            if ref_payload.startswith("shagun_"):
                raw_id = ref_payload.replace("shagun_", "")
                if raw_id.isdigit():
                    referrer_id = int(raw_id)
            elif ref_payload.startswith("ref_"):
                raw_id = ref_payload.replace("ref_", "")
                if raw_id.isdigit():
                    referrer_id = int(raw_id)
            elif ref_payload.isdigit():
                referrer_id = int(ref_payload)
            
            if referrer_id and referrer_id == user_id:
                await send_telegram_message(
                    chat_id,
                    "⚠️ *Self-Referral Detected*\nYou cannot refer yourself with your own Shagun link. Share your link with friends to earn points and bond companions!"
                )
                if not text.startswith("/start"):
                    return
            elif referrer_id and referrer_id != user_id:
                try:
                    ref_res = process_referral_claim(referrer_id, user_id)
                    print(f"[REFERRAL SUCCESS]: Player {user_id} successfully bound to referrer {referrer_id}")
                    raw_friend_tag = f"@{username}" if username else first_name
                    friend_tag = escape_md(raw_friend_tag)
                    ref_name = escape_md(ref_res.get("referrer_name", f"Player {referrer_id}"))
                    if ref_res.get("is_companion"):
                        await send_telegram_message(
                            referrer_id,
                            f"🤝 *New Diya Companion Bound!* 🎉\n\n"
                            f"Your friend *{friend_tag}* joined through your Shagun link and is now your permanent Diya Companion!\n"
                            f"• You earned: *+1 Hard Point*\n"
                            f"• You can now send each other free daily Diya Wicks!"
                        )
                        await send_telegram_message(
                            chat_id,
                            f"🤝 *Diya Companion Bond Formed!*\n\n"
                            f"You are now bonded with *{ref_name}* as Diya Companions!\n"
                            f"• Your inviter earned: *+1 Point*\n"
                            f"• You can now exchange free daily Diya Wicks via `/shagun`!"
                        )
                        await send_bot_log(f"🤝 *Companion Bound*: `{user_id}` ({raw_friend_tag}) bound with `{referrer_id}` (+1 Pt).")
                    else:
                        await send_telegram_message(
                            referrer_id,
                            f"🎁 *New Lampbearer Joined!* 🪔\n\n"
                            f"Your friend *{friend_tag}* joined through your link! (+1 Point added, total: {ref_res.get('referral_points_earned')}/{settings.MAX_REFERRAL_POINTS})."
                        )
                        await send_telegram_message(
                            chat_id,
                            f"🎁 *Shagun Invite Accepted!*\n\n"
                            f"You joined through *{ref_name}*'s Shagun invite link! +1 Point has been credited to their festival score."
                        )
                        await send_bot_log(f"🎁 *Referral Claimed*: `{user_id}` ({raw_friend_tag}) referred by `{referrer_id}` (+1 Pt).")
                    
                    if text.startswith(("/shagun", "/bind")):
                        return
                except Exception as e:
                    detail = getattr(e, "detail", str(e))
                    print(f"[REFERRAL CLAIM INFO]: {detail}")
                    await send_telegram_message(chat_id, f"ℹ️ *Referral Notice*: {detail}")
                    if text.startswith(("/shagun", "/bind")):
                        return

    # 2. Check for document upload with /restore
    caption = message.get("caption", "").strip()
    if doc and caption.startswith("/restore"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required to restore backups.")
            await send_bot_log(f"🚨 *Security Alert*: Non-admin `{user_id}` attempted to upload `/restore` file.")
            return

        file_id = doc.get("file_id")
        file_name = doc.get("file_name", "backup.json")
        try:
            get_file_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                res_info = await client.get(get_file_url)
                file_path = res_info.json().get("result", {}).get("file_path")
                if not file_path:
                    await send_telegram_message(chat_id, "❌ Could not retrieve file path from Telegram.")
                    return
                down_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"
                file_resp = await client.get(down_url)
                backup_data = file_resp.json()

            res_restored = restore_from_backup_data(backup_data)
            success_msg = (
                f"✅ *Database Restored from File: {file_name}* 🎉\n\n"
                f"• Restored Players: *{res_restored['users_restored']}*\n"
                f"• Restored Referrals: *{res_restored['referrals_restored']}*\n"
                f"• Restored Game Runs: *{res_restored['games_restored']}*\n\n"
                f"All player scores, wicks, and community sparks are fully operational."
            )
            await send_telegram_message(chat_id, success_msg)
            await send_bot_log(f"🔄 *Database Restored*: Admin `{user_id}` restored `{file_name}` ({res_restored['users_restored']} players).")
            return
        except Exception as e:
            await send_telegram_message(chat_id, f"❌ *Restore Failed*: Invalid JSON or schema error: `{str(e)}`")
            return

    # Reset gate test command
    if text in ("/resetgate", "/testgate"):
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 0 WHERE telegram_id = ?", (user_id,))
        conn.close()
        await send_telegram_message(chat_id, "🔄 Group verification gate reset to 0! Send /start now to see the 3 group join buttons.")
        return

    # Public commands that anyone can run even before joining groups:
    allowed_unverified = (
        "/verify", "verify", "/help", "/commands", "/menu", "/tiers",
        "/status", "/mydata", "/profile", "/data", "/top", "/tops", "/topusers",
        "/gharanas", "/leaderboard", "/stats", "/shagun", "/bind",
        "/captcha", "/testcaptcha", "/verifyhuman", "/boost", "/gifts", "/gift",
        "/clash", "/gharanaclash"
    )

    # Mandatory 3 Group Links Gate before entering the game (Applies to all users unless admin or running info commands)
    cmd_head_check = text.split()[0].lower() if text else ""
    if not user.get("joined_groups", 0) and not is_admin(user_id) and cmd_head_check not in allowed_unverified and not text.startswith(("/bypassverify", "/admin")):
        if is_private:
            safe_fname = escape_md(first_name)
            gate_text = (
                f"🪔 *Welcome to Ordinal Legacy Maha Deepotsav, {safe_fname}!* 🪔\n\n"
                f"Before entering the sacred arena, you must join our 3 official community groups:\n\n"
                f"1️⃣ {settings.GROUP_NAME_1}\n"
                f"2️⃣ {settings.GROUP_NAME_2}\n"
                f"3️⃣ {settings.GROUP_NAME_3}\n\n"
                f"👉 Tap each button below to join, then tap *Verify & Enter Arena*!"
            )
            gate_keyboard = {
                "inline_keyboard": [
                    [{"text": f"1. Join {settings.GROUP_NAME_1}", "url": settings.GROUP_LINK_1}],
                    [{"text": f"2. Join {settings.GROUP_NAME_2}", "url": settings.GROUP_LINK_2}],
                    [{"text": f"3. Join {settings.GROUP_NAME_3}", "url": settings.GROUP_LINK_3}],
                    [{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]
                ]
            }
            await send_telegram_message(chat_id, gate_text, gate_keyboard)
        else:
            bot_user = settings.BOT_USERNAME or "OrdinalLegacyEventBot"
            await send_telegram_message(chat_id, f"👉 Please use `/start` in private chat with [@{bot_user}](https://t.me/{bot_user}) to verify and enter the festival arena.")
        return

    if text.startswith("/bypassverify"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
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
            unjoined_items = "\n".join([f"• {html.escape(name)}" for name, link in unjoined])
            warn_text = (
                f"⚠️ <b>Verification Incomplete!</b>\n\n"
                f"We couldn't confirm your membership in:\n"
                f"{unjoined_items}\n\n"
                f"👉 Please join the group(s) above using the buttons below, then tap <b>Verify & Enter Arena</b> again!"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": f"Join {name}", "url": link}] for name, link in unjoined
                ] + [[{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]]
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
                    [{"text": "Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                    [{"text": "Play Mini-Games in Chat", "callback_data": f"menu_play:{user_id}"}],
                    [{"text": "Play Chakri", "callback_data": f"play_chakri:{user_id}"},
                     {"text": "Play Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                     {"text": "Play Mithai", "callback_data": f"play_mithai:{user_id}"}],
                    [{"text": "Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": f"cmd_shubh:{user_id}"}]
                ]
            }
        )
        return
    
    if text.startswith("/start"):
        safe_fname = escape_md(first_name)
        welcome_text = (
            f"🪔 *Welcome to Ordinal Legacy Maha Deepotsav, {safe_fname}!* 🪔\n\n"
            f"You have been initiated into the *{settings.GHARANAS[user['gharana_id']]}*!\n"
            f"Our sacred goal is to unite and collect *{settings.GLOBAL_MILESTONE_TARGET:,} Sparks* to ignite the community *Akhand Diya*.\n\n"
            f"• Mini-Games: /chakri, /rangoli, /mithai (1 to 3 hard points per play)\n"
            f"• Diya Companion: /shagun (Invite 1 friend as your bonded companion for daily free wicks!)\n"
            f"• Daily Refill: /shubh (Claim daily bonus wicks and sparks)\n"
            f"• Profile & Rewards: /mydata\n\n"
            f"Tap the buttons below to play:"
        )
        
        webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": webapp_url}}],
                [{"text": "Play Mini-Games in Chat", "callback_data": f"menu_play:{user_id}"}],
                [{"text": "Play Chakri", "callback_data": f"play_chakri:{user_id}"},
                 {"text": "Play Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                 {"text": "Play Mithai", "callback_data": f"play_mithai:{user_id}"}],
                [{"text": "My Dossier & Rewards", "callback_data": f"cmd_mydata:{user_id}"},
                 {"text": "Rewards Ladder", "callback_data": f"cmd_tiers:{user_id}"}],
                [{"text": "My Shagun Invite Link", "callback_data": f"cmd_shagun:{user_id}"},
                 {"text": "Claim Shubh Refill", "callback_data": f"cmd_shubh:{user_id}"}],
                [{"text": "Community Status", "callback_data": f"cmd_status:{user_id}"},
                 {"text": "Gharanas Leaderboard", "callback_data": f"cmd_gharanas:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, welcome_text, keyboard)
        return

    elif text == "/play":
        from app.database import is_event_paused
        if is_event_paused() and not is_admin(user_id):
            await send_telegram_message(
                chat_id,
                "⏳ <b>Festival Arena Paused for Score Auditing</b>\n\n"
                "The festival arena has been temporarily paused by administrators for final score auditing and winner verification.\n\n"
                "• You can still view your final dossier and rank via /mydata and /top!\n"
                "• Stay tuned for the official winners and reward distribution announcement!"
            )
            return
        from app.captcha_engine import is_user_captcha_locked
        if is_user_captcha_locked(user_id):
            await send_captcha_prompt(chat_id, user_id, "Automated action prevention: Please verify human presence before entering the arena.")
            return
        from app.game_engine import get_gharana_boost_status
        boost = get_gharana_boost_status()
        rem_m = boost["seconds_remaining"] // 60
        rem_s = boost["seconds_remaining"] % 60
        u_gid = user.get("gharana_id", 1)
        is_my_gharana = (u_gid == boost["active_gharana_id"])
        
        if is_my_gharana:
            boost_highlight = (
                f"⚡ *2X GHARANA SURGE ACTIVE FOR YOUR HOUSE!* 🔥\n"
                f"• Boost House: {boost['active_gharana_emoji']} *{boost['active_gharana_name']}*\n"
                f"• Time Remaining: `{rem_m:02d}:{rem_s:02d}` (10-minute rotation)\n"
                f"• Multiplier: *2X SPARKS on every play!* (Up to +6 pts)\n\n"
            )
        else:
            boost_highlight = (
                f"⚡ *Active 2x Surge*: {boost['active_gharana_emoji']} *{boost['active_gharana_name']}* (`{rem_m:02d}:{rem_s:02d}` left)\n"
                f"⏳ Next House: {boost['next_gharana_emoji']} {boost['next_gharana_name']}\n\n"
            )

        play_text = (
            f"🎮 *Maha Deepotsav Festival Arena: Choose How to Play!*\n\n"
            f"{boost_highlight}"
            f"Every run consumes *1 Diya Wick* (max 10, regenerates 1 every 1–3 mins randomly).\n"
            f"Earn *1 to 3 hard sparks* per run (doubled to 2–6 pts during 2x boost) to ignite the 200,000 Akhand Diya!\n\n"
            f"Select an in-chat game or launch the full Mini-App:"
        )
        play_kb = {
            "inline_keyboard": [
                [{"text": "Launch Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "Play Chakri Whirl", "callback_data": f"play_chakri:{user_id}"},
                 {"text": "Play Rangoli Pattern", "callback_data": f"play_rangoli:{user_id}"}],
                [{"text": "Play Mithai Feast", "callback_data": f"play_mithai:{user_id}"}],
                [{"text": "View 2x Boost Schedule", "callback_data": f"cmd_boost:{user_id}"}],
                [{"text": "Claim Shubh Refill", "callback_data": f"cmd_shubh:{user_id}"},
                 {"text": "My Data & Rewards", "callback_data": f"cmd_mydata:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, play_text, play_kb)
        return

    elif text == "/boost":
        from app.game_engine import get_gharana_boost_status
        boost = get_gharana_boost_status()
        rem_m = boost["seconds_remaining"] // 60
        rem_s = boost["seconds_remaining"] % 60
        u_gid = user.get("gharana_id", 1)
        is_my_gharana = (u_gid == boost["active_gharana_id"])
        
        my_mult = "🔥 *2X MULTIPLIER ACTIVE!*" if is_my_gharana else "1x (Normal)"
        
        boost_msg = (
            f"⚡ *MAHA GHARANA 2X SURGE ARENA* ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 *Active Boost House*: {boost['active_gharana_emoji']} *{boost['active_gharana_name']}*\n"
            f"⏱️ *Surge Countdown*: `{rem_m:02d}:{rem_s:02d}` (10-minute equal window)\n"
            f"⏳ *Upcoming House*: {boost['next_gharana_emoji']} *{boost['next_gharana_name']}*\n\n"
            f"👤 *Your House*: *{settings.GHARANAS.get(u_gid, 'Surya Gharana')}*\n"
            f"🎯 *Your Status*: {my_mult}\n\n"
            f"📜 *Equal Opportunity Mechanics*:\n"
            f"• All 4 Gharanas rotate through a 10-minute 2x Surge 24/7.\n"
            f"• Cycle: ☀️ Surya → 🔥 Agni → 🌙 Chandra → 💨 Vayu.\n"
            f"• Every team receives exactly equal bonus opportunities!\n"
            f"• When your house is active, win **2x Hard Sparks** (2, 4, or 6 points) per game run!\n\n"
            f"👉 Ready to harvest double sparks? Choose an arena:"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "Enter Mini-App Arena", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "Play Chakri Whirl", "callback_data": f"play_chakri:{user_id}"},
                 {"text": "Play Rangoli", "callback_data": f"play_rangoli:{user_id}"}],
                [{"text": "Play Mithai Feast", "callback_data": f"play_mithai:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, boost_msg, kb)
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

    elif text in ("/captcha", "/testcaptcha", "/verifyhuman"):
        await send_captcha_prompt(chat_id, user_id, "Sacred Jyoti Verification Self-Test:")
        return

    elif text == "/status":
        conn = get_db_connection()
        with conn:
            update_user_stamina(conn, user_id)
            comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            u = conn.execute("SELECT points_total, tier_level, diya_wicks, referral_points_earned FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            comp_row = conn.execute(
                '''SELECT u.telegram_id, u.first_name, u.username, u.tier_level
                   FROM referrals r
                   JOIN users u ON u.telegram_id = (
                       CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END
                   )
                   WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1''',
                (user_id, user_id, user_id)
            ).fetchone()
        conn.close()
        
        sparks_total = comm["total_sparks"] if comm else 0
        stage_num, stage_name = get_stage_info(sparks_total)
        pts = u["points_total"] if u else 0
        t_lvl = u["tier_level"] if u else 0
        wicks = u["diya_wicks"] if u else 10
        ref_pts = u["referral_points_earned"] if u else 0
        tier_name = get_tier_name(t_lvl)
        if comp_row:
            comp_display = comp_row.get('first_name') or comp_row.get('username') or f"Player {comp_row.get('telegram_id', '')}"
            companion_text = f"*{escape_md(comp_display)}* ({get_tier_name(comp_row['tier_level'])})"
        else:
            companion_text = "_None yet (Invite 1 friend!)_"
        
        status_msg = (
            f"🪔 *Maha Deepotsav Status Report*\n\n"
            f"🔥 *Community Sparks*: `{sparks_total:,}` / `{settings.GLOBAL_MILESTONE_TARGET:,}`\n"
            f"🌟 *Current Stage*: {stage_name}\n\n"
            f"👤 *Your Profile*:\n"
            f"• Points: *{pts}*\n"
            f"• Tier: *{tier_name}* (Tier {t_lvl})\n"
            f"• Diya Wicks: *{wicks}/10*\n"
            f"• Diya Companion: {companion_text}\n"
            f"• Shagun Points: *{ref_pts}/{settings.MAX_REFERRAL_POINTS}*"
        )
        await send_telegram_message(chat_id, status_msg)
        return

    elif text.startswith("/shagun"):
        invite_link = f"https://t.me/{settings.BOT_USERNAME}?start=shagun_{user_id}"
        conn = get_db_connection()
        u = conn.execute("SELECT points_total, referral_points_earned FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        comp_row = conn.execute('''
            SELECT u.telegram_id, u.username, u.first_name, u.points_total
            FROM referrals r
            JOIN users u ON (u.telegram_id = CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END)
            WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1
        ''', (user_id, user_id, user_id)).fetchone()
        total_friends_count = conn.execute("SELECT COUNT(id) as c FROM referrals WHERE referrer_id = ?", (user_id,)).fetchone()["c"]
        conn.close()

        ref_points = u["referral_points_earned"] if u else 0
        if comp_row:
            c_name = f"@{comp_row['username']}" if comp_row['username'] else (comp_row['first_name'] or f"Player {comp_row['telegram_id']}")
            comp_status = f"🤝 *Diya Companion*: *{escape_md(c_name)}* (Bonded & Active)"
        else:
            comp_status = "🤝 *Diya Companion*: _None yet_ (Invite your 1st friend to bond!)"

        shagun_msg = (
            f"🎁 *Your Diwali Shagun Invite Link:*\n`{invite_link}`\n\n"
            f"{comp_status}\n"
            f"• *Invited Friends*: *{total_friends_count}* joined\n"
            f"• *Referral Points*: *{ref_points}/{settings.MAX_REFERRAL_POINTS} Pts* earned\n\n"
            f"Share your link with friends! Each friend awards you +1 point towards milestone tier coin rewards, and your 1st companion unlocks daily free wick exchanges!"
        )
        kb_buttons = []
        if comp_row:
            kb_buttons.append([{"text": "🎁 Send Free Wick to Companion", "callback_data": f"gift_companion_wick:{user_id}"}])
        kb_buttons.append([{"text": "📲 Share Invite on Telegram", "url": f"https://t.me/share/url?url={invite_link}&text=Join%20me%20in%20the%20Ordinal%20Legacy%20Diwali%20Maha%20Deepotsav!"}])
        await send_telegram_message(chat_id, shagun_msg, {"inline_keyboard": kb_buttons})
        return

    elif text == "/shubh":
        try:
            res = claim_shubh_refill(user_id)
            await send_telegram_message(chat_id, f"✨ *{res['message']}*")
        except Exception as e:
            await send_telegram_message(chat_id, f"⚠️ {getattr(e, 'detail', str(e))}")
        return

    elif text.startswith(("/gifts", "/gift")):
        # Must work in @Ordinal_Legacy group ONLY and nowhere else!
        if is_private or not is_ordinal_legacy_group(chat):
            await send_telegram_message(
                chat_id,
                "🎁 <b>Diwali Gift Exchange Exclusive Group</b>\n\n"
                "The <code>/gifts</code> command can only be used inside our official community group: "
                "<a href=\"https://t.me/Ordinal_Legacy\">@Ordinal_Legacy</a>.\n\n"
                "👉 Join the group to send and receive free Diya Wick gifts with your fellow players!"
            )
            return

        # Extract target from reply_to_message or command argument
        reply_msg = message.get("reply_to_message")
        reply_from = reply_msg.get("from", {}) if reply_msg else {}
        reply_to_id = reply_from.get("id") if reply_msg else None
        parts = text.split(maxsplit=1)
        target_arg = parts[1].strip() if len(parts) > 1 else ""

        if not target_arg and reply_from.get("is_bot"):
            await send_telegram_message(
                chat_id,
                "❌ <b>Invalid Recipient</b>: You cannot send Diya Wick gifts to bots! Reply to a fellow player's message in @Ordinal_Legacy."
            )
            return

        from app.game_engine import get_user_gift_status, execute_community_gift

        # If user did not specify any target and did not reply to any message, show their gift status
        if not target_arg and not reply_to_id:
            status = get_user_gift_status(user_id)
            cd_sec = status["cooldown_remaining_seconds"]
            if cd_sec > 0:
                h = cd_sec // 3600
                m = (cd_sec % 3600) // 60
                s = cd_sec % 60
                cd_text = f"⏳ Active ({h}h {m}m remaining)" if h > 0 else f"⏳ Active ({m}m {s}s remaining)"
            else:
                cd_text = "✅ Ready to gift!"

            guide_msg = (
                "🎁 <b>Festive Diya Gift Exchange in @Ordinal_Legacy</b>\n\n"
                f"• <b>Gifts Used Today</b>: <code>{status['gifts_used_today']}/{status['daily_limit']}</code> ({status['gifts_remaining_today']} left)\n"
                f"• <b>Cooldown Status</b>: {cd_text}\n"
                f"• <b>Gift Reward</b>: <b>+1 Diya Wick 🪔</b> for the recipient\n\n"
                "👉 <b>How to gift:</b>\n"
                "• <b>Reply</b> to any member's message in this group with <code>/gifts</code>\n"
                "• Or type <code>/gifts &lt;user_id&gt;</code> or <code>/gifts @username</code>\n\n"
                "<i>Rules: 5 gifts daily limit • 2h cooldown between gifts • 1 gift per recipient daily.</i>"
            )
            await send_telegram_message(chat_id, guide_msg)
            return

        # Execute the gift
        res = execute_community_gift(user_id, target_arg, reply_to_id)
        if not res["success"]:
            await send_telegram_message(chat_id, res["error"])
            return

        sender_fn = html.escape(first_name or f"Player {user_id}")
        receiver_fn = html.escape(res["receiver_name"])
        success_msg = (
            f"🎁 <b>Diwali Diya Gift Delivered!</b>\n\n"
            f"<b>{sender_fn}</b> gifted <b>1 Diya Wick 🪔</b> to <b>{receiver_fn}</b> (ID: <code>{res['receiver_id']}</code>)!\n\n"
            f"• <b>Recipient Stamina</b>: <code>{res['receiver_wicks']}/10 Wicks</code>\n"
            f"• <b>Your Allowance</b>: <code>{res['gifts_used_today']}/5 used</code> ({res['gifts_remaining_today']} left today)\n"
            f"• <b>Next Gift Cooldown</b>: 2 hours"
        )
        await send_telegram_message(chat_id, success_msg)
        await send_bot_log(f"🎁 Player <code>{user_id}</code> gifted 1 Diya Wick to <code>{res['receiver_id']}</code> in @Ordinal_Legacy. ({res['gifts_used_today']}/5 used today)")
        return

    elif text in ("/clash", "/gharanaclash"):
        from app.group_activities import get_gharana_clash_card
        clash_text = get_gharana_clash_card()
        await send_telegram_message(chat_id, clash_text)
        return

    elif text.startswith(("/dropdiya", "/flashdiya")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return

        from app.group_activities import create_flash_diya, record_event_message_id
        target_chat = chat_id
        if is_private:
            stored_group = get_system_setting("ordinal_legacy_group_chat_id", "")
            cfg_id = getattr(settings, "ORDINAL_LEGACY_CHAT_ID", "")
            if cfg_id and str(cfg_id).lstrip("-").isdigit():
                target_chat = int(cfg_id)
            elif stored_group and stored_group.lstrip("-").isdigit():
                target_chat = int(stored_group)
            else:
                await send_telegram_message(chat_id, "👉 Run `/dropdiya` directly inside the @Ordinal_Legacy group to release the flash flame!")
                return

        event_id, drop_text, kb = create_flash_diya(target_chat, max_claims=10)
        ok, msg_id = await send_telegram_message_with_id(target_chat, drop_text, kb)
        if ok and msg_id:
            record_event_message_id(event_id, msg_id)
            if is_private:
                await send_telegram_message(chat_id, f"✅ *Sacred Flash Diya Released* in group `{target_chat}`! (Event ID: `{event_id}`)")
            await send_bot_log(f"🪔 Admin `{user_id}` released a Sacred Flash Diya in `{target_chat}`.")
        else:
            await send_telegram_message(chat_id, "❌ Failed to dispatch Flash Diya to group.")
        return

    elif text.startswith(("/droptrivia", "/riddle")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return

        from app.group_activities import create_trivia_drop, record_event_message_id
        target_chat = chat_id
        if is_private:
            stored_group = get_system_setting("ordinal_legacy_group_chat_id", "")
            cfg_id = getattr(settings, "ORDINAL_LEGACY_CHAT_ID", "")
            if cfg_id and str(cfg_id).lstrip("-").isdigit():
                target_chat = int(cfg_id)
            elif stored_group and stored_group.lstrip("-").isdigit():
                target_chat = int(stored_group)
            else:
                await send_telegram_message(chat_id, "👉 Run `/droptrivia` directly inside the @Ordinal_Legacy group to release the trivia!")
                return

        event_id, drop_text, kb = create_trivia_drop(target_chat)
        ok, msg_id = await send_telegram_message_with_id(target_chat, drop_text, kb)
        if ok and msg_id:
            record_event_message_id(event_id, msg_id)
            if is_private:
                await send_telegram_message(chat_id, f"✅ *Sacred Festive Trivia Dispatched* to group `{target_chat}`! (Event ID: `{event_id}`)")
            await send_bot_log(f"🏮 Admin `{user_id}` dispatched Sacred Trivia to `{target_chat}`.")
        else:
            await send_telegram_message(chat_id, "❌ Failed to dispatch Trivia to group.")
        return

    elif text in ("/widget", "/akhand"):
        cached_w = get_cache("bot_cmd_widget")
        if cached_w:
            webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"
            await send_telegram_message(chat_id, cached_w, {"inline_keyboard": [[{"text": "🪔 Enter Festival Arena & Light the Flame", "web_app": {"url": webapp_url}}]]})
            return
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

        found_gids = {g["gharana_id"]: g for g in top_gharanas}
        complete_gharanas = []
        for gid, gname in settings.GHARANAS.items():
            if gid in found_gids:
                g = found_gids[gid]
                complete_gharanas.append({
                    "gharana_id": gid,
                    "members": g["members"],
                    "avg_pts": float(g["avg_pts"] or 0)
                })
            else:
                complete_gharanas.append({
                    "gharana_id": gid,
                    "members": 0,
                    "avg_pts": 0.0
                })
        sorted_gharanas = sorted(complete_gharanas, key=lambda g: g["avg_pts"], reverse=True)
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
        set_cache("bot_cmd_widget", widget_msg, ttl_seconds=10.0)
        webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"
        keyboard = {
            "inline_keyboard": [
                [{"text": "🪔 Enter Festival Arena & Light the Flame", "web_app": {"url": webapp_url}}]
            ]
        }
        await send_telegram_message(chat_id, widget_msg, keyboard)
        return

    elif text in ("/gharanas", "/leaderboard"):
        cached_g = get_cache("bot_cmd_gharanas")
        if cached_g:
            await send_telegram_message(chat_id, cached_g)
            return
        conn = get_db_connection()
        rows = conn.execute('''
            SELECT u.gharana_id, COUNT(u.id) as members, SUM(u.points_total) as pts, AVG(u.points_total) as avg_pts
            FROM users u GROUP BY u.gharana_id
        ''').fetchall()
        conn.close()

        found_gids = {r["gharana_id"]: r for r in rows}
        complete_rows = []
        for gid, gname in settings.GHARANAS.items():
            if gid in found_gids:
                r = found_gids[gid]
                complete_rows.append({
                    "gharana_id": gid,
                    "members": r["members"],
                    "pts": r["pts"] or 0,
                    "avg_pts": float(r["avg_pts"] or 0)
                })
            else:
                complete_rows.append({
                    "gharana_id": gid,
                    "members": 0,
                    "pts": 0,
                    "avg_pts": 0.0
                })
        sorted_rows = sorted(complete_rows, key=lambda r: (r["avg_pts"], r["pts"]), reverse=True)
        msg = "🏰 *Maha Deepotsav Gharana Standings:*\n\n"
        for idx, r in enumerate(sorted_rows, 1):
            g_name = settings.GHARANAS.get(r["gharana_id"], f"Gharana {r['gharana_id']}")
            avg_p = round(float(r["avg_pts"] or 0), 1)
            msg += f"*{idx}. {g_name}*\n   • Avg: *{avg_p} Pts* | Total: `{r['pts'] or 0:,} Sparks` | Members: {r['members']}\n\n"
        msg += "_All houses cooperate to ignite the 200,000 Akhand Diya while vying for house honor!_"
        set_cache("bot_cmd_gharanas", msg, ttl_seconds=10.0)
        await send_telegram_message(chat_id, msg)
        return

    elif text in ("/admins", "/findadmins"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: You do not have permission to view administrator records.")
            return
        admins = get_all_admin_ids()
        conn = get_db_connection()
        admin_lines = []
        for a_id in admins:
            u = conn.execute("SELECT username, first_name FROM users WHERE telegram_id = ?", (a_id,)).fetchone()
            name_str = f" (@{u['username']})" if u and u["username"] else (f" ({u['first_name']})" if u and u["first_name"] else "")
            super_tag = " 👑 [Sudo]" if a_id == 1257427765 else ""
            admin_lines.append(f"• ID: `{a_id}`{name_str}{super_tag}")
        conn.close()
        
        admin_msg = (
            f"👑 *Maha Deepotsav Event Administrators:*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(admin_lines) + "\n\n"
            f"🔒 _Notice: All game modification, SQL querying, and database commands are strictly locked to authorized administrators._"
        )
        if not is_private:
            delivered = await send_telegram_message(user_id, admin_msg)
            if delivered:
                await send_telegram_message(chat_id, "🔒 Administrator records sent privately to your DM, Sudo.")
            else:
                bot_user = settings.BOT_USERNAME or "OrdinalLegacyEventBot"
                await send_telegram_message(chat_id, f"🔒 Administrator records: Could not deliver to your private DM. Please open a chat with [@{bot_user}](https://t.me/{bot_user}) first.")
        else:
            await send_telegram_message(chat_id, admin_msg)
        return

    elif text in ("/admin", "/adminhelp"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: You do not have administrator privileges.")
            await send_bot_log(f"🚨 *Security Alert*: Unauthorized user `{user_id}` attempted to access `/adminhelp`.")
            return
        admin_help = (
            f"👑 *MAHA DEEPOTSAV: ADMIN COMMAND CENTER*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 *Player Management:*\n"
            f"• `/userinfo <id/@user>` — Deep dossier on player\n"
            f"• `/setpoints <id> <pts>` — Set exact hard sparks score\n"
            f"• `/addpoints <id> <pts>` — Add/deduct sparks (also `/add`)\n"
            f"• `/setwicks <id> <0-10>` — Set user's diya wicks\n"
            f"• `/resetwicks <id>` — Refill user to 10/10 wicks\n"
            f"• `/setgharana <id> <1-4>` — Transfer Gharana (1=Surya, 2=Agni, 3=Chandra, 4=Vayu)\n"
            f"• `/bypassverify <id>` — Manually grant group verification\n"
            f"• `/unverify <id>` — Reset verification status to unverified\n"
            f"• `/setcaptcha <id>` — Force human verification captcha on player\n"
            f"• `/unlockcaptcha <id>` — Instantly lift captcha lock for player\n"
            f"• `/unlockallcaptcha` — Lift captcha locks for all players\n"
            f"• `/deleteuser <id>` — Delete unwanted/test user record\n\n"
            f"📢 *Broadcast & Milestones:*\n"
            f"• `/broadcast <msg>` — Send announcement to all players\n"
            f"• `/setsparks <num>` — Set Akhand Jyoti community sparks\n"
            f"• `/settarget <num>` — Change community target goal (e.g. 50k, 100k)\n\n"
            f"🛡️ *Logs & Data Recovery Groups:*\n"
            f"• `/setlogschat <chat_id>` — Set Bot Logs Telegram Group\n"
            f"• `/setbackupchat <chat_id>` — Set Bot Recovery Telegram Group\n"
            f"• `/getchats` — View configured Logs & Recovery Groups\n"
            f"• `/testlog` — Send test ping to Logs & Recovery groups\n"
            f"• `/backup` — Trigger immediate backup snapshot\n"
            f"• `/restore` — Instructions to restore backup file\n\n"
            f"👑 *Admin Management:*\n"
            f"• `/addadmin <id>` — Add new administrator\n"
            f"• `/deladmin <id>` — Remove administrator\n"
            f"• `/admins` — View list of administrators\n\n"
            f"⏸️ <b>Event Controls & Score Auditing:</b>\n"
            f"• `/adminstats` — Deep audit of all players, active users & total contributions (also `/userstats`)\n"
            f"• `/stopevent` — Freeze game plays for final score audit\n"
            f"• `/resumeevent` — Unfreeze game plays and resume festival\n"
            f"• `/auditscores` — View complete final scores & tier breakdown\n"
            f"• `/tierusers <level>` — List all players in a tier (e.g. /tierusers 5)\n"
            f"• `/exportrewards` — Download complete CSV rewards spreadsheet\n"
            f"• `/eventstatus` — Check whether games are active or paused\n\n"
            f"⚙️ *Database & Multi-Level Resets:*\n"
            f"• `/resetscores CONFIRM` — Reset points/wicks (KEEPS all users & referrals!)\n"
            f"• `/refillallwicks` — Refill 10/10 wicks for all players instantly\n"
            f"• `/resetshubh` — Reset daily Shubh Muhurat refill for all\n"
            f"• `/resetevent CONFIRM` — Full event wipe (auto-backup first)\n"
            f"• `/cleandummy` — Purge mock/test accounts before launch\n"
            f"• `/syncreferrals` — Reconcile & sync ground-truth referral counts\n"
            f"• `/resetreferrals CONFIRM` — Clear all referral bonds & reset referral points\n"
            f"• `/query <SQL>` — Execute raw SQL query (Admin Only)\n"
            f"• `/syncbot` — Synchronize public commands in BotFather"
        )
        if not is_private:
            delivered = await send_telegram_message(user_id, admin_help)
            if delivered:
                await send_telegram_message(chat_id, "🔒 *Admin Command Center*: Dispatched privately to your DM, Sudo.")
            else:
                bot_user = settings.BOT_USERNAME or "OrdinalLegacyEventBot"
                await send_telegram_message(chat_id, f"🔒 *Admin Command Center*: Could not deliver to your private DM. Please open a chat with [@{bot_user}](https://t.me/{bot_user}) first, or run `/admin` in DM.")
        else:
            await send_telegram_message(chat_id, admin_help)
        return

    elif text.startswith("/addadmin"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            await send_bot_log(f"🚨 *Security Alert*: User `{user_id}` tried to use `/addadmin`.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: `/addadmin <telegram_id>`")
            return
        new_admin = int(parts[1])
        if add_admin_id(new_admin):
            await send_telegram_message(chat_id, f"✅ Administrator `{new_admin}` added successfully!")
            await send_bot_log(f"👑 Admin `{user_id}` added new admin `{new_admin}`.")
        else:
            await send_telegram_message(chat_id, f"ℹ️ `{new_admin}` is already an administrator.")
        return

    elif text.startswith("/deladmin"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            await send_bot_log(f"🚨 *Security Alert*: User `{user_id}` tried to use `/deladmin`.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: `/deladmin <telegram_id>`")
            return
        target_admin = int(parts[1])
        if target_admin == 1257427765:
            await send_telegram_message(chat_id, "⛔ Cannot remove primary Sudo administrator.")
            return
        if remove_admin_id(target_admin):
            await send_telegram_message(chat_id, f"✅ Administrator `{target_admin}` removed successfully.")
            await send_bot_log(f"👑 Admin `{user_id}` removed admin `{target_admin}`.")
        else:
            await send_telegram_message(chat_id, f"❌ Administrator `{target_admin}` not found or cannot be removed.")
        return

    elif text.startswith(("/setlogschat", "/setlogs", "/setlog")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2:
            await send_telegram_message(chat_id, "Usage: `/setlogs <chat_id>`\nExample: `/setlogs -1001234567890`")
            return
        new_cid = parts[1].strip()
        set_system_setting("logs_chat_id", new_cid)
        await send_telegram_message(chat_id, f"✅ Bot Logs Group ID set to `{new_cid}`.")
        await send_bot_log(f"🔔 *Bot Logs Group Connected!* Real-time operational logs will be streamed here.")
        return

    elif text.startswith(("/setbackupchat", "/setbackup")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2:
            await send_telegram_message(chat_id, "Usage: `/setbackup <chat_id>`\nExample: `/setbackup -1009876543210`")
            return
        new_cid = parts[1].strip()
        set_system_setting("backup_chat_id", new_cid)
        await send_telegram_message(chat_id, f"✅ Bot Recovery Data Group ID set to `{new_cid}`. Sending initial backup verification...")
        try:
            ok = await dispatch_backup_snapshot(reason="Initial Recovery Group Binding", target_chat_id=int(new_cid))
            if ok:
                await send_telegram_message(chat_id, f"🎉 Verification backup snapshot successfully delivered to `{new_cid}`!")
            else:
                await send_telegram_message(chat_id, f"⚠️ Configured, but failed to send initial file. Make sure bot is added as admin in `{new_cid}`.")
        except Exception as e:
            await send_telegram_message(chat_id, f"⚠️ Configured with warning: {e}")
        return

    elif text in ("/getchats", "/channels"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        logs_c = get_effective_logs_chat_id()
        backup_c = get_effective_backup_chat_id()
        last_b = get_system_setting("last_backup_time", "None")
        msg = (
            f"📡 *Configured Group Channels:*\n\n"
            f"• *Bot Logs Group*: `{logs_c or 'Not Configured'}`\n"
            f"• *Bot Recovery Data Group*: `{backup_c or 'Not Configured'}`\n"
            f"• *Last 6-Hr Auto-Backup*: `{last_b}`\n\n"
            f"_Use `/setlogs <id>` and `/setbackup <id>` to update._"
        )
        await send_telegram_message(chat_id, msg)
        return

    elif text in ("/testlog", "/testlogs"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        await send_bot_log(f"🧪 *Test Log Ping* triggered by admin `{user_id}`. Operational log system active.")
        await send_telegram_message(chat_id, "✅ Test log ping dispatched!")
        return

    elif text.startswith("/setpoints"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            await send_bot_log(f"🚨 *Security Alert*: User `{user_id}` tried to use `/setpoints`.")
            return
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            await send_telegram_message(chat_id, "Usage: `/setpoints <telegram_id> <points>`")
            return
        target_id = int(parts[1])
        new_pts = int(parts[2])
        new_tier = calculate_tier(new_pts)
        conn = get_db_connection()
        with conn:
            target = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not target:
                conn.close()
                await send_telegram_message(chat_id, f"❌ Player `{target_id}` not found.")
                return
            diff = new_pts - target["points_total"]
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, target_id))
            if diff != 0:
                comm_row = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
                cur_comm = comm_row["total_sparks"] if comm_row else 0
                new_comm = max(0, cur_comm + diff)
                new_stage, _ = get_stage_info(new_comm)
                conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (new_comm, new_stage))
            comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            comm_total = comm["total_sparks"] if comm else 0
        conn.close()
        from app.cache import invalidate_event_cache
        invalidate_event_cache(target_id)
        await send_telegram_message(
            chat_id,
            f"✅ *Score Updated*: User `{target_id}` points set to *{new_pts}* ({get_tier_name(new_tier)}).\n"
            f"• Community Total: *{comm_total:,} Sparks*"
        )
        await send_bot_log(f"✏️ Admin `{user_id}` set points for `{target_id}` to `{new_pts}`.")
        return

    elif text.startswith(("/add", "/addpoints")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            await send_bot_log(f"🚨 *Security Alert*: User `{user_id}` tried to use `/addpoints`.")
            return
            
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
            await send_telegram_message(chat_id, "Usage: `/addpoints <telegram_id> <points>`")
            return
            
        target_id = int(parts[1])
        pts = int(parts[2])
        
        conn = get_db_connection()
        with conn:
            target = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not target:
                conn.close()
                await send_telegram_message(chat_id, f"❌ Player `{target_id}` not found.")
                return
                
            new_pts = max(0, target["points_total"] + pts)
            new_tier = calculate_tier(new_pts)
            
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, target_id))
            comm_row = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            cur_comm = comm_row["total_sparks"] if comm_row else 0
            new_comm = max(0, cur_comm + pts)
            new_stage, _ = get_stage_info(new_comm)
            conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (new_comm, new_stage))
            comm_total = new_comm
        conn.close()
        from app.cache import invalidate_event_cache
        invalidate_event_cache(target_id)
        
        await send_telegram_message(
            chat_id,
            f"✅ *Admin Update*: Added {pts} points to `{target_id}`.\n"
            f"• New User Score: *{new_pts}* ({get_tier_name(new_tier)})\n"
            f"• Community Total: *{comm_total:,} Sparks*"
        )
        await send_bot_log(f"✨ Admin `{user_id}` adjusted points for `{target_id}` by `{pts}`.")
        return

    elif text.startswith("/setwicks"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            await send_telegram_message(chat_id, "Usage: `/setwicks <telegram_id> <0-10>`")
            return
        target_id = int(parts[1])
        wicks_val = min(10, max(0, int(parts[2])))
        conn = get_db_connection()
        with conn:
            u = conn.execute("SELECT first_name FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not u:
                conn.close()
                await send_telegram_message(chat_id, f"❌ Player `{target_id}` not found.")
                return
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            from app.game_engine import get_random_wick_cooldown
            next_cd = get_random_wick_cooldown()
            try:
                conn.execute("UPDATE users SET diya_wicks = ?, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?", (wicks_val, now_iso, next_cd, target_id))
            except Exception:
                conn.execute("UPDATE users SET diya_wicks = ?, last_wick_regen = ? WHERE telegram_id = ?", (wicks_val, now_iso, target_id))
        conn.close()
        await send_telegram_message(chat_id, f"✅ Diya Wicks set to *{wicks_val}/10* for `{target_id}` ({u['first_name']}).")
        await send_bot_log(f"🪔 Admin `{user_id}` updated wicks for `{target_id}` to `{wicks_val}`.")
        return

    elif text.startswith("/setgharana"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in ("1", "2", "3", "4"):
            await send_telegram_message(chat_id, "Usage: `/setgharana <telegram_id> <1-4>`\n1=Surya, 2=Agni, 3=Chandra, 4=Vayu")
            return
        target_id = int(parts[1])
        new_gid = int(parts[2])
        g_name = settings.GHARANAS.get(new_gid)
        conn = get_db_connection()
        with conn:
            u = conn.execute("SELECT first_name FROM users WHERE telegram_id = ?", (target_id,)).fetchone()
            if not u:
                conn.close()
                await send_telegram_message(chat_id, f"❌ Player `{target_id}` not found.")
                return
            conn.execute("UPDATE users SET gharana_id = ? WHERE telegram_id = ?", (new_gid, target_id))
        conn.close()
        await send_telegram_message(chat_id, f"✅ User `{target_id}` ({u['first_name']}) transferred to *{g_name}*!")
        await send_bot_log(f"🏰 Admin `{user_id}` moved `{target_id}` to `{g_name}`.")
        return

    elif text.startswith("/setsparks"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: `/setsparks <sparks>`\nExample: `/setsparks 50000`")
            return
        new_sparks = int(parts[1])
        new_stage, stage_name = get_stage_info(new_sparks)
        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (new_sparks, new_stage))
        conn.close()
        await send_telegram_message(chat_id, f"🔥 *Akhand Diya Sparks Updated*: `{new_sparks:,}` Sparks ({stage_name}).")
        await send_bot_log(f"🔥 Admin `{user_id}` set community sparks to `{new_sparks:,}`.")
        return

    elif text.startswith("/settarget"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
            await send_telegram_message(chat_id, "Usage: `/settarget <target_sparks>`\nExample: `/settarget 100000` or `/settarget 50000`")
            return
        new_target = int(parts[1])
        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE community_state SET target_sparks = ? WHERE id = 1", (new_target,))
            row = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
            cur_sparks = row["total_sparks"] if row else 0
        conn.close()
        pct = min(100.0, (cur_sparks / new_target) * 100)
        await send_telegram_message(
            chat_id,
            f"🎯 *Community Akhand Jyoti Target Updated!*\n\n"
            f"• New Target: *{new_target:,} Sparks*\n"
            f"• Current Progress: *{cur_sparks:,} / {new_target:,} Sparks* ({pct:.1f}%)\n\n"
            f"✨ All mini-app progress tracks and status commands are now synced to this target!"
        )
        await send_bot_log(f"🎯 Sudo `{user_id}` updated community target to `{new_target:,}` Sparks.")
        return

    elif text.startswith("/unverify"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        target_uid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else user_id
        conn = get_db_connection()
        conn.execute("UPDATE users SET joined_groups = 0 WHERE telegram_id = ?", (target_uid,))
        conn.close()
        await send_telegram_message(chat_id, f"🔒 User `{target_uid}` status set to *Unverified*.")
        await send_bot_log(f"🛡️ Admin `{user_id}` unverified user `{target_uid}`.")
        return

    elif text.startswith("/setcaptcha"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        target_uid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else user_id
        from app.captcha_engine import lock_user_captcha
        lock_user_captcha(target_uid)
        await send_telegram_message(chat_id, f"🔒 Captcha lock activated on player `{target_uid}`.")
        await send_captcha_prompt(target_uid, target_uid, "Security Verification Triggered by Admin:")
        return

    elif text.startswith(("/unlockcaptcha", "/clearcaptcha")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        target_uid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else user_id
        from app.captcha_engine import unlock_user_captcha
        unlock_user_captcha(target_uid)
        await send_telegram_message(chat_id, f"🔓 Captcha lock lifted for player `{target_uid}`. They can now play freely.")
        await send_bot_log(f"🔓 Admin `{user_id}` unlocked captcha for `{target_uid}`.")
        return

    elif text in ("/unlockallcaptcha", "/clearcaptchas", "/resetcaptcha"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        from app.captcha_engine import unlock_all_users_captcha
        cleared = unlock_all_users_captcha()
        await send_telegram_message(chat_id, f"🔓 Lifted all active captcha locks ({cleared} players unlocked).")
        await send_bot_log(f"🔓 Admin `{user_id}` cleared all captcha locks ({cleared} players).")
        return

    elif text.startswith("/deleteuser"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: `/deleteuser <telegram_id>`")
            return
        target_uid = int(parts[1])
        if target_uid == 1257427765:
            await send_telegram_message(chat_id, "❌ Cannot delete Sudo administrator.")
            return
        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (target_uid,))
            conn.execute("DELETE FROM game_sessions WHERE telegram_id = ?", (target_uid,))
            conn.execute("DELETE FROM referrals WHERE referrer_id = ? OR referred_id = ?", (target_uid, target_uid))
            row = conn.execute("SELECT COALESCE(SUM(points_total), 0) as s FROM users").fetchone()
            valid_sparks = row["s"] if row else 0
            stage, _ = get_stage_info(valid_sparks)
            conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (valid_sparks, stage))
        conn.close()
        await send_telegram_message(chat_id, f"🗑️ User `{target_uid}` deleted from database. Akhand sparks updated to {valid_sparks:,}.")
        await send_bot_log(f"🗑️ Sudo `{user_id}` deleted user `{target_uid}`.")
        return

    elif text.startswith("/broadcast"):
        global _IS_BROADCASTING
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        bc_msg = text[len("/broadcast"):].strip()
        if not bc_msg:
            await send_telegram_message(chat_id, "Usage: `/broadcast <message>`")
            return

        if _IS_BROADCASTING:
            await send_telegram_message(chat_id, "⚠️ A broadcast is already running. Please wait for it to finish.")
            return

        await send_telegram_message(chat_id, "⏳ *Broadcast initiated in the background...*")

        async def _run_broadcast(admin_id: int, message: str):
            global _IS_BROADCASTING
            _IS_BROADCASTING = True
            try:
                conn = get_db_connection()
                user_rows = conn.execute("SELECT DISTINCT telegram_id FROM users WHERE telegram_id IS NOT NULL").fetchall()
                conn.close()

                target_ids = list({row["telegram_id"] for row in user_rows})
                sent_count = 0
                formatted = f"📢 *FESTIVAL BROADCAST*\n-------------------------------\n{message}"

                for target_uid in target_ids:
                    try:
                        ok = await send_telegram_message(target_uid, formatted)
                        if ok:
                            sent_count += 1
                    except Exception as e:
                        print(f"Broadcast delivery error for {target_uid}: {e}")
                    await asyncio.sleep(0.04)

                await send_telegram_message(admin_id, f"✅ Broadcast delivered to *{sent_count}/{len(target_ids)}* registered users.")
                try:
                    await send_bot_log(f"📢 Admin `{admin_id}` broadcasted to `{sent_count}` users.")
                except Exception:
                    pass
            finally:
                _IS_BROADCASTING = False

        asyncio.create_task(_run_broadcast(user_id, bc_msg))
        return


    elif text.startswith("/query"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: You do not have permission to execute SQL queries.")
            await send_bot_log(f"🚨 *CRITICAL SECURITY ALERT*: Unauthorized user `{user_id}` attempted to execute SQL query: `{text}`")
            return
        
        query_str = text[len("/query"):].strip()
        if not query_str:
            await send_telegram_message(chat_id, "Usage:\n`/query SELECT telegram_id, points_total FROM users LIMIT 5;`\n`/query UPDATE users SET diya_wicks = 10 WHERE telegram_id = 123456;`")
            return
        
        upper_q = query_str.upper()
        if not (upper_q.startswith("SELECT") or upper_q.startswith("UPDATE") or upper_q.startswith("INSERT") or upper_q.startswith("DELETE")):
            await send_telegram_message(chat_id, "⚠️ Only `SELECT`, `UPDATE`, `INSERT`, and `DELETE` queries are permitted.")
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
                await send_telegram_message(chat_id, f"✅ *Statement Executed*: `{affected}` rows affected.")
                await send_bot_log(f"💾 Admin `{user_id}` executed query: `{query_str[:80]}` ({affected} rows affected).")
        except Exception as e:
            await send_telegram_message(chat_id, f"❌ *Query Error*: `{str(e)}`")
        finally:
            conn.close()
        return

    elif text.startswith(("/findtier", "/tierusers")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
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

    elif text.startswith("/userinfo") or text == "/user" or text.startswith("/user "):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
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
        
        if comp_row:
            c_tag = f"@{comp_row['username']}" if comp_row['username'] else (comp_row['first_name'] or f"ID {comp_row['telegram_id']}")
            comp_str = f"{c_tag} (`{comp_row['telegram_id']}`)"
        else:
            comp_str = "None"
            
        g_name = settings.GHARANAS.get(u["gharana_id"], "Unknown")
        display_name = f"@{u['username']}" if u['username'] else (u['first_name'] or f"Player {u['telegram_id']}")
        u_handle = f"@{u['username']}" if u['username'] else "None"
        
        profile_msg = (
            f"👤 <b>Player Profile: {html.escape(display_name)}</b>\n\n"
            f"• Telegram ID: <code>{u['telegram_id']}</code>\n"
            f"• Username: <b>{html.escape(u_handle)}</b>\n"
            f"• Gharana: <b>{g_name}</b>\n"
            f"• Hard Points: <b>{u['points_total']} Pts</b>\n"
            f"• Tier: <b>{get_tier_name(u['tier_level'])}</b> (Tier {u['tier_level']})\n"
            f"• Diya Wicks: <b>{u['diya_wicks']}/10</b>\n"
            f"• Diya Companion: <b>{html.escape(comp_str)}</b>\n"
            f"• Friends Invited: <b>{total_refs}</b> (Points earned: {u['referral_points_earned']}/{settings.MAX_REFERRAL_POINTS})\n"
            f"• Completed Runs: <b>{games_count}</b> (Flawless 3-pt runs: {three_pts})\n"
            f"• Joined: <code>{u['created_at']}</code>"
        )
        await send_telegram_message(chat_id, profile_msg)
        return

    elif text in ("/top", "/tops", "/topusers", "/leaderboard"):
        cached_t = get_cache("bot_cmd_top")
        if cached_t:
            await send_telegram_message(chat_id, cached_t)
            return
        conn = get_db_connection()
        rows = conn.execute('''
            SELECT telegram_id, username, first_name, gharana_id, points_total, tier_level
            FROM users
            ORDER BY points_total DESC, id ASC
            LIMIT 10
        ''').fetchall()
        conn.close()
        
        msg = "🌟 <b>Maha Deepotsav Top 10 Lampbearers:</b>\n\n"
        medals = ["🥇", "🥈", "🥉"] + ["✨"] * 7
        for idx, r in enumerate(rows):
            clean_fn = re.sub(r'[\r\n\t]+', ' ', r['first_name']).strip() if r['first_name'] else "Lampbearer"
            safe_name = html.escape(clean_fn)
            u_tag = f"{safe_name} (ID: <code>{r['telegram_id']}</code>)"
            g_name = settings.GHARANAS.get(r['gharana_id'], "")
            msg += f"{medals[idx]} <b>#{idx+1}. {u_tag}</b> — <b>{r['points_total']} Pts</b>\n   <i>{get_tier_name(r['tier_level'])} • {g_name}</i>\n\n"
        delete_cache("bot_cmd_top")
        set_cache("bot_cmd_top", msg, ttl_seconds=10.0)
        await send_telegram_message(chat_id, msg)
        return

    elif text.startswith("/resetwicks"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
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
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            from app.game_engine import get_random_wick_cooldown
            next_cd = get_random_wick_cooldown()
            try:
                conn.execute("UPDATE users SET diya_wicks = ?, last_wick_regen = ?, wick_cooldown_seconds = ? WHERE telegram_id = ?", (settings.STAMINA_BANK_CAP, now_iso, next_cd, target_id))
            except Exception:
                conn.execute("UPDATE users SET diya_wicks = ?, last_wick_regen = ? WHERE telegram_id = ?", (settings.STAMINA_BANK_CAP, now_iso, target_id))
        conn.close()
        await send_telegram_message(chat_id, f"✅ Restored full Diya Wicks (10/10) for `{target_id}` ({u['first_name']}).")
        await send_bot_log(f"🪔 Admin `{user_id}` restored full wicks (10/10) for `{target_id}`.")
        return

    elif text in ("/backup", "/snapshot"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        await send_telegram_message(chat_id, "⏳ Generating complete database snapshot and dispatching to Recovery Group...")
        ok = await dispatch_backup_snapshot(reason=f"Manual Admin Request by {user_id}", target_chat_id=chat_id)
        if ok:
            await send_telegram_message(chat_id, "✅ Database backup snapshot dispatched successfully!")
        else:
            await send_telegram_message(chat_id, "⚠️ Backup generation encountered an issue. Check server logs.")
        return

    elif text.startswith("/restore"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        msg = (
            "📥 *Database Recovery / Restore Procedure*\n\n"
            "To restore the database from a backup JSON snapshot:\n"
            "1. Locate any `.json` backup file generated by `/backup` or automatic 6-hour backup.\n"
            "2. Send/upload that file directly to this bot chat.\n"
            "3. Set the file caption to `/restore`.\n\n"
            "⚠️ *Note*: Restoring will import all users, referrals, and community sparks from the snapshot."
        )
        await send_telegram_message(chat_id, msg)
        return

    elif text.startswith("/resetevent"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
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

        # Automatic safety backup first dispatched to recovery group & admin chat
        await dispatch_backup_snapshot(reason=f"Pre-Reset Safety Snapshot by Admin {user_id}", target_chat_id=chat_id)

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
        await send_bot_log(f"🔄 *Event Reset Executed* by Admin `{user_id}`. Safety backup snapshot was dispatched.")
        return

    elif text.startswith(("/resetscores", "/resetpoints")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) < 2 or parts[1].upper() != "CONFIRM":
            warn_msg = (
                f"⚠️ *RESET SCORES REQUESTED (Keeps All Users & Referrals)*\n\n"
                f"This will:\n"
                f"• Reset all player scores to *0 Pts* (Tier 0: Diya Spark)\n"
                f"• Refill all players' Diya Wicks to *10/10*\n"
                f"• Reset community Akhand Jyoti to *0 Sparks (Stage 0)*\n"
                f"• Reset daily Shubh Muhurat refills\n"
                f"• Clear gameplay session history\n\n"
                f"🔒 *100% PRESERVED*:\n"
                f"• All registered users & Telegram usernames\n"
                f"• Gharana house assignments\n"
                f"• Group gate verification statuses\n"
                f"• All Diya Companion & referral bonds\n\n"
                f"👉 To execute for tomorrow's launch, type:\n`/resetscores CONFIRM`"
            )
            await send_telegram_message(chat_id, warn_msg)
            return

        # Automatic safety backup first
        await dispatch_backup_snapshot(reason=f"Pre-Score-Reset Safety Snapshot by Sudo {user_id}", target_chat_id=chat_id)

        res = reset_scores_keep_users()
        await send_telegram_message(
            chat_id,
            f"🔄 *Festival Scores Reset Complete!*\n\n"
            f"• All player scores reset to *0 Pts* for official launch!\n"
            f"• All Diya Wicks refilled to *10/10*\n"
            f"• Community Akhand Diya reset to *0 Sparks*\n"
            f"• Preserved Lampbearers: *{res['users_preserved']}*\n"
            f"• Preserved Referral Bonds: *{res['referrals_preserved']}*\n\n"
            f"✨ The competition arena is fresh and ready!"
        )
        await send_bot_log(f"🔄 Sudo `{user_id}` executed `/resetscores`. Scores reset; {res['users_preserved']} users and {res['referrals_preserved']} referrals preserved.")
        return

    elif text.startswith("/resetreferrals"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) < 2 or parts[1].upper() != "CONFIRM":
            await send_telegram_message(
                chat_id,
                "⚠️ *RESET ALL REFERRALS*\n\nThis will clear all referral bonds, companion links, and reset all players' `referral_points_earned` to 0 so you can test freshly.\n\nType `/resetreferrals CONFIRM` to execute."
            )
            return
        from app.referral_engine import reset_all_referrals
        res = reset_all_referrals()
        await send_telegram_message(chat_id, f"✅ *Referrals Reset*: {res['message']}")
        await send_bot_log(f"🔄 Sudo `{user_id}` executed `/resetreferrals`. All referral records cleared.")
        return

    elif text in ("/refillallwicks", "/resetallwicks"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        res = refill_all_users_wicks()
        await send_telegram_message(chat_id, f"🪔 *All Wicks Refilled!* Restored full Diya Wicks (10/10) for all *{res['users_refilled']}* registered players.")
        await send_bot_log(f"🪔 Sudo `{user_id}` refilled wicks for all {res['users_refilled']} players.")
        return

    elif text in ("/resetshubh", "/resetallshubh"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        res = reset_all_shubh_refills()
        await send_telegram_message(chat_id, f"✨ *Shubh Muhurat Reset!* All *{res['users_reset']}* players can now claim their +5 wicks & points blessing again.")
        await send_bot_log(f"✨ Sudo `{user_id}` reset Shubh Muhurat refills for all {res['users_reset']} players.")
        return

    elif text in ("/cleandummy", "/purgedummy"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        await send_telegram_message(chat_id, "⏳ Purging all mock/test accounts and dummy sessions from database...")
        res = purge_dummy_data()
        await send_telegram_message(
            chat_id,
            f"🧹 *Dummy Accounts Purged Successfully!*\n\n"
            f"• Real Lampbearers Preserved: *{res['remaining_users']}*\n"
            f"• Valid Akhand Jyoti Sparks: *{res['sparks']:,} Sparks*\n"
            f"• All test and mock user records removed for official launch."
        )
        await send_bot_log(f"🧹 Admin `{user_id}` executed `/cleandummy`. Remaining players: {res['remaining_users']}.")
        return

    elif text == "/stats":
        cached_s = get_cache("bot_cmd_stats")
        if cached_s:
            await send_telegram_message(chat_id, cached_s)
            return
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
        set_cache("bot_cmd_stats", stats_msg, ttl_seconds=10.0)
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
            f"🏆 *Maha Deepotsav Milestone Rewards Ladder*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 *Tier 0: Diya Spark (0–499 Pts)* — Welcome Badge\n"
            f"🪙 *Tier 1: Diya Sevak (500 Pts)* — 🪙 Coins\n"
            f"🔮 *Tier 2: Rangoli Artisan (1,500 Pts)* — 🔮 Pearl\n"
            f"🎟 *Tier 3: Spark Master (2,750 Pts)* — 🎟 Ticket\n"
            f"🐾 *Tier 4: Deep Mahant (4,000 Pts)* — 🐾 Pet\n"
            f"👑 *Tier 5: Akhand Sovereign (5,000+ Pts)* — 🏆 ALL REWARDS: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet!\n\n"
            f"🔥 *Community 200,000 Sparks (5 Segments):*\n"
            f"• 40,000 Sparks — Segment 1 Clears 🪙 Coins\n"
            f"• 80,000 Sparks — Segment 2 Clears 🔮 Pearls\n"
            f"• 120,000 Sparks — Segment 3 Clears 🎟 Tickets\n"
            f"• 160,000 Sparks — Segment 4 Clears 🐾 Pets\n"
            f"• 200,000 Sparks — Segment 5 Clears All Combined Rewards!\n\n"
            f"_Earn 1 to 3 hard sparks per mini-game run to ascend the ladder!_"
        )
        await send_telegram_message(chat_id, ladder_text)
        return

    elif text in ("/mydata", "/profile", "/data"):
        conn = get_db_connection()
        with conn:
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
        
        if comp_row:
            comp_display = comp_row['first_name'] or comp_row['username'] or f"Player {comp_row['telegram_id']}"
            comp_str = f"*{escape_md(comp_display)}*"
        else:
            comp_str = "_None yet (Use /shagun)_"
        today_str = datetime.date.today().isoformat()
        shubh_status = "✅ Claimed today" if u["shubh_refill_date"] == today_str else "✨ Available now (/shubh)"
        
        safe_fname = escape_md(first_name)
        u_handle = f"@{username}" if username else "None"
        mydata_msg = (
            f"👤 *PLAYER EVENT DOSSIER: {safe_fname}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 *Telegram ID*: `{user_id}`\n"
            f"🏷 *Username*: {u_handle}\n"
            f"🏰 *Initiated House*: *{g_name}*\n"
            f"🛡 *Official Gate*: {'✅ Verified Member' if u['joined_groups'] else '⚠️ Unverified'}\n\n"
            f"🔥 *Sparks Contributed*: *{pts:,} Sparks*\n"
            f"🏆 *Current Rank Tier*: *{tier_name} (Tier {tier})*\n\n"
            f"🎁 *Reward Milestones:*\n"
            f"{rew_text}\n\n"
            f"🪔 *Diya Wicks*: *{u['diya_wicks']}/10*\n"
            f"⚡ *Stamina Speed*: 1 wick every 1–3 mins randomly\n"
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
                [{"text": "Play Mini-Games", "callback_data": f"menu_play:{user_id}"},
                 {"text": "Launch Mini-App", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                [{"text": "Invite Friends", "callback_data": f"cmd_shagun:{user_id}"},
                 {"text": "Daily Refill", "callback_data": f"cmd_shubh:{user_id}"}]
            ]
        }
        await send_telegram_message(chat_id, mydata_msg, kb)
        return

    elif text == "/syncbot":
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        ok = await sync_telegram_bot_commands()
        if ok:
            await send_telegram_message(chat_id, "✅ *Telegram Bot Commands Synchronized!* All player commands are now visible in the Telegram menu button.")
        else:
            await send_telegram_message(chat_id, "⚠️ Failed to sync commands. Check bot token or server logs.")
        return

    elif text == "/syncreferrals":
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ *Access Denied*: Admin privileges required.")
            return
        from app.referral_engine import reconcile_all_referrals
        res = reconcile_all_referrals()
        await send_telegram_message(chat_id, f"✅ *Referral Reconciliation Complete*: Synced {res['synced_users']} user accounts with exact referral table records.")
        return

    elif text in ("/stopevent", "/pauseevent"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return
        from app.database import set_event_paused
        set_event_paused(True)
        delete_cache("api_community_state")
        msg = (
            "⏸️ <b>Maha Deepotsav Games Frozen</b>\n\n"
            "All game plays across Telegram Chat and the Web Mini-App have been paused for score auditing.\n\n"
            "• Players can still view their final stats via /mydata and /top, but cannot start new game runs.\n"
            "• Use /auditscores to inspect the final score audit.\n"
            "• Use /tierusers &lt;level&gt; to list winners by tier.\n"
            "• Use /exportrewards to download the complete CSV winners list.\n"
            "• Use /resumeevent to unfreeze when ready."
        )
        await send_telegram_message(chat_id, msg)
        await send_bot_log(f"⏸️ <b>Event Frozen</b>: Admin `{user_id}` paused game plays for final score audit.")
        return

    elif text in ("/resumeevent", "/startevent", "/unpauseevent"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return
        from app.database import set_event_paused
        set_event_paused(False)
        delete_cache("api_community_state")
        msg = (
            "▶️ <b>Maha Deepotsav Games Resumed</b>\n\n"
            "Game plays in Chat and Mini-App are now active again!"
        )
        await send_telegram_message(chat_id, msg)
        await send_bot_log(f"▶️ <b>Event Resumed</b>: Admin `{user_id}` unpaused game plays.")
        return

    elif text in ("/adminstats", "/userstats", "/playerstats", "/eventstats") or text.startswith(("/adminstats ", "/userstats ", "/playerstats ", "/eventstats ")):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return

        conn = get_db_connection()
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        active_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE points_total > 0").fetchone()["c"]
        verified_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE joined_groups = 1").fetchone()["c"]
        
        unique_gamers = conn.execute("SELECT COUNT(DISTINCT telegram_id) as c FROM game_sessions WHERE is_valid = 1").fetchone()["c"]
        total_sessions = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE is_valid = 1").fetchone()["c"]
        three_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 3 AND is_valid = 1").fetchone()["c"]
        two_pts = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 2 AND is_valid = 1").fetchone()["c"]
        one_pt = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE score_awarded = 1 AND is_valid = 1").fetchone()["c"]
        game_points = conn.execute("SELECT COALESCE(SUM(score_awarded), 0) as s FROM game_sessions WHERE is_valid = 1").fetchone()["s"]

        comm = conn.execute("SELECT total_sparks, target_sparks FROM community_state WHERE id = 1").fetchone()
        total_sparks = comm["total_sparks"] if comm else 0
        target_sparks = comm["target_sparks"] if comm else settings.GLOBAL_MILESTONE_TARGET
        comm_pct = min(100.0, (total_sparks / max(1, target_sparks)) * 100)
        stage_num, stage_name = get_stage_info(total_sparks)

        total_bank_points = conn.execute("SELECT COALESCE(SUM(points_total), 0) as s FROM users").fetchone()["s"]
        total_ref_points = conn.execute("SELECT COALESCE(SUM(referral_points_earned), 0) as s FROM users").fetchone()["s"]
        companions = conn.execute("SELECT COUNT(*) as c FROM referrals WHERE is_companion = 1").fetchone()["c"]

        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        today_shubh = conn.execute("SELECT COUNT(*) as c FROM users WHERE shubh_refill_date = ?", (today_str,)).fetchone()["c"]

        tier_counts = conn.execute("SELECT tier_level, COUNT(*) as c FROM users GROUP BY tier_level").fetchall()
        tc_dict = {row["tier_level"]: row["c"] for row in tier_counts}

        gharana_stats = conn.execute(
            "SELECT gharana_id, COUNT(*) as members, COALESCE(SUM(points_total), 0) as total_pts FROM users GROUP BY gharana_id ORDER BY total_pts DESC"
        ).fetchall()

        top_mvps = conn.execute(
            "SELECT telegram_id, username, first_name, points_total, tier_level FROM users ORDER BY points_total DESC LIMIT 5"
        ).fetchall()
        
        from app.database import is_event_paused
        paused = is_event_paused()
        conn.close()

        status_str = "⏸️ <b>PAUSED FOR AUDIT</b>" if paused else "🟢 <b>ACTIVE & RUNNING</b>"
        active_pct = (active_users / total_users * 100) if total_users > 0 else 0.0

        lines = [
            "📊 <b>MAHA DEEPOTSAV — COMPREHENSIVE EVENT & USER AUDIT</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚡ <b>Event State</b>: {status_str}",
            f"🔥 <b>Community Akhand Diya</b>: <code>{total_sparks:,} / {target_sparks:,} Sparks</code> (<b>{comm_pct:.1f}%</b>)",
            f"📍 <b>Milestone Stage</b>: <code>{stage_name}</code> (Stage {stage_num})\n",
            
            "👥 <b>USER PARTICIPATION STATS:</b>",
            f"• Total Registered: <b>{total_users:,} players</b>",
            f"• Active Scoring Users: <b>{active_users:,} players</b> (<b>{active_pct:.1f}%</b>)",
            f"• Zero-Score Inactive: <b>{(total_users - active_users):,} players</b>",
            f"• Group-Verified Members: <b>{verified_users:,} players</b>",
            f"• Unique Game Players: <b>{unique_gamers:,} players</b>\n",

            "🎯 <b>TOTAL CONTRIBUTIONS DONE:</b>",
            f"• Total Sparks Generated: <b>{total_sparks:,} Sparks</b>",
            f"• Total Points in Player Banks: <b>{total_bank_points:,} Pts</b>",
            f"• Game Runs Completed: <b>{total_sessions:,} runs</b> (<b>{game_points:,} Pts</b>)",
            f"   - 🌟 Flawless (3 Pts): <code>{three_pts:,}</code>",
            f"   - ✨ Skilled (2 Pts): <code>{two_pts:,}</code>",
            f"   - 🪔 Base (1 Pt): <code>{one_pt:,}</code>",
            f"• Referral Points Earned: <b>{total_ref_points:,} Pts</b> (<b>{companions:,}</b> bonded pairs)",
            f"• Today's Shubh Muhurat Claims: <b>{today_shubh:,} players</b>\n",

            "🏛️ <b>GHARANA CONTRIBUTIONS:</b>"
        ]

        gharana_names = {1: "☀️ Surya Gharana", 2: "🔥 Agni Gharana", 3: "🌙 Chandra Gharana", 4: "💨 Vayu Gharana"}
        for g in gharana_stats:
            g_name = gharana_names.get(g["gharana_id"], f"Gharana {g['gharana_id']}")
            lines.append(f"• {g_name}: <b>{g['total_pts']:,} Pts</b> ({g['members']:,} members)")

        lines.append("\n🎖️ <b>TIER LADDER DISTRIBUTION:</b>")
        lines.append(f"• Tier 5 (5,000+ Pts): <b>{tc_dict.get(5, 0):,}</b>")
        lines.append(f"• Tier 4 (4,000–4,999): <b>{tc_dict.get(4, 0):,}</b>")
        lines.append(f"• Tier 3 (2,750–3,999): <b>{tc_dict.get(3, 0):,}</b>")
        lines.append(f"• Tier 2 (1,500–2,749): <b>{tc_dict.get(2, 0):,}</b>")
        lines.append(f"• Tier 1 (500–1,499): <b>{tc_dict.get(1, 0):,}</b>")
        lines.append(f"• Tier 0 (0–499): <b>{tc_dict.get(0, 0):,}</b>\n")

        lines.append("🌟 <b>TOP 5 CONTRIBUTORS:</b>")
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        if not top_mvps:
            lines.append("<i>No scores recorded yet.</i>")
        else:
            for idx, mvp in enumerate(top_mvps):
                m = medals[idx] if idx < len(medals) else f"{idx+1}."
                if mvp["username"]:
                    name = f"@{mvp['username'].lstrip('@')}"
                elif mvp["first_name"]:
                    clean_mname = re.sub(r'[\r\n\t]+', ' ', mvp['first_name']).strip()
                    name = clean_mname or f"ID {mvp['telegram_id']}"
                else:
                    name = f"ID {mvp['telegram_id']}"
                contrib_pct = (mvp["points_total"] / total_sparks * 100) if total_sparks > 0 else 0.0
                lines.append(f"{m} <b>{html.escape(name)}</b> (<code>{mvp['telegram_id']}</code>): <b>{mvp['points_total']:,} Pts</b> ({contrib_pct:.1f}% of sparks)")

        lines.append("\n👉 Run <code>/exportrewards</code> to export complete user dataset as CSV.")
        await send_telegram_message(chat_id, "\n".join(lines))
        return

    elif text in ("/eventstatus", "/pausestatus"):
        from app.database import is_event_paused
        paused = is_event_paused()
        conn = get_db_connection()
        total_p = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        active_p = conn.execute("SELECT COUNT(*) as c FROM users WHERE points_total > 0").fetchone()["c"]
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        conn.close()
        sparks = comm["total_sparks"] if comm else 0
        status_str = "⏸️ <b>PAUSED FOR AUDIT</b>" if paused else "🟢 <b>ACTIVE & RUNNING</b>"
        msg = (
            f"📊 <b>Maha Deepotsav Arena Status</b>\n\n"
            f"• State: {status_str}\n"
            f"• Total Registered: <b>{total_p:,} Players</b>\n"
            f"• Active Scoring: <b>{active_p:,} Players</b>\n"
            f"• Total Sparks: <b>{sparks:,} Sparks</b>\n\n"
            f"{'👉 Games are currently frozen for auditing.' if paused else '👉 Games are actively playable in chat and mini-app.'}\n\n"
            f"💡 <i>Admin tip: Use /adminstats for complete deep-dive participation & contribution analytics.</i>"
        )
        await send_telegram_message(chat_id, msg)
        return

    elif text == "/auditscores":
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return
        conn = get_db_connection()
        top_players = conn.execute(
            "SELECT telegram_id, username, first_name, points_total, tier_level, gharana_id FROM users ORDER BY points_total DESC LIMIT 10"
        ).fetchall()
        tier_counts = conn.execute(
            "SELECT tier_level, COUNT(*) as c FROM users GROUP BY tier_level ORDER BY tier_level DESC"
        ).fetchall()
        comm = conn.execute("SELECT total_sparks, target_sparks FROM community_state WHERE id = 1").fetchone()
        conn.close()
        
        tc_dict = {row["tier_level"]: row["c"] for row in tier_counts}
        stage_num, stage_name = get_stage_info(comm["total_sparks"])
        
        lines = [
            "🏆 <b>FINAL SCORE AUDIT & WINNERS BREAKDOWN</b>\n",
            f"🔥 <b>Community Akhand Diya</b>: <code>{comm['total_sparks']:,} / {comm['target_sparks']:,} Sparks</code>",
            f"✨ <b>Community Stage</b>: <code>{stage_name}</code> (Stage {stage_num})\n",
            "🎖️ <b>Lampbearers by Tier</b>:",
            f"• Tier 5 (5,000+ Pts): <b>{tc_dict.get(5, 0)}</b> guardians",
            f"• Tier 4 (4,000–4,999): <b>{tc_dict.get(4, 0)}</b> lampbearers",
            f"• Tier 3 (2,750–3,999): <b>{tc_dict.get(3, 0)}</b> artisans",
            f"• Tier 2 (1,500–2,749): <b>{tc_dict.get(2, 0)}</b> initiates",
            f"• Tier 1 (500–1,499): <b>{tc_dict.get(1, 0)}</b> novices",
            f"• Tier 0 (0–499): <b>{tc_dict.get(0, 0)}</b> wanderers\n",
            "🌟 <b>Top 10 Final Standings</b>:"
        ]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, p in enumerate(top_players):
            m = medals[idx] if idx < len(medals) else f"{idx+1}."
            if p["username"]:
                name = f"@{p['username'].lstrip('@')}"
            elif p["first_name"]:
                clean_pname = re.sub(r'[\r\n\t]+', ' ', p['first_name']).strip()
                name = clean_pname or f"Player {p['telegram_id']}"
            else:
                name = f"Player {p['telegram_id']}"
            lines.append(f"{m} <b>{html.escape(name)}</b> — <code>{p['points_total']} Pts</code> (Tier {p['tier_level']})")
        
        lines.append("\n👉 Run <code>/exportrewards</code> to download complete CSV spreadsheet!")
        await send_telegram_message(chat_id, "\n".join(lines))
        return

    elif text.startswith("/tierusers") or text.startswith("/tierplayers"):
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await send_telegram_message(chat_id, "Usage: <code>/tierusers &lt;tier_level&gt;</code> (e.g. <code>/tierusers 5</code>)")
            return
        t_level = int(parts[1])
        t_name = get_tier_name(t_level)
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT telegram_id, username, first_name, points_total FROM users WHERE tier_level = ? ORDER BY points_total DESC LIMIT 50",
            (t_level,)
        ).fetchall()
        total_in_tier = conn.execute("SELECT COUNT(*) as c FROM users WHERE tier_level = ?", (t_level,)).fetchone()["c"]
        conn.close()
        
        lines = [f"🏅 <b>Lampbearers in Tier {t_level}: {t_name}</b> (Total: {total_in_tier})\n"]
        if not rows:
            lines.append("<i>No players in this tier yet.</i>")
        else:
            for idx, r in enumerate(rows, 1):
                if r["username"]:
                    u_tag = f"@{r['username'].lstrip('@')}"
                elif r["first_name"]:
                    clean_rname = re.sub(r'[\r\n\t]+', ' ', r['first_name']).strip()
                    u_tag = clean_rname or f"ID {r['telegram_id']}"
                else:
                    u_tag = f"ID {r['telegram_id']}"
                lines.append(f"{idx}. <b>{html.escape(u_tag)}</b> (<code>{r['telegram_id']}</code>): <b>{r['points_total']} Pts</b>")
        if total_in_tier > 50:
            lines.append(f"\n<i>...and {total_in_tier - 50} more. Use /exportrewards for full list.</i>")
        await send_telegram_message(chat_id, "\n".join(lines))
        return

    elif text == "/exportrewards":
        if not is_admin(user_id):
            await send_telegram_message(chat_id, "⛔ <b>Access Denied</b>: Admin privileges required.")
            return
        await send_telegram_message(chat_id, "⏳ Generating rewards CSV export...")
        from app.routes.admin_routes import api_export_rewards
        rows = api_export_rewards(user_id)
        csv_lines = ["Rank,Telegram ID,Username,First Name,Points Total,Tier Level,Tier Name,Reward Category,Reward Details"]
        for r in rows:
            uname = r.username or ""
            fname = (r.first_name or "").replace(",", " ")
            details = (r.details or "").replace(",", ";")
            csv_lines.append(f"{r.rank},{r.telegram_id},{uname},{fname},{r.points_total},{r.tier_level},{r.tier_name},{r.reward_category},{details}")
        csv_bytes = "\n".join(csv_lines).encode("utf-8")
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"ordinal_event_rewards_{now_str}.csv"
        await send_telegram_document(chat_id, csv_bytes, filename, f"📊 <b>Ordinal Legacy Event Rewards Export</b> ({len(rows)} players)")
        await send_bot_log(f"📊 <b>Rewards Exported</b>: Admin `{user_id}` generated rewards CSV ({len(rows)} players).")
        return

    elif text in ("/help", "/commands", "/menu"):
        help_text = (
            f"Ordinal Legacy Event Bot Commands:\n\n"
            f"Festival Games:\n"
            f"/play - Choose games menu (Chat or Mini-App)\n"
            f"/chakri - Spin Chakri Whirl in chat (1 wick, 1-3 pts)\n"
            f"/rangoli - Draw Rangoli in chat (1 wick, 1-3 pts)\n"
            f"/mithai - Feast on Mithai in chat (1 wick, 1-3 pts)\n\n"
            f"Event & Profile:\n"
            f"/mydata - View your complete score, stats & unlocked rewards\n"
            f"/start - Launch festival arena and mini-games\n"
            f"/status - View community Akhand Diya sparks and progress\n"
            f"/house - View your Gharana standing & rank\n"
            f"/boost - View 10-min 2x Gharana Surge schedule & active bonus\n"
            f"/top - View Top 10 Lampbearers on the leaderboard\n"
            f"/shagun - Get your companion referral link\n"
            f"/shubh - Claim daily Shubh refill (+5 wicks & pts)\n"
            f"/widget - View pinned channel Akhand Diya widget\n"
            f"/gharanas - View live Gharana house standings\n"
            f"/tiers - View milestone ladder & rewards (Coins, Pearl...)\n"
            f"/stats - View global event metrics and statistics\n"
            f"/help - Show this command menu\n"
        )
        await send_telegram_message(chat_id, help_text)
        return

    else:
        # Ignore random chatter in groups and private chat.
        # Only notify for unrecognized slash commands in private chat.
        if is_private and text.startswith("/"):
            await send_telegram_message(chat_id, "❓ *Unrecognized Command*: Type /help to view all festival commands.")
        return

async def handle_bot_callback_query(callback_query: Dict[str, Any]):
    callback_id = callback_query.get("id")
    from_user = callback_query.get("from", {})
    user_id = from_user.get("id")
    chat = callback_query.get("message", {}).get("chat", {})
    chat_id = chat.get("id") or user_id
    raw_data = callback_query.get("data", "")

    if not user_id or not chat_id:
        return

    # 1. Anti-spam rate-limit guard (debounced at 200ms to keep clicks feeling instantaneous)
    now = time.time()
    last_click = _BUTTON_CLICK_COOLDOWN.get(user_id, 0.0)
    if now - last_click < 0.20:
        await answer_telegram_callback_query(
            callback_id,
            text="⏳ Please wait a moment before tapping again!",
            show_alert=False
        )
        return
    _BUTTON_CLICK_COOLDOWN[user_id] = now

    # 2. Owner ID Guard: verify if button belongs to this user
    parts = raw_data.split(":")
    action = parts[0]
    owner_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

    PUBLIC_GROUP_ACTIONS = {"claim_diya", "flash_diya", "trivia_ans"}
    if action not in PUBLIC_GROUP_ACTIONS:
        if owner_id is not None and owner_id != user_id:
            await answer_telegram_callback_query(
                callback_id,
                text="⛔ This query belongs to another player. Please use the command yourself in private chat!",
                show_alert=True
            )
            return

    # 3. Stop Telegram loading spinner immediately
    await answer_telegram_callback_query(callback_id)

    # 4. Route action
    if action == "claim_diya":
        if len(parts) < 2 or not parts[1].isdigit():
            return
        event_id = int(parts[1])
        from app.group_activities import claim_flash_diya
        user_fn = from_user.get("first_name", f"Player_{user_id}")
        res = claim_flash_diya(event_id, user_id, user_fn)
        if not res["ok"]:
            await answer_telegram_callback_query(callback_id, text=res["message"], show_alert=True)
            return

        await answer_telegram_callback_query(
            callback_id,
            text=f"✨ Sacred Flame Claimed! +1 Diya Wick (Now: {res['new_wicks']}/10) & +5 Sparks added!",
            show_alert=True
        )

        # Update group message
        msg_id = res.get("message_id")
        grp_chat_id = res.get("chat_id")
        if msg_id and grp_chat_id:
            if res["is_completed"]:
                winners_lines = []
                medals = ["🥇", "🥈", "🥉"] + ["✨"] * 20
                for w_idx, w in enumerate(res["winners"]):
                    m = medals[w_idx] if w_idx < len(medals) else "✨"
                    winners_lines.append(f"{m} <b>#{w_idx+1}. {html.escape(w['name'])}</b> (+1 Wick, +5 Pts)")

                done_text = (
                    "🪔✨ <b>MAHA AARTI: ALL 10 SACRED SPARKS CLAIMED!</b> ✨🪔\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "The celestial flame has illuminated our community!\n"
                    "Total <b>+50 Sparks</b> awakened for the Akhand Jyoti Beacon!\n\n"
                    "👑 <b>Blessed Lampbearers:</b>\n" +
                    "\n".join(winners_lines) +
                    "\n\n<i>Stay vigilant for the next sacred flash drop in @Ordinal_Legacy!</i>"
                )
                await edit_telegram_message(grp_chat_id, msg_id, done_text, reply_markup={"inline_keyboard": []})
            else:
                updated_text = (
                    "🪔✨ <b>MAHA AARTI: SACRED FLASH DIYA AWAKENED!</b> ✨🪔\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "A celestial flame has descended into @Ordinal_Legacy!\n\n"
                    f"The first <b>{res['max_claims']} Lampbearers</b> to light their diya will be blessed with:\n"
                    "• <b>+1 Diya Wick 🪔</b> (Stamina refill)\n"
                    "• <b>+5 Sparks 🔥</b> for the Akhand Jyoti Beacon!\n\n"
                    f"👉 <i>Tap the button below to catch the flame! ({res['remaining']}/{res['max_claims']} sparks remaining)</i>"
                )
                updated_kb = {
                    "inline_keyboard": [
                        [{"text": f"🪔 Light the Sacred Diya ({res['remaining']} left)", "callback_data": f"claim_diya:{event_id}"}]
                    ]
                }
                await edit_telegram_message(grp_chat_id, msg_id, updated_text, reply_markup=updated_kb)
        return

    elif action == "trivia_ans":
        if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
            return
        event_id = int(parts[1])
        chosen_idx = int(parts[2])
        from app.group_activities import answer_trivia_drop
        user_fn = from_user.get("first_name", f"Player_{user_id}")
        res = answer_trivia_drop(event_id, user_id, user_fn, chosen_idx)
        if not res["ok"]:
            await answer_telegram_callback_query(callback_id, text=res["message"], show_alert=True)
            return

        await answer_telegram_callback_query(
            callback_id,
            text=res["message"],
            show_alert=True
        )

        msg_id = res.get("message_id")
        grp_chat_id = res.get("chat_id")
        if msg_id and grp_chat_id and res["is_completed"]:
            winners_lines = []
            medals = ["🥇", "🥈", "🥉"]
            for w in res["winners"]:
                rank = w["rank"]
                m = medals[rank - 1] if rank <= len(medals) else "✨"
                winners_lines.append(f"{m} <b>#{rank}. {html.escape(w['name'])}</b> (+1 Wick, +2 Sparks)")

            done_text = (
                "🏮✨ <b>SACRED FESTIVE TRIVIA COMPLETED!</b> ✨🏮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"❓ <b>Question:</b>\n{html.escape(res['question'])}\n\n"
                f"✅ <b>Correct Answer:</b> <b>{html.escape(res['correct_answer'])}</b>\n\n"
                "👑 <b>Fastest Wisdom Winners:</b>\n" +
                "\n".join(winners_lines) +
                "\n\n<i>Stay tuned for more trivia flash drops in @Ordinal_Legacy!</i>"
            )
            await edit_telegram_message(grp_chat_id, msg_id, done_text, reply_markup={"inline_keyboard": []})
        return
    if action == "verify_groups":
        is_ok, unjoined = await verify_user_all_groups(user_id)
        if not is_ok:
            unjoined_items = "\n".join([f"• {html.escape(name)}" for name, link in unjoined])
            warn_text = (
                f"⚠️ <b>Verification Incomplete!</b>\n\n"
                f"We couldn't confirm your membership in:\n"
                f"{unjoined_items}\n\n"
                f"👉 Please join the group(s) above using the buttons below, then tap <b>Verify & Enter Arena</b> again!"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": f"Join {name}", "url": link}] for name, link in unjoined
                ] + [[{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]]
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
                    [{"text": "Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": f"{settings.MINI_APP_URL}?tg_id={user_id}"}}],
                    [{"text": "Play Mini-Games in Chat", "callback_data": f"menu_play:{user_id}"}],
                    [{"text": "Play Chakri", "callback_data": f"play_chakri:{user_id}"},
                     {"text": "Play Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                     {"text": "Play Mithai", "callback_data": f"play_mithai:{user_id}"}],
                    [{"text": "Claim Shubh Refill (+5 Wicks & Pts)", "callback_data": f"cmd_shubh:{user_id}"}],
                    [{"text": "My Shagun Invite Link", "callback_data": f"cmd_shagun:{user_id}"}]
                ]
            }
        )
        return

    elif action == "menu_play":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/play"}
        await handle_bot_message(fake_msg)
    elif action == "play_chakri":
        await run_in_chat_chakri(chat_id, user_id)
    elif action == "play_rangoli":
        await run_in_chat_rangoli(chat_id, user_id)
    elif action == "play_mithai":
        await run_in_chat_mithai(chat_id, user_id)

    elif action == "cmd_shagun":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/shagun"}
        await handle_bot_message(fake_msg)
    elif action == "cmd_status":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/status"}
        await handle_bot_message(fake_msg)
    elif action == "cmd_mydata":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/mydata"}
        await handle_bot_message(fake_msg)
    elif action == "cmd_shubh":
        try:
            res = claim_shubh_refill(user_id)
            await send_telegram_message(chat_id, f"✨ *{res['message']}*")
        except Exception as e:
            await send_telegram_message(chat_id, f"⚠️ {getattr(e, 'detail', str(e))}")
    elif action == "cmd_gharanas":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/gharanas"}
        await handle_bot_message(fake_msg)
    elif action == "cmd_tiers":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/tiers"}
        await handle_bot_message(fake_msg)
    elif action == "cmd_boost":
        fake_msg = {"chat": {"id": chat_id}, "from": from_user, "text": "/boost"}
        await handle_bot_message(fake_msg)
    elif action == "cpa":
        # parts: ["cpa", <user_id>, <ans_idx>, <token>]
        if len(parts) >= 4:
            ans_idx = int(parts[2])
            tok = ":".join(parts[3:])
            from app.captcha_engine import verify_captcha_answer
            ok, msg = verify_captcha_answer(user_id, ans_idx, tok)
            if ok:
                await send_telegram_message(chat_id, f"✅ *Sacred Jyoti Check Passed!* 🎉\n\nYou are verified as a human Lampbearer. You can now freely play all mini-games!")
                await send_bot_log(f"✅ Player `{user_id}` successfully solved Sacred Jyoti Captcha.")
            else:
                await send_telegram_message(chat_id, f"❌ *Incorrect Answer!* Try this fresh check:")
                await send_captcha_prompt(chat_id, user_id, "Anti-Automation Verification Retry:")
        return

async def handle_bot_chat_member(chat_member_update: Dict[str, Any]):
    """
    Triggered when a user joins, leaves, or is removed from a group or channel.
    If a user leaves any official group chat, revoke verification and notify them to re-verify.
    """
    try:
        new_member = chat_member_update.get("new_chat_member", {})
        status = new_member.get("status")
        user_info = new_member.get("user", {})
        user_id = user_info.get("id")
        
        if not user_id or user_info.get("is_bot") or is_admin(user_id):
            return

        chat = chat_member_update.get("chat", {})
        chat_username = (chat.get("username") or "").lower()
        chat_title = chat.get("title") or "Official Community Group"
        chat_id_str = str(chat.get("id", ""))

        official_handles = {"ordinallegacy", "ordinallegacyeventinfo", "ordinal_legacy"}
        is_official = chat_username in official_handles or any(h in chat_title.lower() for h in ["ordinal legacy", "common discussion", "event info"])
        if not is_official:
            for glink in (settings.GROUP_LINK_1, settings.GROUP_LINK_2, settings.GROUP_LINK_3):
                h = glink.split("t.me/")[-1].strip("/").lower()
                if h and (h == chat_username or h in chat_id_str):
                    is_official = True
                    break
        
        if not is_official:
            return

        if status in ("left", "kicked", "banned"):
            conn = get_db_connection()
            with conn:
                conn.execute("UPDATE users SET joined_groups = 0 WHERE telegram_id = ?", (user_id,))
            conn.close()
            
            print(f"[GROUP LEAVE DETECTED]: User {user_id} left {chat_title} (@{chat_username}). Verification reset to 0.")
            
            notice_msg = (
                f"⚠️ <b>Official Group Membership Update</b>\n\n"
                f"We noticed that you left our community group: <b>{html.escape(chat_title)}</b>.\n\n"
                f"Active membership in all official groups is required to participate in Maha Deepotsav and play mini-games.\n\n"
                f"👉 Please rejoin the group using the button below and tap <b>Verify & Enter Arena</b> to resume playing!"
            )
            rejoin_url = f"https://t.me/{chat_username}" if chat_username else settings.GROUP_LINK_1
            kb = {
                "inline_keyboard": [
                    [{"text": f"Rejoin {chat_title}", "url": rejoin_url}],
                    [{"text": "Verify & Enter Arena", "callback_data": f"verify_groups:{user_id}"}]
                ]
            }
            await send_telegram_message(user_id, notice_msg, reply_markup=kb)
            await send_bot_log(f"🚪 <b>Player Left Group</b>: User <code>{user_id}</code> left <b>{html.escape(chat_title)}</b>. Verification revoked.")
            
        elif status in ("member", "administrator", "creator", "restricted"):
            print(f"[GROUP JOIN DETECTED]: User {user_id} joined {chat_title}.")
    except Exception as e:
        print(f"[CHAT MEMBER UPDATE ERROR]: {e}")