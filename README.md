# Ordinal Legacy Event Bot — Diwali Maha Deepotsav

Production-grade Telegram Mini App (TWA) and Bot for the **Maha Deepotsav: Awakening the 200,000 Sparks of Akhand Jyoti** festive campaign.

## 🪔 Core Architecture & Game Design

* **Strict 1–3 Point Scoring**: Every mini-game awards strictly 1, 2, or 3 points based on skill and precision. No 3x tables, no inflated multipliers.
* **1 Official Companion Rule**: Players can invite multiple friends, but designate **strictly 1 as their official Diya Companion** for mutual tier notifications and daily free Energy Wick exchanges.
* **Additional Friends (+1 Pt Each)**: Extra invited friends who join and play award **+1 point each** (minimum points), capped at 15 points total to prevent referral farming.
* **200,000 Points Global Community Milestone**: Progressive stages from 25k to 200k+ sparks so any cohort size feels victory.
* **Anti-Cheat Engine**: Cryptographic HMAC-SHA256 Telegram `initData` verification, single-use session nonces, and duration checks (<12s rejected).
* **4 Auspicious Gharanas**: Surya, Agni, Chandra, and Vayu competing on average score per player.

---

## 🎮 3 Festive Mini-Games (HTML5 Canvas)

1. **Chakri Whirl & Rocket Blast (Precision Timing)**: 360° rotating dial. Golden Deepak Zone (12%) awards 3 pts, Silver Halo awards 2 pts, Outer zone awards 1 pt. Heavy Telegram haptic kick on launch.
2. **Rangoli Color Symphony (Memory Sequence)**: Symmetrical lotus rangoli flashing sacred ritual colors (Kumkum Red, Haldi Gold, Peacock Blue, Marigold Orange) with Web Audio notes.
3. **Mithai Drop Catcher (Reflex / Catch)**: 20-second session dragging an ornate brass thali to catch falling sweets (+1) while avoiding falling soot embers (-1).

---

## 🚀 Quick Start Guide

### 1. Local Setup
```bash
# Clone or unzip repository
cd ordinal_legacy_event_bot

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Initialize database and seed sample players
python3 scripts/seed_data.py

# Launch development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open `http://localhost:8000` in your browser to view the playable Telegram Mini App!

### 2. Docker Deployment
```bash
docker-compose up --build -d
```

### 3. Telegram Bot Setup
1. Open [@BotFather](https://t.me/BotFather) on Telegram and create a bot (`/newbot`).
2. Set `/setmenubutton` pointing to your deployed Mini App URL.
3. Set your webhook:
   ```bash
   curl -F "url=https://your-domain.com/webhook" https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook
   ```

---

## 🛠️ Admin Management & Reward Auditing

### Telegram Bot Commands
* `/start`: Launch festival arena, Mini App, and claim referral invites.
* `/status`: Check community sparks, flame stage, Diya Wicks, and bonded companion.
* `/house` / `/mygharana`: View your Gharana house motto, ranking, members, and avg points.
* `/top` / `/topusers`: Global Top 10 Lampbearers leaderboard.
* `/shagun`: Generate your personal Shagun invite link.
* `/shubh`: Claim your daily Shubh Muhurat refill (+5 Diya Wicks).
* `/widget` / `/akhand`: Generate the real-time pinned channel Akhand Diya widget message.
* `/gharanas` / `/leaderboard`: View live house rankings and average points.
* `/tiers`: View individual milestone reward tiers.
* `/findtier <0-5>`: Find and list all players in a specific reward tier.
* `/user <id/@username>`: Inspect detailed player profile (points, companion, games, wicks).
* `/stats`: Deep global event metrics (game breakdowns, companion pairs, sparks progress).

### Admin Commands (Restricted to ADMIN_TELEGRAM_IDS)
* `/query SELECT ...`: Execute read queries directly against the database with preview.
* `/query UPDATE ...`: Execute secure database updates and receive rows affected count.
* `/add <user_id> <points>`: Manually credit or deduct points for a user.
* `/resetwicks <user_id>`: Instantly restore full stamina (10 Diya Wicks) for a user.

### Admin REST API Endpoints
* `POST /api/admin/query`: Execute arbitrary SELECT or UPDATE queries (`{admin_telegram_id, query}`).
* `GET /api/admin/users_by_tier?admin_id=...&tier_level=...`: Retrieve all users in a specific tier.
* `POST /api/admin/reset_wicks`: Restore a user's stamina to 10 wicks.
* `GET /api/admin/stats?admin_id=...`: Fetch complete event analytics and score breakdown.
* `GET /api/admin/export_rewards_csv?admin_id=...`: Download full rewards distribution CSV.

---

## 🧪 Running Automated Tests
```bash
pytest
```
All 28 comprehensive tests verify anti-cheat token validation, replay prevention, speed-run defense, referral limits, stamina refills, admin query engine, tier user finders, and reward exports.
