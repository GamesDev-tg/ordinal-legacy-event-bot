# 🪔 Ordinal Legacy Maha Deepotsav — Complete Event Master Specification & AI Generation Guide

> **Target Audience**: AI Language Models, Community Managers, Game Designers, and Bot Operators.  
> **Purpose**: Provides total architectural, mechanical, thematic, and technical context so any AI can reliably understand the event mechanics and generate lore-accurate, high-converting announcements, alerts, and community messages.

---

## 1. Executive Summary & Core Event Narrative

### The Lore of Maha Deepotsav
The **Ordinal Legacy Maha Deepotsav** is a grand festive celebration inspired by the Festival of Lights (Diwali). The event centers around the **Akhand Diya** (the Eternal Lamp of Cosmic Radiance). According to lore, darkness threatens the digital kingdom, and only the collective embers—**Sparks of Devotion**—gathered by the community lampbearers can kindle the Great Sacred Flame and unlock the vault of royal festive treasures.

### The Two Pillars of Participation
1. **The Individual Ascent (Personal Tiers)**: Each player gathers hard points through skill mini-games, daily blessings, and companion invitations to climb 5 milestone tiers up to **5,000 Points**.
2. **The Community Akhand Jyoti (Collective Milestones)**: Every single point earned by any player contributes 1:1 to the global pool of **200,000 Community Sparks**, which unlocks 5 sequential treasure segments (Coins, Pearls, Tickets, Pets, and Maha Grand Rewards).

---

## 2. Core Game Mechanics & Stamina Economy

### A. Diya Wicks (Stamina System)
- **Maximum Capacity**: 10 Wicks.
- **Consumption**: Every game play (whether in Telegram chat or the Web Mini-App) consumes **1 Diya Wick**.
- **Dynamic Natural Refill**: Wicks automatically regenerate **1 wick every 1 to 3 minutes** (randomized interval to deter automated macro sync and provide exciting unpredictability).
- **Hard Cap Guard**: Natural regeneration halts when the wick count reaches 10/10.

### B. Shubh Muhurat (Daily Auspicious Blessing)
- **Command**: `/shubh`
- **Cadence**: Once every calendar day (UTC reset).
- **Reward**: Instantly grants **+5 Diya Wicks** (can overflow above 10 up to 15) and **+5 Hard Points**.

### C. Mini-Games (Chat & Canvas Web App)
Players can play in chat or via the interactive Telegram Web Mini-App:
1. **Chakri Whirl (`/chakri`)**: Spin the sacred ground spinner to align the fiery sparks.
2. **Rangoli Connect (`/rangoli`)**: Trace intricate festive geometry to channel radiant blessing.
3. **Mithai Catch (`/mithai`)**: Catch celebratory sweets falling from the royal feast.
- **Reward Engine**: Each completed run earns between **1 and 3 Sparks / Hard Points** based on performance and sacred luck.

---

## 3. Milestone Progression: 5,000 Points Top Tier

Individual players ascend through 5 distinct ranks. Achieving higher ranks unlocks prestigious titles, badges, and entitlement to end-of-event prize distribution:

| Tier | Tier Name | Points Required | Unlocked Title & Rewards |
| :--- | :--- | :--- | :--- |
| **Tier 0** | *Wanderer in the Dark* | 0 – 499 Pts | Base initiation, apprentice lampbearer status. |
| **Tier 1** | *Diya Novice* | 500 – 1,499 Pts | **Festival Coins Pool** eligibility. |
| **Tier 2** | *Flame Initiate* | 1,500 – 2,749 Pts | **Festival Coins + Sacred Pearls** eligibility. |
| **Tier 3** | *Lustrous Artisan* | 2,750 – 3,999 Pts | **Coins + Pearls + Golden Lottery Tickets**. |
| **Tier 4** | *Grand Lampbearer* | 4,000 – 4,999 Pts | **Coins + Pearls + Tickets + Exclusive Diwali Pets**. |
| **Tier 5** | *Akhand Jyoti Guardian* | **5,000+ Pts** | **Full Royal Vault Access**: Maximum multiplier on all prize pools + Guardian Hall of Fame status. |

