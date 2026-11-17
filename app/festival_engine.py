import datetime
import html
from typing import Optional, Dict, Any, Tuple
from app.config import settings
from app.database import get_system_setting, set_system_setting, get_db_connection
from app.cache import get_cache, set_cache, delete_cache

FESTIVAL_THEMES = {
    "arcade": {
        "id": "arcade",
        "name": "Ordinal Legacy Arcade Arena",
        "short_name": "Arcade Arena",
        "icon": "🕹️",
        "tagline": "Battle in PvP & PvAI Mini-Games, earn Arcade Sparks, and climb the Leaderboard!",
        "currency_name": "Arcade Sparks",
        "currency_icon": "⚡",
        "status_beacon": "Arcade Power Core",
        "description": "Year-round competitive and casual gaming season between major festivals."
    },
    "diwali": {
        "id": "diwali",
        "name": "Ordinal Legacy Maha Deepotsav",
        "short_name": "Maha Deepotsav",
        "icon": "🪔",
        "tagline": "Ignite the Maha Akhand Jyoti, gather sacred sparks, and honor your Gharana!",
        "currency_name": "Festive Sparks",
        "currency_icon": "✨",
        "status_beacon": "Maha Akhand Jyoti",
        "description": "Sacred Festival of Lights, Diyas, Gharana Clash, and Sovereign Titles."
    },
    "christmas": {
        "id": "christmas",
        "name": "Ordinal Legacy Winter Wonderland",
        "short_name": "Winter Wonderland",
        "icon": "🎄",
        "tagline": "Unpack Santa Drops, decorate the Maha Christmas Tree, and stack Winter Snowflakes!",
        "currency_name": "Winter Snowflakes",
        "currency_icon": "❄️",
        "status_beacon": "Maha Christmas Tree",
        "description": "Christmas & New Year winter extravaganza with seasonal drops and holiday gifts."
    }
}

DEFAULT_FESTIVAL = "arcade"

def get_active_festival() -> str:
    """Returns the currently active festival theme key ('arcade', 'diwali', or 'christmas')."""
    cached = get_cache("active_festival_theme")
    if cached and cached in FESTIVAL_THEMES:
        return cached
    theme = get_system_setting("festival_theme", DEFAULT_FESTIVAL)
    if theme not in FESTIVAL_THEMES:
        theme = DEFAULT_FESTIVAL
    set_cache("active_festival_theme", theme, ttl_seconds=60.0)
    return theme

def set_active_festival(theme: str) -> Tuple[bool, str]:
    """Sets the active festival theme with cache invalidation."""
    theme_key = theme.strip().lower()
    if theme_key not in FESTIVAL_THEMES:
        valid_keys = ", ".join(FESTIVAL_THEMES.keys())
        return False, f"Invalid festival theme '{theme}'. Valid themes: {valid_keys}"
    
    set_system_setting("festival_theme", theme_key)
    delete_cache("active_festival_theme")
    set_cache("active_festival_theme", theme_key, ttl_seconds=60.0)
    return True, f"Successfully switched active festival theme to '{FESTIVAL_THEMES[theme_key]['name']}' ({theme_key})!"

def get_festival_config(theme: Optional[str] = None) -> dict:
    """Returns full configuration details of the active or requested festival."""
    active_key = theme if theme in FESTIVAL_THEMES else get_active_festival()
    return FESTIVAL_THEMES.get(active_key, FESTIVAL_THEMES[DEFAULT_FESTIVAL])

