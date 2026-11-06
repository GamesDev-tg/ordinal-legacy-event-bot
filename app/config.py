import os
from typing import List

class Settings:
    BOT_TOKEN: str = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "mock_bot_token_for_dev").strip("'\" ")
    BOT_USERNAME: str = (os.getenv("TELEGRAM_BOT_USERNAME") or os.getenv("BOT_USERNAME") or "OrdinalLegacyEventBot").strip("'\" ")
    
    _app_url = (os.getenv("MINI_APP_URL") or "https://ordinal-legacy-event-bot.vercel.app").strip("'\" ")
    if "localhost" in _app_url and (os.getenv("VERCEL") or os.getenv("RENDER")):
        _app_url = "https://ordinal-legacy-event-bot.vercel.app"
    elif not _app_url.startswith("http://") and not _app_url.startswith("https://"):
        _app_url = "https://" + _app_url
    MINI_APP_URL: str = _app_url
    
    _admin_ids_str: str = os.getenv("ADMIN_TELEGRAM_IDS", "123456789,1257427765")
    ADMIN_IDS: List[int] = [int(i.strip()) for i in _admin_ids_str.split(",") if i.strip().isdigit()]
    
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    _db_url: str = os.getenv("DATABASE_URL", "").strip("'\" ")
    _db_path: str = os.getenv("DATABASE_PATH", "").strip("'\" ")
    if _db_url and (_db_url.startswith("postgres://") or _db_url.startswith("postgresql://")):
        DATABASE_PATH: str = _db_url
    elif _db_path and (_db_path.startswith("postgres://") or _db_path.startswith("postgresql://")):
        DATABASE_PATH: str = _db_path
    elif _db_url:
        DATABASE_PATH: str = _db_url
    elif _db_path:
        DATABASE_PATH: str = _db_path
    else:
        DATABASE_PATH: str = "ordinal_event.db"
    
    GLOBAL_MILESTONE_TARGET: int = int(os.getenv("GLOBAL_MILESTONE_TARGET", "200000"))
    MAX_REFERRAL_POINTS: int = int(os.getenv("MAX_REFERRAL_POINTS", "15"))
    MIN_GAME_DURATION_SECONDS: int = int(os.getenv("MIN_GAME_DURATION_SECONDS", "2"))
    STAMINA_BANK_CAP: int = int(os.getenv("STAMINA_BANK_CAP", "10"))
    STAMINA_REGEN_MINUTES: int = int(os.getenv("STAMINA_REGEN_MINUTES", "1"))

    GROUP_LINK_1: str = os.getenv("GROUP_LINK_1", "https://t.me/OrdinalLegacy")
    GROUP_LINK_2: str = os.getenv("GROUP_LINK_2", "https://t.me/OrdinalLegacyEventInfo")
    GROUP_LINK_3: str = os.getenv("GROUP_LINK_3", "https://t.me/Ordinal_Legacy")
    GROUP_NAME_1: str = os.getenv("GROUP_NAME_1", "Ordinal Legacy Main (@OrdinalLegacy)")
    GROUP_NAME_2: str = os.getenv("GROUP_NAME_2", "Ordinal Legacy Events Information (@OrdinalLegacyEventInfo)")
    GROUP_NAME_3: str = os.getenv("GROUP_NAME_3", "Common Discussion (@Ordinal_Legacy)")

    LOGS_CHAT_ID: str = os.getenv("LOGS_CHAT_ID", "").strip("'\" ")
    BACKUP_CHAT_ID: str = os.getenv("BACKUP_CHAT_ID", "").strip("'\" ")
    
    TIER_THRESHOLDS = {
        0: 0,
        1: 500,
        2: 1500,
        3: 2750,
        4: 4000,
        5: 5000
    }
    
    TIER_REWARDS = {
        0: "Welcome Badge",
        1: "🪙 Coins",
        2: "🔮 Pearl",
        3: "🎟 Ticket",
        4: "🐾 Pet",
        5: "All Rewards: 🪙 Coins + 🔮 Pearl + 🎟 Ticket + 🐾 Pet"
    }
    
    GHARANAS = {
        1: "Surya Gharana",
        2: "Agni Gharana",
        3: "Chandra Gharana",
        4: "Vayu Gharana"
    }

settings = Settings()
