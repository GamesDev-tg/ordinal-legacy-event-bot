import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routes.auth_routes import router as auth_router
from app.routes.game_routes import router as game_router
from app.routes.referral_routes import router as referral_router
from app.routes.community_routes import router as community_router
from app.routes.admin_routes import router as admin_router
from app.bot import handle_bot_message, handle_bot_callback_query

app = FastAPI(
    title="Ordinal Legacy Event Bot API",
    description="Backend API for the Diwali Maha Deepotsav Telegram Mini App & Bot",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_performance_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"
    elif path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
    return response

_DB_INITIALIZED = False

def ensure_db_initialized():
    global _DB_INITIALIZED
    if not _DB_INITIALIZED:
        try:
            init_db()
            _DB_INITIALIZED = True
        except Exception as e:
            print(f"[ENSURE_DB_INITIALIZED_ERROR]: {e}")

@app.on_event("startup")
def on_startup():
    ensure_db_initialized()
    print("Database initialized successfully.")

app.include_router(auth_router)
app.include_router(game_router)
app.include_router(referral_router)
app.include_router(community_router)
app.include_router(admin_router)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    ensure_db_initialized()
    try:
        update = await request.json()
        if "message" in update:
            try:
                await handle_bot_message(update["message"])
            except Exception as e:
                print(f"[HANDLE_BOT_MESSAGE_ERROR]: {e}")
        elif "callback_query" in update:
            try:
                await handle_bot_callback_query(update["callback_query"])
            except Exception as e:
                print(f"[HANDLE_CALLBACK_QUERY_ERROR]: {e}")
        elif "chat_member" in update:
            from app.bot import handle_bot_chat_member
            await handle_bot_chat_member(update["chat_member"])
        elif "my_chat_member" in update:
            from app.bot import handle_bot_chat_member
            await handle_bot_chat_member(update["my_chat_member"])
        return {"ok": True}
    except Exception as e:
        print(f"Error handling webhook update: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/api/init_db")
def api_init_db():
    init_db()
    return {"ok": True, "message": "Database initialized and schema verified."}

@app.get("/api/cron/flash_diya")
async def api_cron_flash_diya():
    from app.database import get_system_setting
    from app.group_activities import create_flash_diya, record_event_message_id
    from app.bot import send_telegram_message_with_id
    stored_group = get_system_setting("ordinal_legacy_group_chat_id", "")
    cfg_id = getattr(settings, "ORDINAL_LEGACY_CHAT_ID", "")
    target_chat = None
    if cfg_id and str(cfg_id).lstrip("-").isdigit():
        target_chat = int(cfg_id)
    elif stored_group and stored_group.lstrip("-").isdigit():
        target_chat = int(stored_group)
    
    if not target_chat:
        return {"ok": False, "message": "No @Ordinal_Legacy group ID detected yet."}

    event_id, text, kb = create_flash_diya(target_chat, max_claims=10)
    ok, msg_id = await send_telegram_message_with_id(target_chat, text, kb)
    if ok and msg_id:
        record_event_message_id(event_id, msg_id)
        return {"ok": True, "event_id": event_id, "chat_id": target_chat, "message_id": msg_id}
    return {"ok": False, "message": "Failed to send flash diya"}

@app.get("/api/cron/trivia")
async def api_cron_trivia():
    from app.database import get_system_setting
    from app.group_activities import create_trivia_drop, record_event_message_id
    from app.bot import send_telegram_message_with_id
    stored_group = get_system_setting("ordinal_legacy_group_chat_id", "")
    cfg_id = getattr(settings, "ORDINAL_LEGACY_CHAT_ID", "")
    target_chat = None
    if cfg_id and str(cfg_id).lstrip("-").isdigit():
        target_chat = int(cfg_id)
    elif stored_group and stored_group.lstrip("-").isdigit():
        target_chat = int(stored_group)
    
    if not target_chat:
        return {"ok": False, "message": "No @Ordinal_Legacy group ID detected yet."}

    event_id, text, kb = create_trivia_drop(target_chat)
    ok, msg_id = await send_telegram_message_with_id(target_chat, text, kb)
    if ok and msg_id:
        record_event_message_id(event_id, msg_id)
        return {"ok": True, "event_id": event_id, "chat_id": target_chat, "message_id": msg_id}
    return {"ok": False, "message": "Failed to send trivia"}

@app.get("/api/set_webhook")
async def api_set_webhook():
    import httpx
    if settings.BOT_TOKEN == "mock_bot_token_for_dev":
        return {"ok": True, "mock": True}
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/setWebhook"
    webhook_url = "https://ordinal-legacy-event-bot.vercel.app/webhook"
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query", "chat_member", "my_chat_member"],
        "drop_pending_updates": False
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/cron/backup")
async def api_cron_backup():
    from app.bot import dispatch_backup_snapshot
    ok = await dispatch_backup_snapshot(reason="Automated 6-Hour Scheduled Cron")
    return {"ok": ok, "message": "6-hour backup snapshot dispatched to recovery group" if ok else "Backup group not configured or dispatch completed"}

@app.get("/api/cron/referrals")
def api_cron_referrals():
    from app.referral_engine import reconcile_all_referrals
    res = reconcile_all_referrals()
    return {"ok": True, "result": res}

@app.get("/api/sync_commands")
async def api_sync_commands():
    from app.bot import sync_telegram_bot_commands
    ok = await sync_telegram_bot_commands()
    return {"ok": ok, "message": "Bot commands synchronized with Telegram BotFather" if ok else "Failed to sync"}

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Ordinal Legacy Event Bot", "version": "3.0.0"}

@app.get("/debug")
def debug_check():
    from app.database import is_postgres
    token_len = len(settings.BOT_TOKEN) if settings.BOT_TOKEN else 0
    token_preview = (settings.BOT_TOKEN[:6] + "..." + settings.BOT_TOKEN[-4:]) if token_len > 12 else ("mock" if settings.BOT_TOKEN == "mock_bot_token_for_dev" else "short")
    return {
        "bot_token_configured": settings.BOT_TOKEN != "mock_bot_token_for_dev",
        "bot_token_preview": token_preview,
        "bot_username": settings.BOT_USERNAME,
        "database_mode": "postgres" if is_postgres() else "sqlite",
        "admin_ids_count": len(settings.ADMIN_IDS),
        "mini_app_url": settings.MINI_APP_URL
    }

@app.get("/api/webhook_info")
async def get_tg_webhook_info():
    import httpx
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getWebhookInfo"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            return resp.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/test_send")
async def test_send(chat_id: int):
    import httpx
    from app.enums import ParseMode
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": "🪔 <b>Deepotsav System Online!</b>\nBot connection is fully active.", "parse_mode": ParseMode.HTML.value}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return {"status_code": resp.status_code, "body": resp.json()}
    except Exception as e:
        return {"error": str(e)}

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Ordinal Legacy Event Bot API is running. Mount static frontend at static/index.html"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
