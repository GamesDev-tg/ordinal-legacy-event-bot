import datetime
from fastapi import APIRouter, HTTPException, Response
from typing import List
from app.models import (
    AdminAddPointsRequest, AdminAddPointsResponse, RewardExportRow,
    AdminQueryRequest, AdminQueryResponse, AdminTierUsersResponse,
    AdminResetEventRequest, AdminResetEventResponse, AdminBackupResponse
)
from app.config import settings
from app.database import get_db_connection, calculate_tier, get_tier_name, generate_full_backup, reset_event_data, get_stage_info

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])

def check_admin(admin_id: int):
    from app.database import get_all_admin_ids
    if admin_id not in get_all_admin_ids():
        raise HTTPException(status_code=403, detail="Unauthorized: Admin privileges required.")

@router.post("/add_points", response_model=AdminAddPointsResponse)
def api_admin_add_points(req: AdminAddPointsRequest):
    check_admin(req.admin_telegram_id)
    conn = get_db_connection()
    with conn:
        user = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (req.target_telegram_id,)).fetchone()
        if not user:
            conn.close()
            raise HTTPException(status_code=404, detail="Target user not found")
            
        new_total = max(0, user["points_total"] + req.points_to_add)
        new_tier = calculate_tier(new_total)
        
        conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_total, new_tier, req.target_telegram_id))
        comm = conn.execute("SELECT total_sparks FROM community_state WHERE id = 1").fetchone()
        cur_comm = comm["total_sparks"] if comm else 0
        comm_total = max(0, cur_comm + req.points_to_add)
        new_stage, _ = get_stage_info(comm_total)
        conn.execute("UPDATE community_state SET total_sparks = ?, current_stage = ? WHERE id = 1", (comm_total, new_stage))
    conn.close()
    
    from app.cache import invalidate_event_cache
    invalidate_event_cache(req.target_telegram_id)
    
    return AdminAddPointsResponse(
        success=True,
        target_telegram_id=req.target_telegram_id,
        points_added=req.points_to_add,
        new_total=new_total,
        new_tier=new_tier,
        community_total=comm_total
    )

