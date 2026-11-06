import os
import json
import time
import tempfile
import threading
from typing import Any, Optional, Dict

CACHE_FILE_PATH = os.path.join(tempfile.gettempdir(), "ordinal_event_cache.json")
_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_write_count = 0

# Load any existing cache from temp file on startup
try:
    if os.path.exists(CACHE_FILE_PATH):
        with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            now = time.time()
            for k, v in loaded.items():
                if isinstance(v, dict) and v.get("expires_at", 0) > now:
                    _MEMORY_CACHE[k] = v
except Exception:
    pass

def _sync_to_disk():
    try:
        now = time.time()
        with _CACHE_LOCK:
            data = {k: v for k, v in _MEMORY_CACHE.items() if isinstance(v, dict) and v.get("expires_at", 0) > now}
        temp_file = CACHE_FILE_PATH + f".tmp_{os.getpid()}"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(temp_file, CACHE_FILE_PATH)
    except Exception:
        pass

def get_cache(key: str, default: Any = None) -> Any:
    """
    Retrieves a cached value from high-speed in-memory cache or temp cache file.
    Returns default if expired or not found.
    """
    now = time.time()
    with _CACHE_LOCK:
        entry = _MEMORY_CACHE.get(key)
        if entry and isinstance(entry, dict) and entry.get("expires_at", 0) > now:
            return entry.get("value")
    return default

def set_cache(key: str, value: Any, ttl_seconds: float = 30.0):
    """
    Saves a value in fast in-memory cache.
    Disk sync is deferred to avoid blocking hot paths during live events.
    """
    now = time.time()
    entry = {"value": value, "expires_at": now + ttl_seconds}
    with _CACHE_LOCK:
        _MEMORY_CACHE[key] = entry
    # Only sync to disk every 30 writes to avoid blocking under high load
    global _write_count
    _write_count += 1
    if _write_count % 30 == 0:
        _sync_to_disk()

def delete_cache(key: str):
    """
    Invalidates a specific cached key from memory and temp cache file.
    """
    with _CACHE_LOCK:
        _MEMORY_CACHE.pop(key, None)
    _sync_to_disk()

def clear_all_cache():
    """
    Clears all cached entries from memory and removes the temp cache file.
    """
    with _CACHE_LOCK:
        _MEMORY_CACHE.clear()
    try:
        if os.path.exists(CACHE_FILE_PATH):
            os.remove(CACHE_FILE_PATH)
    except Exception:
        pass

def invalidate_event_cache(user_id: Optional[int] = None):
    """
    Instantly invalidates all community, leaderboard, and user caches so bot
    and mini-app display 100% synchronized, up-to-the-millisecond progress.
    """
    delete_cache("api_community_state")
    delete_cache("bot_cmd_top")
    delete_cache("bot_cmd_stats")
    delete_cache("bot_cmd_gharanas")
    delete_cache("bot_cmd_widget")
    # Also invalidate event pause setting cache so pause/resume takes effect immediately
    delete_cache("setting_event_paused")
    if user_id:
        delete_cache(f"reg_user_{user_id}")
