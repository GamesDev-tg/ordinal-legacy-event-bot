from fastapi import APIRouter, Header, HTTPException
from typing import Optional
from app.models import ReferralClaimRequest, ReferralClaimResponse, GiftWickResponse
from app.referral_engine import process_referral_claim, send_companion_wick_gift
from app.routes.game_routes import extract_telegram_id

router = APIRouter(prefix="/api/referral", tags=["Referrals & Companions"])

@router.post("/claim", response_model=ReferralClaimResponse)
def api_referral_claim(
    req: ReferralClaimRequest,
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    from app.bot import send_bot_log_sync
    from app.cache import invalidate_event_cache
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = process_referral_claim(req.referrer_telegram_id, user_id)
    invalidate_event_cache(user_id)
    invalidate_event_cache(req.referrer_telegram_id)
    send_bot_log_sync(f"🤝 *Companion / Shagun Invite*: `{req.referrer_telegram_id}` bonded with `{user_id}` (Companion: {res['is_companion']}).")
    return ReferralClaimResponse(**res)

@router.post("/gift_wick", response_model=GiftWickResponse)
def api_gift_wick(
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    from app.bot import send_bot_log_sync
    from app.cache import invalidate_event_cache
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = send_companion_wick_gift(user_id)
    invalidate_event_cache(user_id)
    send_bot_log_sync(f"🪔 *Diya Wick Gift*: Player `{user_id}` gifted a free wick to companion.")
    return GiftWickResponse(**res)
