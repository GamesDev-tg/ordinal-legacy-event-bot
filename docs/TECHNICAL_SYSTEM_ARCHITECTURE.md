# 🛠️ Ordinal Legacy Event Bot — Technical System Architecture & AI Developer Runbook

> **Target Audience**: AI Coding Assistants (Antigravity, Cursor, Claude, ChatGPT), Systems Engineers, and Bot Maintainers.  
> **Purpose**: Provides complete technical architecture, database schemas, directory structures, API route maps, testing instructions, and disaster recovery protocols. If any bug or error occurs, any AI can read this document to diagnose, locate the exact file, and fix it safely.

---

## 1. Project Directory Structure & Key Files

```
ordinal_legacy_event_bot/
├── app/
│   ├── __init__.py
│   ├── config.py             # Pydantic settings, tier thresholds, group names, env vars
│   ├── database.py           # SQLite connection, WAL mode, schema migrations, stage math
│   ├── bot.py                # Telegram webhook dispatcher, escape_md, command handlers
│   ├── cache.py              # In-memory TTL cache (get_cache, set_cache) for high concurrency
│   ├── captcha_engine.py     # Anti-macro challenge generation, token signing & verification
│   ├── referral_engine.py    # Shagun companion bonding, point allocation, wick gifting
│   ├── models.py             # Pydantic models for REST API requests & responses
│   ├── main.py               # FastAPI entrypoint, lifecycle hooks, route inclusions
│   └── routes/
│       ├── admin_routes.py   # Admin management endpoints, points adjustments, backups
│       ├── auth_routes.py    # Telegram initData HMAC validation & demo login
│       ├── community_routes.py # Live Akhand Diya community sparks state endpoint
│       └── game_routes.py    # Game start, finish, stamina consumption, captcha gate
├── static/
│   ├── index.html            # Web Mini-App frontend UI (Canvas games & tier ladder)
│   ├── css/style.css         # Festive gold/maroon dark-mode theme styling
│   └── js/app.js             # Mini-App game loops (Chakri, Rangoli, Mithai) & captcha modal
├── tests/
│   ├── test_admin.py         # Admin authentication, point edits, and security tests
│   ├── test_bot_and_api.py   # Core bot commands, mini-game REST APIs, and Shubh refill
│   ├── test_cache.py         # In-memory cache hit, miss, and expiry TTL tests
│   ├── test_captcha.py       # Captcha generation, token validation, and lock checks
│   ├── test_full_simulation.py # E2E simulation (exotic names, referrals, group hygiene)
│   ├── test_game_engine.py   # Stamina deduction and scoring boundary tests
│   └── test_referral_engine.py # Referral anti-self checks, limits, and companion bonding
├── vercel.json               # Serverless deployment configuration for Vercel
├── requirements.txt          # Python dependencies (fastapi, uvicorn, pydantic, httpx, etc.)
└── docs/
    ├── EVENT_LORE_AND_AI_GUIDE.md        # Event lore, tiers, and AI copy generation
    └── TECHNICAL_SYSTEM_ARCHITECTURE.md   # This technical developer manual
```

---

## 2. Complete Database Schema (SQLite in WAL Mode)

Database connection helper: `app/database.py` (`get_db_connection`). Automatically enables `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` to handle 500+ concurrent readers and writers without database locking errors.

### Tables Overview:
1. `users`:
   - `telegram_id` (INTEGER PRIMARY KEY)
   - `username` (TEXT)
   - `first_name` (TEXT)
   - `points_total` (INTEGER DEFAULT 0)
   - `tier_level` (INTEGER DEFAULT 0) — Calculated from `app/config.py:TIER_THRESHOLDS`
   - `diya_wicks` (INTEGER DEFAULT 10) — Stamina points (0 to 10)
   - `gharana_id` (INTEGER) — House affiliation (0=Surya, 1=Chandra, 2=Agni, 3=Vayu)
   - `joined_groups` (INTEGER DEFAULT 0) — 1 if verified across official groups, 0 if gated
   - `shubh_refill_date` (TEXT) — YYYY-MM-DD string tracking daily `/shubh` claim
   - `last_wick_refill` (REAL) — Unix timestamp tracking natural stamina regeneration
   - `referral_points_earned` (INTEGER DEFAULT 0) — Hard cap at 50 points
   - `companion_id` (INTEGER) — Telegram ID of permanently bonded 1st referral
   - `captcha_locked` (INTEGER DEFAULT 0) — 1 if user must solve captcha before playing
   - `captcha_games_played` (INTEGER DEFAULT 0) — Consecutive games counter (resets after captcha)
   - `consecutive_wins` (INTEGER DEFAULT 0)
   - `is_banned` (INTEGER DEFAULT 0)
   - `created_at` (TIMESTAMP)

2. `community_progress`:
   - `id` (INTEGER PRIMARY KEY)
   - `total_sparks` (INTEGER DEFAULT 0) — Sum of all sparks gathered community-wide
   - `current_stage` (INTEGER DEFAULT 0) — 0 to 5 based on 40,000 sparks per segment