---

## 4. Community Akhand Diya: 200,000 Sparks in 5 Segments

The community target is fixed at **200,000 Sparks**. To maintain continuous engagement, the target is divided into **5 discrete 40,000-spark stages**. As the community crosses each threshold, a new reward tier becomes claimable:

```
[0 Sparks] ────────> [40,000 Sparks] ────────> [80,000 Sparks] ────────> [120,000 Sparks] ────────> [160,000 Sparks] ────────> [200,000 Sparks]
  Stage 0: Unlit       Stage 1: Coins          Stage 2: Pearls         Stage 3: Tickets         Stage 4: Pets          Stage 5: FULL IGNITION
```

1. **Stage 0 (0 – 40,000 Sparks)**: *Diya Awakening* — Lighting the initial oil wick. Unlocks **Festival Coins**.
2. **Stage 1 (40,000 – 80,000 Sparks)**: *Sacred Radiance* — Flame stabilizes. Unlocks **Sacred Pearls**.
3. **Stage 2 (80,000 – 120,000 Sparks)**: *Golden Flame Ascending* — Temple courtyard glows. Unlocks **Golden Lottery Tickets**.
4. **Stage 3 (120,000 – 160,000 Sparks)**: *Resplendent Mahotsav* — Night sky illuminated. Unlocks **Exclusive Diwali Pets**.
5. **Stage 4 & 5 (160,000 – 200,000 Sparks)**: *Maha Akhand Jyoti Full Ignition* — The Eternal Flame achieves immortality. **All 5 Reward Classes Cleared & Multipliers Activated**.

---

## 5. The Four Sacred Gharanas (Houses)

Every player is initiated into one of four noble houses upon entering (`/start`). Gharanas compete for top average score and collective glory:

1. **Surya Gharana (Sun Clan)** ☀️
   - *Motto*: "Radiant as the Morning Sun, Fearless in the Dark."
   - *Theme*: Golden light, solar energy, unwavering discipline.
2. **Chandra Gharana (Moon Clan)** 🌙
   - *Motto*: "Serene as the Autumn Moon, Guiding the Lost."
   - *Theme*: Silver luminescence, wisdom, patience, strategic play.
3. **Agni Gharana (Fire Clan)** 🔥
   - *Motto*: "Fierce as the Sacred Flame, Consuming all Shadows."
   - *Theme*: Crimson and amber embers, high passion, competitive frenzy.
4. **Vayu Gharana (Wind Clan)** 💨
   - *Motto*: "Swift as the Midnight Breeze, Spreading the Sparks."
   - *Theme*: Emerald and azure wind, speed, agility, viral growth.

---

## 6. Shagun Referral & Diya Companion System

- **Referral Link Format**: `https://t.me/OrdinalLegacyEventBot?start=ref_<USER_ID>`
- **First Invited Friend = Diya Companion**:
  - The very first user who joins via a player's link is permanently bonded as their **Diya Companion**.
  - **Companion Synergy**: Both players can exchange daily Diya Wick gifts via `/shagun` without spending their own stamina.
  - Bonding gives **+1 Hard Point** to the referrer.
- **Subsequent Referrals**:
  - Each friend who joins and verifies groups grants **+1 Hard Point** up to a maximum cap of **50 referral points**.
- **Self-Referral Guard**: Players cannot click or bind their own referral link.
- **Companion View**: Visible on `/status`, `/shagun`, and `/mydata`.

---

## 7. Anti-Macro / Anti-Bot "Sacred Jyoti Captcha"

To prevent autohotkey scripts, macro clickers, or bot farms from monopolizing the 5k top tier:
- **Automatic Trigger**: Triggers automatically after every 15 consecutive mini-game plays or via `/captcha` / `/testcaptcha`.
- **Three Challenge Varieties**:
  1. **Visual Emoji Garland**: Displays a sequence of festive icons (e.g. `🪔 🌸 🪔 🪔 🌺 🪔`) and asks how many of a specific symbol are present.
  2. **Festive Cultural Trivia**: Questions celebrating Diwali traditions that require human contextual reasoning.
  3. **Mental Math**: Randomized festive arithmetic.
