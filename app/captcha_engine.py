import random
import time
import uuid
import hmac
import hashlib
import json
import secrets
from typing import Dict, Any, Optional, Tuple
from app.config import settings

# In-memory storage for active captcha challenges and user attempt tracking
_ACTIVE_CAPTCHAS: Dict[int, Dict[str, Any]] = {}
_USER_GAME_COUNTS: Dict[int, int] = {}
_USER_CAPTCHA_LOCKED: Dict[int, bool] = {}

# Rich pool of festive, human-intuitive cultural and visual riddles that automated scripts cannot parse
CAPTCHA_QUESTIONS = [
    {
        "question": "Which round golden sweet made of besan is traditionally offered to Lord Ganesha during Diwali?",
        "options": ["🍬 Motichoor Laddu", "🌙 Crescent Moon", "🪔 Clay Diya", "💨 Sacred Wind"],
        "answer": "🍬 Motichoor Laddu"
    },
    {
        "question": "Which grand Festival of Lights celebrates the joyful return of Shri Ram to Ayodhya?",
        "options": ["🪔 Maha Deepotsav (Diwali)", "🌈 Holi", "🪁 Makar Sankranti", "🎋 Pongal"],
        "answer": "🪔 Maha Deepotsav (Diwali)"
    },
    {
        "question": "What pure clarified butter or holy oil is poured to light traditional Diwali Diyas?",
        "options": ["🧈 Pure Cow Ghee / Sesame Oil", "🚗 Engine Gasoline", "🧊 Cold Ice Water", "🪨 Crushed Stone"],
        "answer": "🧈 Pure Cow Ghee / Sesame Oil"
    },
    {
        "question": "What colorful sacred artwork is hand-drawn at home entrances using bright powders and flower petals?",
        "options": ["🎨 Rangoli Pattern", "💻 Laptop Screen", "🚗 Motor Vehicle", "📱 Smartphone"],
        "answer": "🎨 Rangoli Pattern"
    },
    {
        "question": "Which divine Goddess of wealth and prosperity is worshipped along with Lord Ganesha on Diwali evening?",
        "options": ["🪔 Goddess Lakshmi", "❄️ Snow Queen", "⚡ Thunder Spirit", "🌊 Sea Siren"],
        "answer": "🪔 Goddess Lakshmi"
    },
    {
        "question": "What sacred cotton thread is placed inside the clay lamp to hold the holy flame?",
        "options": ["🧵 Cotton Diya Wick (Baati)", "🔌 Copper Wire", "🪵 Bamboo Stick", "🔩 Iron Screw"],
        "answer": "🧵 Cotton Diya Wick (Baati)"
    },
    {
        "question": "What auspicious gift is exchanged between loved ones and Diya Companions during Diwali?",
        "options": ["🎁 Shagun & Sweets", "🪨 Gray Rocks", "🗑️ Discarded Scrap", "🍂 Dry Weeds"],
        "answer": "🎁 Shagun & Sweets"
    }
]

def _get_signing_key() -> str:
    return getattr(settings, "BOT_TOKEN", "sacred_diwali_key") or "sacred_diwali_key"

