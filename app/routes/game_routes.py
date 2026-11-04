from fastapi import APIRouter, Header, HTTPException
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
        raise HTTPException(status_code=403, detail="Unauthorized: You must first start the bot on Telegram to play and contribute sparks.")
    if not user["joined_groups"] and settings.BOT_TOKEN != "mock_bot_token_for_dev":
        raise HTTPException(status_code=403, detail="Unauthorized: You must join all 3 official community groups and verify in the bot first!")

    return user_id

@router.post("/start", response_model=GameStartResponse)
def api_game_start(
    req: GameStartRequest,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = start_game_session(user_id, req.game_type)
    return GameStartResponse(**res)

@router.post("/finish", response_model=GameFinishResponse)
def api_game_finish(
    req: GameFinishRequest,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = finish_game_session(user_id, req.session_id, req.nonce, req.raw_score, req.duration_ms)
    return GameFinishResponse(**res)

@router.post("/shubh_refill", response_model=ShubhRefillResponse)
def api_shubh_refill(
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = claim_shubh_refill(user_id)
    return ShubhRefillResponse(**res)