- **Cryptographic Security**: HMAC-SHA256 signed tokens with a strict 3-minute expiry.
- **Game Lockdown**: If locked, API calls to `/api/game/start` return `captcha_required` until the challenge is solved.
- **Button Guard**: Only the owner (`from.id == user_id`) can tap the answer buttons.

---

## 8. Group vs DM Hygiene Protocol

To maintain a clean experience across affiliated community groups:
- **Private DM Only**: Personal data, status, stamina, referral generation, and games (`/mydata`, `/status`, `/shagun`, `/shubh`, `/play`, `/chakri`, `/rangoli`, `/mithai`) are strictly blocked in group chats.
- **Inline Redirect**: If a user runs these commands in a group, the bot responds with a single clean inline button: *"Please tap below to open our private DM."*
- **Public Group Commands**: Only communal summaries (`/top`, `/gharanas`, `/widget`, `/stats`, `/tiers`) can respond in groups, formatted cleanly without spamming.
- **Admin Panel Lockdown**: `/admin`, `/adminhelp`, and all adjustment tools are completely inaccessible in public groups.

---

## 9. Official Channel Gates & Verification
Before entering the event, every player must join the 3 official community handles:
1. **Official Information Channel**: `@OrdinalLegacyEventInfo`
2. **Main Community Chat**: `@OrdinalLegacy`
3. **Ordinal Gems**: `@ordinalgemsonbtc`

---

## 10. Complete Telegram Bot Command Reference

### Player Commands
- `/start` — Launch the festival arena, house initiation, and mini-app.
- `/mydata` — View personal dossier, exact points, stage clearance, and locked/unlocked rewards.
- `/status` — View current points, stamina wicks, flame stage, and bonded companion.
- `/play` — Choose games menu (Chat or Mini-App).
- `/chakri` — Spin the Chakri in chat (1 wick, 1-3 pts).
- `/rangoli` — Draw Rangoli in chat (1 wick, 1-3 pts).
- `/mithai` — Feast on Mithai in chat (1 wick, 1-3 pts).
- `/shubh` — Claim daily Shubh Muhurat blessing (+5 wicks & pts).
- `/shagun` — Generate referral link and exchange companion wick gifts.
- `/top` — View Top 10 Lampbearers on the live leaderboard.
- `/gharanas` — View live standings of the 4 noble houses.
- `/tiers` — View the 5,000-point milestone ladder and reward tiers.
- `/stats` — View global event metrics and total community sparks.
- `/widget` — Display the live Akhand Diya community flame widget.
- `/captcha` (or `/testcaptcha`) — Test the Sacred Jyoti anti-bot challenge.
- `/help` — Display player help menu.

### Administrative Commands (Admin ID: `1257427765`)
- `/admin` or `/adminhelp` — Open management control panel.
- `/addpoints <id> <pts>` — Credit points to a player.
- `/removepoints <id> <pts>` — Deduct points from a player.
- `/setwicks <id> <qty>` — Manually adjust a player's wick stamina.
- `/resetscores CONFIRM` — Reset all leaderboard points (preserves users).
- `/backup` — Export instant SQLite database snapshot.
- `/snapshot` — Force an automated 6-hour disaster recovery snapshot.
- `/setcaptcha <id>` — Force-lock a suspicious user into captcha verification.
- `/userinfo <id>` — Inspect complete telemetry for any player.
- `/admins` — Display list of active event administrators.

---

## 11. AI System Prompt & Message Generation Guide

When prompting an AI to write messages, announcements, or bot dialogues for this event, provide the following instruction block:

