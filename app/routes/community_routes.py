from fastapi import APIRouter
from app.models import CommunityStateResponse
from app.database import get_db_connection, get_stage_info, is_event_paused
from app.game_engine import get_gharana_boost_status
from app.config import settings
from app.cache import get_cache, set_cache

router = APIRouter(prefix="/api/community", tags=["Community State"])

@router.get("/state", response_model=CommunityStateResponse)
def api_community_state():
    # High-speed temp cache check (sub-millisecond response)
    cached = get_cache("api_community_state")
    if cached is not None:
        try:
            return CommunityStateResponse(**cached)
        except Exception:
            pass

    conn = get_db_connection()
    comm = conn.execute("SELECT total_sparks, target_sparks, current_stage FROM community_state WHERE id = 1").fetchone()
    total_sparks = comm["total_sparks"]
    target_sparks = comm["target_sparks"]
    
    stage_num, stage_name = get_stage_info(total_sparks)
    pct = round(min(100.0, (total_sparks / max(1, target_sparks)) * 100), 2)
    active_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE points_total > 0").fetchone()["count"]
    
    gharana_rows = conn.execute('''
        SELECT 
            u.gharana_id,
            COUNT(u.id) as total_members,
            SUM(u.points_total) as total_points,
            AVG(u.points_total) as avg_points
        FROM users u
        GROUP BY u.gharana_id
        ORDER BY avg_points DESC, total_points DESC
    ''').fetchall()
    
    top_gharanas = []
    existing_gids = set()
    for r in gharana_rows:
        gid = r["gharana_id"]
        existing_gids.add(gid)
        top_gharanas.append({
            "gharana_id": gid,
            "name": settings.GHARANAS.get(gid, f"Gharana {gid}"),
            "members": r["total_members"],
            "total_points": r["total_points"] or 0,
            "avg_points": round(float(r["avg_points"] or 0.0), 1)
        })
    for gid, gname in settings.GHARANAS.items():
        if gid not in existing_gids:
            top_gharanas.append({
                "gharana_id": gid,
                "name": gname,
                "members": 0,
                "total_points": 0,
                "avg_points": 0.0
            })
    top_gharanas.sort(key=lambda g: (g["avg_points"], g["total_points"]), reverse=True)
    conn.close()
    
    paused = is_event_paused()
    
    boost = get_gharana_boost_status()

    resp = CommunityStateResponse(
        total_sparks=total_sparks,
        target_sparks=target_sparks,
        progress_percentage=pct,
        current_stage=stage_num,
        stage_name=stage_name,
        active_players_count=active_count,
        top_gharanas=top_gharanas,
        event_paused=paused,
        active_gharana_boost=boost
    )
    # Cache for 2 seconds to support high concurrency with near-real-time updates
    try:
        set_cache("api_community_state", resp.model_dump() if hasattr(resp, "model_dump") else resp.dict(), ttl_seconds=2.0)
    except Exception:
        pass

    return resp
