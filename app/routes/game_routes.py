from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from typing import Optional
from app.config import settings
from app.models import GameStartRequest, GameStartResponse, GameFinishRequest, GameFinishResponse, ShubhRefillResponse
from app.game_engine import start_game_session, finish_game_session, claim_shubh_refill
from app.auth import verify_telegram_init_data
from app.database import get_db_connection

router = APIRouter(prefix="/api/game", tags=["Mini-Games"])

def extract_telegram_id(authorization: Optional[str], x_telegram_id: Optional[str]) -> int:
    user_id = None
    if x_telegram_id and x_telegram_id.isdigit():
        user_id = int(x_telegram_id)
    elif authorization:
        data = verify_telegram_init_data(authorization)
        user_id = data.get("user", {}).get("id")
    
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail="Unauthorized: Valid Telegram User ID required.")

    conn = get_db_connection()
    user = conn.execute("SELECT id, joined_groups FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        from app.bot import register_user_if_new
        register_user_if_new(user_id, f"player_{user_id}", f"Player_{user_id}")
        conn = get_db_connection()
        user = conn.execute("SELECT id, joined_groups FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
        conn.close()

    from app.bot import is_admin, is_mock_token
    if not user["joined_groups"] and not is_admin(user_id) and not is_mock_token():
        raise HTTPException(status_code=403, detail="Unauthorized: You must join all 3 official community groups and verify in the bot first!")

    return user_id

@router.post("/start", response_model=GameStartResponse)
def api_game_start(
    req: GameStartRequest,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    from app.captcha_engine import is_user_captcha_locked, get_or_create_captcha
    from app.database import is_event_paused
    from app.bot import is_admin
    user_id = extract_telegram_id(authorization, x_telegram_id)
    if is_event_paused() and not is_admin(user_id):
        raise HTTPException(
            status_code=403,
            detail="⏳ The festival games are currently paused by administrators for score auditing. Final scores and winners will be announced soon!"
        )
    if is_user_captcha_locked(user_id):
        ch = get_or_create_captcha(user_id)
        raise HTTPException(
            status_code=403,
            detail={
                "captcha_required": True,
                "message": "Sacred Jyoti Verification Required: Verify human presence before continuing.",
                "question": ch["question"],
                "options": ch["options"],
                "token": ch["token"]
            }
        )
    res = start_game_session(user_id, req.game_type)
    # Non-blocking fire-and-forget log (runs in background thread to not block response)
    import threading
    game_names = {1: "Chakri Whirl", 2: "Rangoli Trace", 3: "Mithai Catcher"}
    g_title = game_names.get(req.game_type, f"Game {req.game_type}")
    threading.Thread(
        target=__import__('app.bot', fromlist=['send_bot_log_sync']).send_bot_log_sync,
        args=(f"🕹️ Player <code>{user_id}</code> started {g_title} (Wicks remaining: {res['wicks_remaining']}).",),
        daemon=True
    ).start()
    return GameStartResponse(**res)

@router.post("/captcha_verify")
def api_captcha_verify(
    req: dict,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    from app.captcha_engine import verify_captcha_answer, get_or_create_captcha
    user_id = extract_telegram_id(authorization, x_telegram_id)
    answer_idx = int(req.get("answer_index", -1))
    token = req.get("token")
    ok, msg = verify_captcha_answer(user_id, answer_idx, token)
    from app.bot import send_bot_log_sync
    send_bot_log_sync(f"🛡️ Player <code>{user_id}</code> Sacred Jyoti Captcha: {'✅ PASSED' if ok else '❌ FAILED'}.")
    res = {"success": ok, "message": msg}
    if not ok:
        new_ch = get_or_create_captcha(user_id)
        res["new_challenge"] = {
            "question": new_ch["question"],
            "options": new_ch["options"],
            "token": new_ch["token"]
        }
    return res

@router.post("/finish", response_model=GameFinishResponse)
def api_game_finish(
    req: GameFinishRequest,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    import threading
    from app.cache import invalidate_event_cache
    from app.captcha_engine import record_game_play_and_check_captcha
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = finish_game_session(user_id, req.session_id, req.nonce, req.raw_score, req.duration_ms)
    invalidate_event_cache(user_id)
    record_game_play_and_check_captcha(user_id)
    log_msg = f"🎮 Player `{user_id}` completed mini-game run (+{res['points_awarded']} Sparks). Total: *{res['new_user_total']} Pts* | Community: *{res['community_total']:,} Sparks*"
    if res.get("tier_unlocked"):
        log_msg += f"\n🏆 *TIER ASCENSION*: Player `{user_id}` unlocked *{res['tier_name']}* (Tier {res['new_tier_level']})!"
    # Non-blocking fire-and-forget log
    threading.Thread(
        target=__import__('app.bot', fromlist=['send_bot_log_sync']).send_bot_log_sync,
        args=(log_msg,),
        daemon=True
    ).start()
    return GameFinishResponse(**res)

@router.post("/shubh_refill", response_model=ShubhRefillResponse)
def api_shubh_refill(
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    import threading
    from app.cache import invalidate_event_cache
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = claim_shubh_refill(user_id)
    invalidate_event_cache(user_id)
    threading.Thread(
        target=__import__('app.bot', fromlist=['send_bot_log_sync']).send_bot_log_sync,
        args=(f"✨ Player `{user_id}` claimed Shubh Muhurat Blessing (+5 wicks & pts). Score: *{res['points_total']} Pts*",),
        daemon=True
    ).start()
    return ShubhRefillResponse(**res)