3. `game_logs`:
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `telegram_id` (INTEGER), `game_type` (TEXT), `points_awarded` (INTEGER), `score` (INTEGER), `created_at` (TIMESTAMP)

4. `referrals`:
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
   - `referrer_id` (INTEGER), `referred_id` (INTEGER UNIQUE), `points_awarded` (INTEGER), `created_at` (TIMESTAMP)

5. `captcha_challenges`:
   - `user_id` (INTEGER PRIMARY KEY), `token` (TEXT), `answer_index` (INTEGER), `created_at` (REAL)

6. `admins`:
   - `telegram_id` (INTEGER PRIMARY KEY), `added_by` (INTEGER), `role` (TEXT), `created_at` (TIMESTAMP)

7. `wick_gifts`:
   - `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `sender_id` (INTEGER), `receiver_id` (INTEGER), `gift_date` (TEXT)

---

## 3. High-Concurrency Performance Architecture

1. **In-Memory TTL Caching (`app/cache.py`)**:
   - Heavy aggregated queries (`/top`, `/gharanas`, `/stats`, `/widget`) are wrapped with `get_cache(key)` and `set_cache(key, value, ttl_seconds=10)`.
   - Prevents database thrashing during viral traffic surges (500+ simultaneous requests).
2. **Randomized Natural Stamina Regeneration**:
   - In `app/database.py`, wicks replenish at a randomized interval between 60 and 180 seconds (1–3 minutes), calculated lazily upon user state access:
     $$\Delta t = \text{now} - \text{last\_wick\_refill}$$
   - This eliminates background daemon loops and handles arbitrary sleep/idle periods cleanly.

---

## 4. Security, Anti-Hacking & Anti-Bot Safeguards

1. **Sacred Jyoti Captcha (`app/captcha_engine.py`)**:
   - Triggered automatically after 15 fast games (`captcha_games_played >= 15`).
   - Tokens signed with `HMAC-SHA256(secret=BOT_TOKEN, data=f"{user_id}:{timestamp}:{rand}")`.
   - Answers are checked by index. Token expires in 180 seconds.
   - Callback query guard: only `user_id` can interact with their generated challenge buttons.
2. **Universal Markdown Entity Escaping (`app/bot.py:escape_md`)**:
   - All dynamic strings (`first_name`, `username`, companion names) pass through `escape_md()`.
   - Escapes `\`, `*`, `_`, `` ` ``, `[`. Prevents Telegram API `HTTP 400: can't parse entities` crashes.
3. **Admin Privilege Guard**:
   - Every admin command verifies `is_admin(user_id)`. Non-admins receive an unauthorized warning, and a security alert is forwarded to `BOT_LOGS_CHAT_ID`.
4. **Group Spam Prevention**:
   - Personal commands invoked in groups are intercepted; the bot outputs only a private DM redirect button.

---

## 5. Troubleshooting & Bug-Fixing Playbook for Any AI

If an error or issue is reported, follow these exact diagnostic paths:

### Issue A: "Telegram message failed: can't parse entities" (HTTP 400)
- **Cause**: A username or message string contains an unescaped underscore (`_`), asterisk (`*`), or bracket (`[`).
- **Fix**: Open `app/bot.py`, locate the message builder, and wrap the variable in `escape_md(variable)`.

### Issue B: "Bot is slow or timing out under load"
- **Cause**: High concurrency hitting uncached database endpoints repeatedly.
- **Fix**: Open `app/cache.py`. Ensure the requested endpoint caches its serialized response using `get_cache(key)` and `set_cache(key, data, ttl_seconds=10)`. Verify SQLite connection in `app/database.py` has `PRAGMA busy_timeout=5000`.

### Issue C: "User cannot play or start mini-games"
- **Cause 1**: User is locked by captcha (`users.captcha_locked == 1`).
  - **Resolution**: Prompt user to run `/captcha` or admin can run `/addpoints` or unlock via database `UPDATE users SET captcha_locked = 0`.
- **Cause 2**: User has 0 wicks.
  - **Resolution**: Wait 1–3 minutes for natural refill or run `/shubh` for daily +5 wicks.
- **Cause 3**: User has not joined official groups (`joined_groups == 0`).
  - **Resolution**: Player must join the 3 groups or admin can verify via `/bypassverify <id>`.

### Issue D: "Referral not registering or companion not binding"
- **Cause**: Self-referral attempt, or user already existed in database before clicking the referral link.
- **Rule**: `referral_engine.py` only binds users who are strictly new (`created_at` matches current event start) and where `referrer_id != referred_id`.

---

## 6. How to Run Automated Verification & Regression Tests

To run the complete test suite:
```bash
python -m unittest discover -s tests
```
Expected output:
```
Ran 59 tests in ~17s
OK
```

All 59 unit, integration, and simulation tests must pass before deploying any code modification.