def render_festival_switch_menu() -> Tuple[str, dict]:
    """Renders the admin control panel for switching active festival modes."""
    curr = get_active_festival()
    cfg = get_festival_config(curr)
    
    text = (
        f"🎛️ <b>FESTIVAL & SEASON MANAGER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📍 <b>Active Festival</b>: {cfg['icon']} <b>{cfg['name']}</b> (<code>{curr}</code>)\n"
        f"💬 <i>{cfg['tagline']}</i>\n\n"
        f"Select a festival theme below to switch instantly:\n"
        f"• <b>🕹️ Arcade Arena</b>: Intermission / year-round mode with PvP & PvAI duels.\n"
        f"• <b>🪔 Maha Deepotsav</b>: Diwali festival with Akhand Jyoti & Gharanas.\n"
        f"• <b>🎄 Winter Wonderland</b>: Christmas festival with Snowflakes & Santa drops.\n\n"
        f"<i>Switching preserves all user scores, wicks, database records, and referral links!</i>"
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"{'✅ ' if curr == 'arcade' else ''}🕹️ Arcade Arena (PvP/PvAI)", "callback_data": "switch_fest:arcade"},
            ],
            [
                {"text": f"{'✅ ' if curr == 'diwali' else ''}🪔 Diwali Deepotsav", "callback_data": "switch_fest:diwali"},
                {"text": f"{'✅ ' if curr == 'christmas' else ''}🎄 Christmas Wonderland", "callback_data": "switch_fest:christmas"}
            ],
            [
                {"text": "🔄 Refresh Status", "callback_data": "cmd_fest_menu:admin"}
            ]
        ]
    }
    return text, keyboard

