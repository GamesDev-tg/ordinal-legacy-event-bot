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

@app.on_event("startup")
def on_startup():
    init_db()
    print("Database initialized successfully.")

app.include_router(auth_router)
app.include_router(game_router)
app.include_router(referral_router)
app.include_router(community_router)
app.include_router(admin_router)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        if "message" in update:
            await handle_bot_message(update["message"])
        elif "callback_query" in update:
            await handle_bot_callback_query(update["callback_query"])
        return {"ok": True}
    except Exception as e:
        print(f"Error handling webhook update: {e}")
        return {"ok": False, "error": str(e)}

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
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": "🪔 *Deepotsav System Online!*\nBot connection is fully active.", "parse_mode": "Markdown"}
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
