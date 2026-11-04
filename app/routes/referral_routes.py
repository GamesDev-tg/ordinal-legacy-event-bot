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
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = process_referral_claim(req.referrer_telegram_id, user_id)
    return ReferralClaimResponse(**res)

@router.post("/gift_wick", response_model=GiftWickResponse)
def api_gift_wick(
    authorization: Optional[str] = Header(None),
    x_telegram_id: Optional[str] = Header(None)
):
    user_id = extract_telegram_id(authorization, x_telegram_id)
    res = send_companion_wick_gift(user_id)
    return GiftWickResponse(**res)
