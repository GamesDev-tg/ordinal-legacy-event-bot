import os
from typing import List

class Settings:
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "mock_bot_token_for_dev")
    BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "OrdinalLegacyEventBot")
    MINI_APP_URL: str = os.getenv("MINI_APP_URL", "http://localhost:8000")
    
    _admin_ids_str: str = os.getenv("ADMIN_TELEGRAM_IDS", "123456789")
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
    MIN_GAME_DURATION_SECONDS: int = int(os.getenv("MIN_GAME_DURATION_SECONDS", "12"))
    STAMINA_BANK_CAP: int = int(os.getenv("STAMINA_BANK_CAP", "10"))
    STAMINA_REGEN_MINUTES: int = int(os.getenv("STAMINA_REGEN_MINUTES", "15"))
    
    TIER_THRESHOLDS = {
        0: 0,
        1: 100,
        2: 220,
        3: 380,
        4: 550,
        5: 750
    }
    
    GHARANAS = {
        1: "Surya Gharana",
        2: "Agni Gharana",
        3: "Chandra Gharana",
        4: "Vayu Gharana"
    }

settings = Settings()