### System Prompt for AI Copywriter
```markdown
You are the "Grand Lampbearer of Ordinal Legacy", the sacred voice and herald of the Ordinal Legacy Maha Deepotsav.
Tone: Festive, epic, warm, encouraging, culturally resonant, and urgent.
Visual Theme: Diya lamps (🪔), sacred flames (🔥), sparks (✨), lotus flowers (🌸), royal sweet feasts (🍬), and auspicious bells (🔔).

Core Rules:
1. Always reference the dual objectives:
   - Personal goal: Reach 5,000 Points to unlock Tier 5 (Akhand Jyoti Guardian).
   - Community goal: Reach 200,000 Sparks to ignite the Maha Akhand Diya across 5 unlock segments (Coins, Pearls, Tickets, Pets, Royal Vault).
2. Highlight Diya Wicks as stamina: Natural refill occurs every 1 to 3 minutes, plus daily /shubh gives +5 wicks & +5 points.
3. Highlight the Shagun Companion feature: The 1st invited friend bonds as a companion for daily mutual stamina gifts.
4. Formatting: When writing in Telegram Markdown, always escape underscores in usernames (e.g. @player\_name) to prevent formatting errors.
```

---

## 12. Pre-Built AI Message Templates

### Template A: Daily Shubh Muhurat Call-to-Action
> 🪔 **The Auspicious Shubh Muhurat Has Dawned!** 🪔  
> 
> Noble Lampbearers of the Four Gharanas, the celestial alignment brings fresh blessings to our festival grounds!  
> 
> ✨ **Claim your Daily Boon**: Type `/shubh` in private chat with @OrdinalLegacyEventBot right now to claim:  
> • **+5 Free Diya Wicks** (Stamina boost)  
> • **+5 Sacred Sparks** to your milestone score  
> 
> Remember: Your wicks also regenerate **1 wick every 1 to 3 minutes**! Don't let your stamina sit at 10/10—spin your `/chakri`, design your `/rangoli`, and collect your `/mithai`!  
> 
> 🏆 *Target*: 5,000 Points unlocks the ultimate **Akhand Jyoti Guardian** vault!  
> 👉 Tap here to play: [@OrdinalLegacyEventBot](https://t.me/OrdinalLegacyEventBot)

---

### Template B: Community Segment Milestone Clearance Alert
> 🌟 **SACRED FLAME UNLOCKED: STAGE [X] CLEARED!** 🌟  
> 
> Together, the Four Noble Gharanas have gathered **[CURRENT_SPARKS] / 200,000 Sparks**!  
> 
> The Akhand Diya blazes brighter, melting the seal of **Stage [X]**:  
> 🎁 **[REWARD_NAME] Unlocked for all eligible players!**  
> 
> • *Stage 1 (40k)*: Festival Coins Pool 🟡  
> • *Stage 2 (80k)*: Sacred Pearls Pool ⚪  
> • *Stage 3 (120k)*: Golden Lottery Tickets 🎫  
> • *Stage 4 (160k)*: Royal Diwali Pets 🐾  
> • *Stage 5 (200k)*: Maha Akhand Jyoti Full Vault 👑  
> 
> Check your individual tier eligibility with `/mydata` and keep spinning!  
> 🪔 Play now: [@OrdinalLegacyEventBot](https://t.me/OrdinalLegacyEventBot)

---

### Template C: Companion & Referral Drive (Shagun System)
> 🤝 **Never Walk the Festival Grounds Alone! Bond with a Diya Companion!**  
> 
> In the ancient tradition of Diwali, prosperity doubles when shared!  
> 
> 🪔 **How the Shagun Companion Works**:  
> 1. Type `/shagun` in [@OrdinalLegacyEventBot](https://t.me/OrdinalLegacyEventBot) to get your sacred invite link.  
> 2. Share it with a friend. The very **first friend** who joins becomes your permanent **Diya Companion**!  
> 3. Both of you can send each other **free daily Diya Wicks** to keep your flames burning all day long!  
> 4. Earn **+1 Hard Point** per friend invited (up to 50 points)!  
> 
> Find your companion today and race together to the 5,000 Points Top Tier! 🚀
