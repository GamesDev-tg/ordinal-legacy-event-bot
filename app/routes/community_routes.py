from fastapi import APIRouter
from app.models import CommunityStateResponse
from app.database import get_db_connection, get_stage_info
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
    for r in gharana_rows:
        gid = r["gharana_id"]
        top_gharanas.append({
            "gharana_id": gid,
            "name": settings.GHARANAS.get(gid, f"Gharana {gid}"),
            "members": r["total_members"],
            "total_points": r["total_points"] or 0,
            "avg_points": round(float(r["avg_points"] or 0.0), 1)
        })
    conn.close()
    
    resp = CommunityStateResponse(
        total_sparks=total_sparks,
        target_sparks=target_sparks,
        progress_percentage=pct,
        current_stage=stage_num,
        stage_name=stage_name,
        active_players_count=active_count,
        top_gharanas=top_gharanas
    )
    # Cache for 5 seconds in temp cache to support hundreds of concurrent players
    try:
        set_cache("api_community_state", resp.model_dump() if hasattr(resp, "model_dump") else resp.dict(), ttl_seconds=5.0)
    except Exception:
        pass

    return resp
