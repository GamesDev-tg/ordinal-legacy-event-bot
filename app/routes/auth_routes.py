from fastapi import APIRouter, HTTPException
from app.models import TelegramAuthRequest, AuthResponse, UserProfile
from app.auth import verify_telegram_init_data
from app.database import get_db_connection, get_tier_name, get_stage_info
from app.bot import register_user_if_new
from app.game_engine import update_user_stamina, get_seconds_until_next_wick
import datetime
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def get_full_user_profile(telegram_id: int) -> UserProfile:
    conn = get_db_connection()
    with conn:
        update_user_stamina(conn, telegram_id)
        user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if not user:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")
            
        comp_row = conn.execute(
            '''SELECT u.telegram_id, u.first_name, u.username, u.tier_level
               FROM referrals r
               JOIN users u ON u.telegram_id = (
                   CASE WHEN r.referrer_id = ? THEN r.referred_id ELSE r.referrer_id END
               )
               WHERE (r.referrer_id = ? OR r.referred_id = ?) AND r.is_companion = 1''',
            (telegram_id, telegram_id, telegram_id)
        ).fetchone()
        
        companion_dict = None
        if comp_row:
            companion_dict = {
                "telegram_id": comp_row["telegram_id"],
                "name": comp_row["first_name"] or f"Player_{comp_row['telegram_id']}",
                "username": comp_row["username"],
                "tier_name": get_tier_name(comp_row["tier_level"])
            }
            
        ref_count = conn.execute(
            "SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?",
            (telegram_id,)
        ).fetchone()["count"]
        
        secs_until_next = get_seconds_until_next_wick(conn, telegram_id)
        today_str = datetime.date.today().isoformat()
        shubh_available = (user["shubh_refill_date"] != today_str)
        
    conn.close()
    
    gharana_name = settings.GHARANAS.get(user["gharana_id"], "Unknown")
    tier_name = get_tier_name(user["tier_level"])
    
    is_v = bool(user["joined_groups"])
    return UserProfile(
        telegram_id=user["telegram_id"],
        username=user["username"],
        first_name=user["first_name"],
        gharana_id=user["gharana_id"],
        gharana_name=gharana_name,
        points_total=user["points_total"],
        diya_wicks=user["diya_wicks"],
        tier_level=user["tier_level"],
        tier_name=tier_name,
        companion=companion_dict,
        referral_points_earned=user["referral_points_earned"],
        total_referrals_count=ref_count,
        # Aliases matching GDD / Blueprint specs
        gharana=gharana_name,
        points=user["points_total"],
        wicks=user["diya_wicks"],
        tier=user["tier_level"],
        partner=companion_dict,
        shubh_refill_available=shubh_available,
        seconds_until_next_wick=secs_until_next,
        joined_groups=is_v,
        is_verified=is_v
    )

@router.post("/telegram", response_model=AuthResponse)
def auth_telegram(req: TelegramAuthRequest):
    verified_data = verify_telegram_init_data(req.init_data)
    user_data = verified_data.get("user", {})
    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="User ID missing from verified payload")
        
    username = user_data.get("username", "")
    first_name = user_data.get("first_name", "Lampbearer")
    register_user_if_new(telegram_id, username, first_name)
    profile = get_full_user_profile(telegram_id)
    
    conn = get_db_connection()
    comm = conn.execute("SELECT total_sparks, target_sparks, current_stage FROM community_state WHERE id = 1").fetchone()
    conn.close()
    
    from app.database import is_event_paused, get_stage_info
    stage_num, stage_desc = get_stage_info(comm["total_sparks"])
    
    from app.bot import send_bot_log_sync
    send_bot_log_sync(f"🌐 Player <code>{telegram_id}</code> (@{username or 'anon'}) launched Maha Deepotsav Mini-App.")

    return AuthResponse(
        success=True,
        user=profile,
        community_sparks=comm["total_sparks"],
        target_sparks=comm["target_sparks"],
        current_stage=stage_num,
        stage_description=stage_desc,
        event_paused=is_event_paused()
    )

@router.get("/demo/{telegram_id}", response_model=AuthResponse)
def auth_demo(telegram_id: int):
    register_user_if_new(telegram_id, f"demo_{telegram_id}", f"DemoUser_{telegram_id}")
    profile = get_full_user_profile(telegram_id)
    conn = get_db_connection()
    comm = conn.execute("SELECT total_sparks, target_sparks, current_stage FROM community_state WHERE id = 1").fetchone()
    conn.close()
    
    from app.database import is_event_paused, get_stage_info
    stage_num, stage_desc = get_stage_info(comm["total_sparks"])
    return AuthResponse(
        success=True,
        user=profile,
        community_sparks=comm["total_sparks"],
        target_sparks=comm["target_sparks"],
        current_stage=stage_num,
        stage_description=stage_desc,
        event_paused=is_event_paused()
    )

@router.post("/widget", response_model=AuthResponse)
def auth_widget(data: dict):
    from app.auth import verify_telegram_widget_data
    verified = verify_telegram_widget_data(data)
    telegram_id = int(verified["id"])
    username = str(verified.get("username") or "")
    first_name = str(verified.get("first_name") or "Lampbearer")
    
    register_user_if_new(telegram_id, username, first_name)
    profile = get_full_user_profile(telegram_id)
    
    conn = get_db_connection()
    comm = conn.execute("SELECT total_sparks, target_sparks, current_stage FROM community_state WHERE id = 1").fetchone()
    conn.close()
    
    from app.database import is_event_paused, get_stage_info
    stage_num, stage_desc = get_stage_info(comm["total_sparks"])
    
    from app.bot import send_bot_log_sync
    send_bot_log_sync(f"🌐 Player <code>{telegram_id}</code> (@{username or 'anon'}) logged in via Web Login Widget.")

    return AuthResponse(
        success=True,
        user=profile,
        community_sparks=comm["total_sparks"],
        target_sparks=comm["target_sparks"],
        current_stage=stage_num,
        stage_description=stage_desc,
        event_paused=is_event_paused()
    )