@router.get("/tier_distribution")
def api_tier_distribution(admin_id: int):
    check_admin(admin_id)
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT 
            tier_level,
            COUNT(*) as player_count,
            AVG(points_total) as avg_points
        FROM users
        GROUP BY tier_level
        ORDER BY tier_level DESC
    ''').fetchall()
    conn.close()
    
    dist = []
    for r in rows:
        t = r["tier_level"]
        dist.append({
            "tier_level": t,
            "tier_name": get_tier_name(t),
            "player_count": r["player_count"],
            "avg_points": round(float(r["avg_points"] or 0.0), 1)
        })
    return {"success": True, "distribution": dist}

@router.get("/export_rewards", response_model=List[RewardExportRow])
def api_export_rewards(admin_id: int):
    check_admin(admin_id)
    conn = get_db_connection()
    users = conn.execute('''
        SELECT telegram_id, username, first_name, points_total, tier_level
        FROM users
        ORDER BY points_total DESC, id ASC
    ''').fetchall()
    conn.close()
    
    export_rows = []
    rank = 1
    for u in users:
        pts = u["points_total"]
        t = u["tier_level"]
        t_name = get_tier_name(t)
        category = "Participation"
        details = "Diya Spark Welcome Badge"
        
        if t == 5:
            if rank <= 50:
                category = "Top 50 Sovereign Elite"
                details = "Legendary Sovereign Mukut + Rare Ordinal Inscription + 4 Airdrop Shares"
            else:
                category = "Akhand Sovereign"
                details = "Legendary Sovereign Mukut + 4 Airdrop Shares"
        elif t == 4:
            category = "Deep Mahant"
            details = "Platinum Halo + 2 Airdrop Shares + VIP Discord/Telegram Role + Pet"
        elif t == 3:
            category = "Spark Master"
            details = "Gold Radiating Aura + 1 Guaranteed Airdrop Share"
        elif t == 2:
            tickets = min(10, max(1, pts // 100))
            category = "Rangoli Artisan"
            details = f"Silver Flame Avatar + {tickets} Community Raffle Tickets"
        elif t == 1:
            category = "Diya Sevak"
            details = "Bronze Profile Frame + Exclusive Custom Sticker Pack"
            
        export_rows.append(RewardExportRow(
            rank=rank,
            telegram_id=u["telegram_id"],
            username=u["username"],
            first_name=u["first_name"],
            points_total=pts,
            tier_level=t,
            tier_name=t_name,
            reward_category=category,
            details=details
        ))
        rank += 1
    return export_rows

@router.get("/export_rewards_csv")
def api_export_rewards_csv(admin_id: int):
    rows = api_export_rewards(admin_id)
    csv_lines = ["Rank,Telegram ID,Username,First Name,Points Total,Tier Level,Tier Name,Reward Category,Reward Details"]
    for r in rows:
        uname = r.username or ""
        fname = (r.first_name or "").replace(",", " ")
        details = (r.details or "").replace(",", ";")
        csv_lines.append(f"{r.rank},{r.telegram_id},{uname},{fname},{r.points_total},{r.tier_level},{r.tier_name},{r.reward_category},{details}")
    
    csv_content = "\n".join(csv_lines)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ordinal_legacy_diwali_rewards.csv"}
    )

@router.post("/query", response_model=AdminQueryResponse)
def api_admin_query(req: AdminQueryRequest):
    check_admin(req.admin_telegram_id)
    raw_query = req.query.strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="Empty query provided.")

    upper_query = raw_query.upper()
    # Security filter: permit only SELECT and UPDATE queries
    if upper_query.startswith("SELECT"):
        query_type = "SELECT"
    elif upper_query.startswith("UPDATE"):
        query_type = "UPDATE"
    else:
        raise HTTPException(status_code=400, detail="Only SELECT and UPDATE queries are permitted.")

    # Guard against destructive commands
    forbidden = ["DROP", "ALTER", "ATTACH", "DETACH", "PRAGMA", "VACUUM"]
    for keyword in forbidden:
        if f" {keyword} " in f" {upper_query} ":
            raise HTTPException(status_code=400, detail=f"Destructive keyword '{keyword}' is blocked.")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if query_type == "SELECT":
            cur.execute(raw_query)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(100) # limit to 100 for safety
            data = []
            for r in rows:
                row_dict = {}
                for idx, col in enumerate(cols):
                    row_dict[col] = r[idx]
                data.append(row_dict)
            conn.close()
            return AdminQueryResponse(
                success=True,
                query_type="SELECT",
                columns=cols,
                data=data,
                message=f"Returned {len(data)} rows (max 100 preview)."
            )
        else: # UPDATE
            with conn:
                cur.execute(raw_query)
                affected = cur.rowcount
            conn.close()
            return AdminQueryResponse(
                success=True,
                query_type="UPDATE",
                rows_affected=affected,
                message=f"Query executed successfully. Rows affected: {affected}."
            )
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Database execution error: {str(e)}")

@router.get("/users_by_tier", response_model=AdminTierUsersResponse)
def api_users_by_tier(admin_id: int, tier_level: int):
    check_admin(admin_id)
    if tier_level < 0 or tier_level > 5:
        raise HTTPException(status_code=400, detail="tier_level must be between 0 and 5.")

    conn = get_db_connection()
    rows = conn.execute('''
        SELECT 
            u.id, 
            u.telegram_id, 
            u.username, 
            u.first_name, 
            u.gharana_id, 
            u.points_total, 
            u.diya_wicks,
            u.referral_points_earned,
            (SELECT COUNT(*) FROM referrals r WHERE r.referrer_id = u.telegram_id) as friends_count,
            (SELECT c.referred_id FROM referrals c WHERE c.referrer_id = u.telegram_id AND c.is_companion = 1) as companion_id
        FROM users u
        WHERE u.tier_level = ?
        ORDER BY u.points_total DESC, u.id ASC
    ''', (tier_level,)).fetchall()
    conn.close()

    user_list = []
    for r in rows:
        gid = r["gharana_id"]
        user_list.append({
            "telegram_id": r["telegram_id"],
            "username": r["username"] or "",
            "name": r["first_name"] or f"Player_{r['telegram_id']}",
            "gharana_name": settings.GHARANAS.get(gid, f"Gharana {gid}"),
            "points": r["points_total"],
            "wicks": r["diya_wicks"],
            "shagun_points": r["referral_points_earned"],
            "friends_invited": r["friends_count"],
            "companion_id": r["companion_id"]
        })

    return AdminTierUsersResponse(
        success=True,
        tier_level=tier_level,
        tier_name=get_tier_name(tier_level),
        total_users=len(user_list),
        users=user_list
    )

@router.post("/reset_wicks")
def api_admin_reset_wicks(admin_id: int, target_telegram_id: int):
    check_admin(admin_id)
    conn = get_db_connection()
    with conn:
        u = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (target_telegram_id,)).fetchone()
        if not u:
            conn.close()
            raise HTTPException(status_code=404, detail="Target user not found.")
        conn.execute("UPDATE users SET diya_wicks = ? WHERE telegram_id = ?", (settings.STAMINA_BANK_CAP, target_telegram_id))
    conn.close()
    from app.cache import invalidate_event_cache
    invalidate_event_cache(target_telegram_id)
    return {"success": True, "target_telegram_id": target_telegram_id, "wicks": settings.STAMINA_BANK_CAP, "message": "Restored full Diya Wicks."}

@router.get("/stats")
def api_admin_stats(admin_id: int):
    check_admin(admin_id)
    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    comm = conn.execute("SELECT total_sparks, target_sparks FROM community_state WHERE id = 1").fetchone()
    total_sessions = conn.execute("SELECT COUNT(*) as c FROM game_sessions WHERE is_valid = 1").fetchone()["c"]

    score_counts = conn.execute('''
        SELECT score_awarded, COUNT(*) as c 
        FROM game_sessions 
        WHERE is_valid = 1 
        GROUP BY score_awarded
    ''').fetchall()
    score_dist = {r["score_awarded"]: r["c"] for r in score_counts}

    companions_count = conn.execute("SELECT COUNT(*) as c FROM referrals WHERE is_companion = 1").fetchone()["c"]
    gifts_count = conn.execute("SELECT COUNT(*) as c FROM partner_wick_gifts").fetchone()["c"]
    conn.close()

    return {
        "success": True,
        "total_users": total_users,
        "community_sparks": comm["total_sparks"],
        "target_sparks": comm["target_sparks"],
        "progress_pct": round(min(100.0, (comm["total_sparks"] / max(1, comm["target_sparks"])) * 100), 2),
        "total_game_sessions": total_sessions,
        "scores_awarded": {
            "3_points": score_dist.get(3, 0),
            "2_points": score_dist.get(2, 0),
            "1_point": score_dist.get(1, 0)
        },
        "bonded_companions": companions_count,
        "wick_gifts_exchanged": gifts_count
    }

@router.post("/reset_event", response_model=AdminResetEventResponse)
def api_admin_reset_event(req: AdminResetEventRequest):
    check_admin(req.admin_telegram_id)
    if not req.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required! Pass confirm=true to verify you want to reset all event scores and wicks."
        )
    generate_full_backup()
    res = reset_event_data()
    from app.cache import clear_all_cache
    clear_all_cache()
    return AdminResetEventResponse(
        success=True,
        message=res["message"],
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

@router.get("/backup", response_model=AdminBackupResponse)
def api_admin_backup(admin_id: int):
    check_admin(admin_id)
    snap = generate_full_backup()
    return AdminBackupResponse(
        success=True,
        total_users=snap["total_users"],
        total_referrals=snap["total_referrals"],
        total_games=snap["total_games"],
        community_sparks=snap["community_sparks"],
        timestamp_utc=snap["timestamp_utc"],
        backup_data=snap["data"]
    )
