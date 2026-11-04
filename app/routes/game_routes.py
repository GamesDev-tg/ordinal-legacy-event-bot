from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from app.models import GameStartRequest, GameStartResponse, GameFinishRequest, GameFinishResponse, ShubhRefillResponse
from app.game_engine import start_game_session, finish_game_session, claim_shubh_refill
from app.auth import verify_telegram_init_data

router = APIRouter(prefix="/api/game", tags=["Mini-Games"])

def extract_telegram_id(authorization: Optional[str], x_telegram_id: Optional[str]) -> int:
    if x_telegram_id and x_telegram_id.isdigit():
        return int(x_telegram_id)
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    data = verify_telegram_init_data(authorization)
    return data["user"]["id"]

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
