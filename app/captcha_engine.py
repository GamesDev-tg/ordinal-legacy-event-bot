import random
import time
import uuid
from typing import Dict, Any, Optional, Tuple

# In-memory storage for active captcha challenges and user attempt tracking
_ACTIVE_CAPTCHAS: Dict[int, Dict[str, Any]] = {}
_USER_GAME_COUNTS: Dict[int, int] = {}
_USER_CAPTCHA_LOCKED: Dict[int, bool] = {}

# Rich pool of festive, human-intuitive cultural and visual riddles that automated scripts cannot parse
CAPTCHA_QUESTIONS = [
    {
        "question": "🪔 Sacred Jyoti Check: Which round golden sweet made of besan is traditionally offered to Lord Ganesha during Diwali?",
        "options": ["🍬 Motichoor Laddu", "🌙 Crescent Moon", "🪔 Clay Diya", "💨 Sacred Wind"],
        "answer": "🍬 Motichoor Laddu"
    },
    {
        "question": "🪔 Sacred Jyoti Check: Which grand Festival of Lights celebrates the joyful return of Shri Ram to Ayodhya?",
        "options": ["🪔 Maha Deepotsav (Diwali)", "🌈 Holi", "🪁 Makar Sankranti", "🎋 Pongal"],
        "answer": "🪔 Maha Deepotsav (Diwali)"
    },
    {
        "question": "🪔 Sacred Jyoti Check: What pure clarified butter or holy oil is poured to light traditional Diwali Diyas?",
        "options": ["🧈 Pure Cow Ghee / Sesame Oil", "🚗 Engine Gasoline", "🧊 Cold Ice Water", "🪨 Crushed Stone"],
        "answer": "🧈 Pure Cow Ghee / Sesame Oil"
    },
    {
        "question": "🪔 Sacred Jyoti Check: What colorful sacred artwork is hand-drawn at home entrances using bright powders and flower petals?",
        "options": ["🎨 Rangoli Pattern", "💻 Laptop Screen", "🚗 Motor Vehicle", "📱 Smartphone"],
        "answer": "🎨 Rangoli Pattern"
    },
    {
        "question": "🪔 Sacred Jyoti Check: Which divine Goddess of wealth and prosperity is worshipped along with Lord Ganesha on Diwali evening?",
        "options": ["🪔 Goddess Lakshmi", "❄️ Snow Queen", "⚡ Thunder Spirit", "🌊 Sea Siren"],
        "answer": "🪔 Goddess Lakshmi"
    },
    {
        "question": "🪔 Sacred Jyoti Check: What sacred cotton thread is placed inside the clay lamp to hold the holy flame?",
        "options": ["🧵 Cotton Diya Wick (Baati)", "🔌 Copper Wire", "🪵 Bamboo Stick", "🔩 Iron Screw"],
        "answer": "🧵 Cotton Diya Wick (Baati)"
    },
    {
        "question": "🪔 Sacred Jyoti Check: What auspicious gift is exchanged between loved ones and Diya Companions during Diwali?",
        "options": ["🎁 Shagun & Sweets", "🪨 Gray Rocks", "🗑️ Discarded Scrap", "🍂 Dry Weeds"],
        "answer": "🎁 Shagun & Sweets"
    }
]

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
    
    question = f"🪔 *Sacred Jyoti Verification*\nCount the exact number of 🪔 Diyas in this festive garland:\n\n`{garland}`"
    
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
        "question": f"🪔 *Sacred Jyoti Verification*\n{item['question']}",
        "options": options,
        "correct_index": correct_idx
    }

def generate_math_challenge() -> dict:
    a = random.randint(2, 5)
    b = random.randint(2, 5)
    total = a + b
    question = f"🪔 *Sacred Jyoti Verification*\nIf {a} sacred lamps are placed at the doorway and {b} lamps at the courtyard, how many lamps illuminate the home?"
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
    """
    now = time.time()
    existing = _ACTIVE_CAPTCHAS.get(user_id)
    if existing and existing.get("expires_at", 0) > now:
        return existing

    choice = random.choice(["visual", "culture", "math"])
    if choice == "visual":
        challenge = generate_visual_emoji_challenge()
    elif choice == "culture":
        challenge = generate_cultural_challenge()
    else:
        challenge = generate_math_challenge()
        
    token = uuid.uuid4().hex[:12]
    record = {
        "user_id": user_id,
        "token": token,
        "question": challenge["question"],
        "options": challenge["options"],
        "correct_index": challenge["correct_index"],
        "created_at": now,
        "expires_at": now + 180  # 3 minutes
    }
    _ACTIVE_CAPTCHAS[user_id] = record
    return record

def verify_captcha_answer(user_id: int, answer_index: int, token: Optional[str] = None) -> Tuple[bool, str]:
    now = time.time()
    challenge = _ACTIVE_CAPTCHAS.get(user_id)
    if not challenge:
        return False, "No active verification found. Please request a new check."
    
    if challenge.get("expires_at", 0) < now:
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        return False, "⏳ Verification timed out! Please try the fresh sacred check."
        
    if token and challenge.get("token") != token:
        return False, "Invalid verification token. Please try again."
        
    if answer_index == challenge.get("correct_index"):
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        _USER_CAPTCHA_LOCKED[user_id] = False
        _USER_GAME_COUNTS[user_id] = 0
        return True, "✨ Sacred Jyoti Verification Passed! Human presence confirmed."
    else:
        # Generate new question on failure to prevent brute forcing the same question
        _ACTIVE_CAPTCHAS.pop(user_id, None)
        return False, "❌ Incorrect answer! A fresh challenge has been issued to verify your presence."

def record_game_play_and_check_captcha(user_id: int) -> bool:
    """
    Called whenever a game starts/finishes.
    Triggers an anti-macro captcha every 12 to 18 games automatically.
    Returns True if captcha is now required.
    """
    count = _USER_GAME_COUNTS.get(user_id, 0) + 1
    _USER_GAME_COUNTS[user_id] = count
    
    # Trigger captcha every 15 games
    if count >= 15:
        _USER_CAPTCHA_LOCKED[user_id] = True
        return True
    return False

def is_user_captcha_locked(user_id: int) -> bool:
    return _USER_CAPTCHA_LOCKED.get(user_id, False)

def lock_user_captcha(user_id: int):
    _USER_CAPTCHA_LOCKED[user_id] = True

def unlock_user_captcha(user_id: int):
    _USER_CAPTCHA_LOCKED[user_id] = False
    _USER_GAME_COUNTS[user_id] = 0
    _ACTIVE_CAPTCHAS.pop(user_id, None)