def _generate_signed_captcha_token(user_id: int, correct_idx: int, exp: int) -> Tuple[str, str]:
    """
    Returns (short_token, signed_token)
    short_token: 12-char hex string (used for Telegram inline keyboard callback data < 64 bytes)
    signed_token: full HMAC-signed token for web/API stateless validation across multi-workers
    """
    salt = secrets.token_hex(4)
    payload = f"{user_id}_{correct_idx}_{exp}_{salt}"
    sig = hmac.new(_get_signing_key().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    signed_token = f"{payload}_{sig}"
    short_token = f"{salt}{sig[:8]}"
    return short_token, signed_token

def generate_visual_emoji_challenge() -> dict:
    """
    Generates a dynamic randomized garland of festive emojis where the human must count
    the exact number of target symbols.
    """
    target_count = random.randint(2, 5)
    distractor_count = random.randint(3, 5)
    
    target_emoji = "🪔"
    distractors = ["🌸", "✨", "🌺", "🌼", "🍬"]
    
    items = [target_emoji] * target_count + [random.choice(distractors) for _ in range(distractor_count)]
    random.shuffle(items)
    garland = " ".join(items)
    
    # Clearly state to count only the Diyas inside the box, so players never count emojis in the question text!
    question = f"✨ *Sacred Jyoti Verification*\nCount only the 🪔 Diyas (oil lamps) inside the box below:\n\n`{garland}`"
    
    correct_ans = f"{target_count} Diyas"
    other_counts = [c for c in range(1, 7) if c != target_count]
    distractor_answers = [f"{c} Diyas" for c in random.sample(other_counts, 3)]
    
    options = distractor_answers + [correct_ans]
    random.shuffle(options)
    correct_idx = options.index(correct_ans)
    
    return {
        "question": question,
        "options": options,
        "correct_index": correct_idx
    }

def generate_cultural_challenge() -> dict:
    item = random.choice(CAPTCHA_QUESTIONS)
    correct_ans = item["answer"]
    options = list(item["options"])
    random.shuffle(options)
    correct_idx = options.index(correct_ans)
    return {
        "question": f"✨ *Sacred Jyoti Verification*\n{item['question']}",
        "options": options,
        "correct_index": correct_idx
    }

def generate_math_challenge() -> dict:
    a = random.randint(2, 5)
    b = random.randint(2, 5)
    total = a + b
    question = f"✨ *Sacred Jyoti Verification*\nIf {a} sacred lamps are placed at the doorway and {b} lamps at the courtyard, how many lamps illuminate the home?"
    correct_ans = f"{total} Lamps"
    other_numbers = [n for n in range(max(1, total - 3), total + 4) if n != total and n > 0]
    distractor_answers = [f"{n} Lamps" for n in random.sample(other_numbers, 3)]
    options = distractor_answers + [correct_ans]
    random.shuffle(options)
    correct_idx = options.index(correct_ans)
    return {
        "question": question,
        "options": options,
        "correct_index": correct_idx
    }

def get_or_create_captcha(user_id: int) -> dict:
    """
    Returns existing active challenge if valid, or generates a new randomized challenge.
    Persists to system_settings so multi-worker and serverless instances share active challenges.
    """
    now = time.time()
    existing = _ACTIVE_CAPTCHAS.get(user_id)
    if not existing:
        try:
            from app.database import get_system_setting
            raw = get_system_setting(f"active_captcha_{user_id}", "")
            if raw:
                data = json.loads(raw)
                if data.get("expires_at", 0) > now:
                    existing = data
                    _ACTIVE_CAPTCHAS[user_id] = existing
        except Exception:
            pass

    if existing and existing.get("expires_at", 0) > now:
        return existing

    choice = random.choice(["visual", "culture", "math"])
    if choice == "visual":
        challenge = generate_visual_emoji_challenge()
    elif choice == "culture":
        challenge = generate_cultural_challenge()
    else:
        challenge = generate_math_challenge()
        
    exp = int(now) + 300  # 5 minutes for generous human reaction time
    short_token, signed_token = _generate_signed_captcha_token(user_id, challenge["correct_index"], exp)
    
    record = {
        "user_id": user_id,
        "token": signed_token,
        "short_token": short_token,
        "question": challenge["question"],
        "options": challenge["options"],
        "correct_index": challenge["correct_index"],
        "created_at": now,
        "expires_at": exp
    }
    _ACTIVE_CAPTCHAS[user_id] = record
    
    try:
        from app.database import set_system_setting
        set_system_setting(f"active_captcha_{user_id}", json.dumps(record))
    except Exception:
        pass

    return record

def verify_captcha_answer(user_id: int, answer_index: int, token: Optional[str] = None, answer_text: Optional[str] = None) -> Tuple[bool, str]:
    now = time.time()
    
    # 1. Fetch challenge from memory or system_settings persistence
    challenge = _ACTIVE_CAPTCHAS.get(user_id)
    if not challenge:
        try:
            from app.database import get_system_setting
            raw = get_system_setting(f"active_captcha_{user_id}", "")
            if raw:
                challenge = json.loads(raw)
                _ACTIVE_CAPTCHAS[user_id] = challenge
        except Exception:
            challenge = None

    # 2. Check stateless HMAC-signed token
    is_hmac_valid = False
    hmac_correct_idx = None
    if token:
        delim = "_" if "_" in token else (":" if ":" in token else None)
        if delim:
            parts = token.split(delim)
            if len(parts) == 5:
                tok_uid, tok_idx, tok_exp, tok_salt, tok_sig = parts
                try:
                    if int(tok_uid) == int(user_id) and float(tok_exp) > now:
                        payload = delim.join([tok_uid, tok_idx, tok_exp, tok_salt])
                        expected_sig = hmac.new(_get_signing_key().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
                        if hmac.compare_digest(tok_sig, expected_sig):
                            is_hmac_valid = True
                            hmac_correct_idx = int(tok_idx)
                except Exception:
                    pass

    if not challenge and not is_hmac_valid:
        return False, "No active verification found. Please request a new check."
    
    # 3. Check expiration
    if challenge and challenge.get("expires_at", 0) < now and not is_hmac_valid:
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        try:
            from app.database import set_system_setting
            set_system_setting(f"active_captcha_{user_id}", "")
        except Exception:
            pass
        return False, "⏳ Verification timed out! Please try the fresh sacred check."
        
    # 4. Token validation (allow match against full signed token, short token, or HMAC validity)
    if token and challenge:
        c_tok = challenge.get("token")
        c_short = challenge.get("short_token")
        if token != c_tok and token != c_short and not is_hmac_valid:
            return False, "Invalid verification token. Please try again."

    # 5. Determine expected index
    expected_idx = hmac_correct_idx if is_hmac_valid else challenge.get("correct_index")
    
    # 6. Check answer match by index OR option text string
    is_correct = False
    if answer_index == expected_idx:
        is_correct = True
    elif challenge and answer_text and isinstance(challenge.get("options"), list):
        try:
            target_text = challenge["options"][expected_idx]
            if str(answer_text).strip() == str(target_text).strip():
                is_correct = True
        except (IndexError, TypeError):
            pass

    if is_correct:
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        _USER_CAPTCHA_LOCKED[user_id] = False
        _USER_GAME_COUNTS[user_id] = 0
        try:
            from app.database import set_system_setting
            set_system_setting(f"captcha_locked_{user_id}", "0")
            set_system_setting(f"active_captcha_{user_id}", "")
        except Exception:
            pass
        return True, "✨ Sacred Jyoti Verification Passed! Human presence confirmed."
    else:
        # Generate new question on failure to prevent brute forcing the same question
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        try:
            from app.database import set_system_setting
            set_system_setting(f"active_captcha_{user_id}", "")
        except Exception:
            pass
        return False, "❌ Incorrect answer! A fresh challenge has been issued to verify your presence."

def record_game_play_and_check_captcha(user_id: int) -> bool:
    """
    Called whenever a game starts/finishes.
    Triggers an anti-macro captcha every 15 games automatically.
    Returns True if captcha is now required.
    """
    count = _USER_GAME_COUNTS.get(user_id, 0) + 1
    _USER_GAME_COUNTS[user_id] = count
    
    # Trigger captcha every 15 games
    if count >= 15:
        lock_user_captcha(user_id)
        return True
    return False

def is_user_captcha_locked(user_id: int) -> bool:
    if _USER_CAPTCHA_LOCKED.get(user_id, False):
        return True
    try:
        from app.database import get_system_setting
        val = get_system_setting(f"captcha_locked_{user_id}", "0")
        if val in ("1", "true", "yes"):
            _USER_CAPTCHA_LOCKED[user_id] = True
            return True
    except Exception:
        pass
    return False

def lock_user_captcha(user_id: int):
    _USER_CAPTCHA_LOCKED[user_id] = True
    try:
        from app.database import set_system_setting
        set_system_setting(f"captcha_locked_{user_id}", "1")
    except Exception:
        pass

def unlock_user_captcha(user_id: int):
    _USER_CAPTCHA_LOCKED[user_id] = False
    _USER_GAME_COUNTS[user_id] = 0
    _ACTIVE_CAPTCHAS.pop(user_id, None)
    try:
        from app.database import set_system_setting
        set_system_setting(f"captcha_locked_{user_id}", "0")
        set_system_setting(f"active_captcha_{user_id}", "")
    except Exception:
        pass

def unlock_all_users_captcha() -> int:
    unlocked_count = len([uid for uid, locked in _USER_CAPTCHA_LOCKED.items() if locked])
    _USER_CAPTCHA_LOCKED.clear()
    _USER_GAME_COUNTS.clear()
    _ACTIVE_CAPTCHAS.clear()
    try:
        from app.database import get_db_connection
        conn = get_db_connection()
        with conn:
            conn.execute("DELETE FROM system_settings WHERE key LIKE 'captcha_locked_%' OR key LIKE 'active_captcha_%'")
        conn.close()
    except Exception:
        pass
    return max(unlocked_count, 1)
