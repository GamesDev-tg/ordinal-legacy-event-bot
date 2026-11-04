from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class TelegramAuthRequest(BaseModel):
    init_data: str

class UserProfile(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    gharana_id: int
    gharana_name: str
    points_total: int
    diya_wicks: int
    tier_level: int
    tier_name: str
    companion: Optional[Dict[str, Any]] = None
    referral_points_earned: int = 0
    total_referrals_count: int = 0
    # Spec aliases & UX enrichments
    gharana: Optional[str] = None
    points: Optional[int] = None
    wicks: Optional[int] = None
    tier: Optional[int] = None
    partner: Optional[Dict[str, Any]] = None
    shubh_refill_available: bool = True
    seconds_until_next_wick: int = 0

class AuthResponse(BaseModel):
    success: bool
    user: UserProfile
    community_sparks: int
    target_sparks: int
    current_stage: int

class GameStartRequest(BaseModel):
    game_type: int = Field(..., ge=1, le=3, description="1: Chakri, 2: Rangoli, 3: Mithai")

class GameStartResponse(BaseModel):
    session_id: str
    seed: str
    nonce: str
    wicks_remaining: int

class GameFinishRequest(BaseModel):
    session_id: str
    nonce: str
    raw_score: int = Field(..., ge=1, le=3, description="Strictly 1, 2, or 3 points")
    duration_ms: int

class GameFinishResponse(BaseModel):
    success: bool
    points_awarded: int
    new_user_total: int
    community_total: int
    tier_unlocked: bool
    new_tier_level: int
    tier_name: str

class ReferralClaimRequest(BaseModel):
    referrer_telegram_id: int

class ReferralClaimResponse(BaseModel):
    success: bool
    is_companion: bool
    referrer_awarded: bool = True
    referral_points_earned: int = 0
    points_awarded_to_referrer: int = 0
    partner_name: Optional[str] = None
    message: str

class GiftWickResponse(BaseModel):
    success: bool
    message: str

class ShubhRefillResponse(BaseModel):
    success: bool
    wicks_added: int
    wicks_total: int
    message: str

class AdminAddPointsRequest(BaseModel):
    admin_telegram_id: int
    target_telegram_id: int
    points_to_add: int

class AdminAddPointsResponse(BaseModel):
    success: bool
    target_telegram_id: int
    points_added: int
    new_total: int
    new_tier: int
    community_total: int

class CommunityStateResponse(BaseModel):
    total_sparks: int
    target_sparks: int
    progress_percentage: float
    current_stage: int
    stage_name: str
    active_players_count: int
    top_gharanas: List[Dict[str, Any]]

class RewardExportRow(BaseModel):
    rank: int
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    points_total: int
    tier_level: int
    tier_name: str
    reward_category: str
    details: str

class AdminQueryRequest(BaseModel):
    admin_telegram_id: int
    query: str

class AdminQueryResponse(BaseModel):
    success: bool
    query_type: str
    rows_affected: Optional[int] = None
    columns: Optional[List[str]] = None
    data: Optional[List[Dict[str, Any]]] = None
    message: str

class AdminTierUsersResponse(BaseModel):
    success: bool
    tier_level: int
    tier_name: str
    total_users: int
    users: List[Dict[str, Any]]

class AdminResetEventRequest(BaseModel):
    admin_telegram_id: int
    confirm: bool = False

class AdminResetEventResponse(BaseModel):
    success: bool
    message: str
    timestamp: str

class AdminBackupResponse(BaseModel):
    success: bool
    total_users: int
    total_referrals: int
    total_games: int
    community_sparks: int
    timestamp_utc: str
    backup_data: Dict[str, Any]