def render_welcome_for_current_festival(user: dict, first_name: str, is_verified: bool = True) -> Tuple[str, dict]:
    """Renders the appropriate /start welcome message and menu based on the active festival theme."""
    theme = get_active_festival()
    cfg = get_festival_config(theme)
    user_id = user["telegram_id"]
    points = user.get("points_total", 0)
    wicks = user.get("diya_wicks", 10)
    safe_fname = html.escape(first_name or f"Player_{user_id}")
    webapp_url = f"{settings.MINI_APP_URL}?tg_id={user_id}"

    if theme == "arcade":
        msg = (
            f"🕹️ <b>Welcome to Ordinal Legacy Arcade Arena, {safe_fname}!</b> 🕹️\n\n"
            f"The festival arena is now live in <b>Arcade Season</b>! Challenge fellow players in real-time PvP, duel our Cosmic AI, and rack up Arcade Sparks!\n\n"
            f"👤 <b>Your Dossier</b>:\n"
            f"• ⚡ <b>Arcade Sparks</b>: <code>{points:,} Pts</code>\n"
            f"• 🔋 <b>Energy Stamina</b>: <code>{wicks}/10 Wicks</code>\n\n"
            f"🎮 <b>Featured Arcade Duels & Mini-Games</b>:\n"
            f"• 🎲 <b>Dice Duel</b>: Roll against AI or challenge players (/duel)\n"
            f"• ⚔️ <b>Elemental Clash</b>: Rock-Paper-Scissors battle (/rps)\n"
            f"• 🪙 <b>Satoshi Toss</b>: Heads or Tails coin duel (/flip)\n"
            f"• 🌀 <b>Classic Hub</b>: Spin Chakri, Trace Rangoli, Catch Mithai\n\n"
            f"<i>Tap below to enter the Arena or jump into an instant duel!</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "🕹️ Open Arcade Arena (Web App)", "web_app": {"url": webapp_url}}],
                [
                    {"text": "🎲 Dice Duel (vs AI)", "callback_data": f"play_dice_ai:{user_id}"},
                    {"text": "⚔️ RPS Clash (vs AI)", "callback_data": f"play_rps_ai:{user_id}"}
                ],
                [
                    {"text": "🪙 Satoshi Flip", "callback_data": f"play_coin_ai:{user_id}"},
                    {"text": "👥 Create PvP Challenge", "callback_data": f"menu_pvp:{user_id}"}
                ],
                [
                    {"text": "🌀 Chakri", "callback_data": f"play_chakri:{user_id}"},
                    {"text": "🎨 Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                    {"text": "🍬 Mithai", "callback_data": f"play_mithai:{user_id}"}
                ],
                [
                    {"text": "📊 My Stats & Rank", "callback_data": f"cmd_mydata:{user_id}"},
                    {"text": "🏆 Top Duels Leaderboard", "callback_data": f"cmd_top:{user_id}"}
                ],
                [
                    {"text": "🤝 Invite Friends", "callback_data": f"cmd_shagun:{user_id}"},
                    {"text": "🎁 Daily Energy Refill", "callback_data": f"cmd_shubh:{user_id}"}
                ]
            ]
        }
        return msg, keyboard

    elif theme == "christmas":
        msg = (
            f"🎄 <b>Welcome to Ordinal Legacy Winter Wonderland, {safe_fname}!</b> ❄️\n\n"
            f"The snow is falling and holiday festivities have begun! Unpack Santa Drops, decorate the Maha Christmas Tree, and duel for festive Snowflakes!\n\n"
            f"👤 <b>Holiday Dossier</b>:\n"
            f"• ❄️ <b>Winter Snowflakes</b>: <code>{points:,} Pts</code>\n"
            f"• 🕯️ <b>Lantern Wicks</b>: <code>{wicks}/10 Wicks</code>\n\n"
            f"🎁 <b>Winter Activities</b>:\n"
            f"• 🎲 <b>Snowball Dice Duel</b>: /dice\n"
            f"• ⚔️ <b>Frost Clash (RPS)</b>: /rps\n"
            f"• 📦 <b>Santa Mystery Drops</b> in community chat!\n\n"
            f"<i>Tap below to enter the Winter Wonderland:</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "🎄 Enter Winter Wonderland (Web App)", "web_app": {"url": webapp_url}}],
                [
                    {"text": "🎲 Snowball Dice Duel", "callback_data": f"play_dice_ai:{user_id}"},
                    {"text": "⚔️ Frost Clash (RPS)", "callback_data": f"play_rps_ai:{user_id}"}
                ],
                [
                    {"text": "🌀 Play Mini-Games in Chat", "callback_data": f"menu_play:{user_id}"},
                    {"text": "🎁 Daily Holiday Refill", "callback_data": f"cmd_shubh:{user_id}"}
                ],
                [
                    {"text": "📊 My Holiday Dossier", "callback_data": f"cmd_mydata:{user_id}"},
                    {"text": "🏆 Winter Leaderboard", "callback_data": f"cmd_top:{user_id}"}
                ]
            ]
        }
        return msg, keyboard

    else:
        # Default / Diwali Deepotsav Mode
        g_name = settings.GHARANAS.get(user.get("gharana_id", 1), "Surya Gharana")
        msg = (
            f"🪔 *Welcome to Ordinal Legacy Maha Deepotsav, {safe_fname}!* 🪔\n\n"
            f"You have been initiated into the *{g_name}*!\n"
            f"Our sacred goal is to unite and collect *{settings.GLOBAL_MILESTONE_TARGET:,} Sparks* to ignite the community *Akhand Diya*.\n\n"
            f"• Mini-Games: /chakri, /rangoli, /mithai (1 to 3 hard points per play)\n"
            f"• Diya Companion: /shagun (Invite 1 friend as your bonded companion for daily free wicks!)\n"
            f"• Daily Refill: /shubh (Claim daily bonus wicks and sparks)\n"
            f"• Profile & Rewards: /mydata\n\n"
            f"Tap the buttons below to play:"
        )
        keyboard = {
            "inline_keyboard": [
                [{"text": "Enter Maha Deepotsav Arena (Mini-App)", "web_app": {"url": webapp_url}}],
                [{"text": "Play Mini-Games in Chat", "callback_data": f"menu_play:{user_id}"}],
                [{"text": "Play Chakri", "callback_data": f"play_chakri:{user_id}"},
                 {"text": "Play Rangoli", "callback_data": f"play_rangoli:{user_id}"},
                 {"text": "Play Mithai", "callback_data": f"play_mithai:{user_id}"}],
                [{"text": "My Dossier & Rewards", "callback_data": f"cmd_mydata:{user_id}"},
                 {"text": "Rewards Ladder", "callback_data": f"cmd_tiers:{user_id}"}],
                [{"text": "My Shagun Invite Link", "callback_data": f"cmd_shagun:{user_id}"},
                 {"text": "Claim Shubh Refill", "callback_data": f"cmd_shubh:{user_id}"}],
                [{"text": "Community Status", "callback_data": f"cmd_status:{user_id}"},
                 {"text": "Gharanas Leaderboard", "callback_data": f"cmd_gharanas:{user_id}"}]
            ]
        }
        return msg, keyboard
