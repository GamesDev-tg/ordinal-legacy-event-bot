import os
import sys
import uvicorn
import argparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import init_db
from app.config import settings

def main():
    parser = argparse.ArgumentParser(description="Start Ordinal Legacy Event Bot Live Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--token", type=str, default=None, help="Telegram Bot Token")
    parser.add_argument("--url", type=str, default=None, help="Live public URL for the mini-app")
    args = parser.parse_args()

    if args.token:
        os.environ["TELEGRAM_BOT_TOKEN"] = args.token
        settings.BOT_TOKEN = args.token
    if args.url:
        os.environ["MINI_APP_URL"] = args.url
        settings.MINI_APP_URL = args.url

    # Ensure database is initialized
    init_db()
    print("=" * 65)
    print("   🪔 ORDINAL LEGACY EVENT BOT — LIVE FESTIVAL SERVER")
    print("=" * 65)
    print(f"🚀 Host: {args.host}:{args.port}")
    print(f"🌐 Mini App URL: {settings.MINI_APP_URL}")
    print(f"🤖 Bot Token Configured: {'Yes' if settings.BOT_TOKEN != 'mock_bot_token_for_dev' else 'Dev/Mock Mode'}")
    print(f"🪔 Global Target: {settings.GLOBAL_MILESTONE_TARGET:,} Sparks")
    print("=" * 65 + "\n")

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
