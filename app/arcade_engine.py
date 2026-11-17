import random
import uuid
import datetime
import html
from typing import Optional, Dict, Any, Tuple
from app.config import settings
from app.database import get_db_connection, is_postgres, calculate_tier
from app.cache import invalidate_event_cache

DICE_EMOJIS = {
    1: "⚀ (1)",
    2: "⚁ (2)",
    3: "⚂ (3)",
    4: "⚃ (4)",
    5: "⚄ (5)",
    6: "⚅ (6)"
}

ELEMENT_BEATS = {
    "fire": "grass",     # 🔥 burns 🌿
    "water": "fire",     # 💧 extinguishes 🔥
    "grass": "water"     # 🌿 absorbs 💧
}

ELEMENT_NAMES = {
    "fire": "🔥 Fire",
    "water": "💧 Water",
    "grass": "🌿 Earth"
}

def ensure_arcade_duels_table():
    conn = get_db_connection()
    try:
        with conn:
            if is_postgres():
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS arcade_duels (
                        id TEXT PRIMARY KEY,
                        game_type TEXT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        message_id BIGINT,
                        challenger_id BIGINT NOT NULL,
                        challenger_name TEXT NOT NULL,
                        challenger_move TEXT,
                        opponent_id BIGINT,
                        opponent_name TEXT,
                        opponent_move TEXT,
                        status TEXT DEFAULT 'pending',
                        winner_id BIGINT,
                        stakes INTEGER DEFAULT 5,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_arcade_duels_status ON arcade_duels (status);
                ''')
            else:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS arcade_duels (
                        id TEXT PRIMARY KEY,
                        game_type TEXT NOT NULL,
                        chat_id INTEGER NOT NULL,
                        message_id INTEGER,
                        challenger_id INTEGER NOT NULL,
                        challenger_name TEXT NOT NULL,
                        challenger_move TEXT,
                        opponent_id INTEGER,
                        opponent_name TEXT,
                        opponent_move TEXT,
                        status TEXT DEFAULT 'pending',
                        winner_id INTEGER,
                        stakes INTEGER DEFAULT 5,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_arcade_duels_status ON arcade_duels (status);
                ''')
    except Exception as e:
        print(f"[ENSURE_ARCADE_DUELS_TABLE_ERROR]: {e}")
    finally:
        conn.close()

def play_dice_vs_ai(user_id: int, first_name: str) -> dict:
    """Player vs Cosmic AI: Roll dice showdown."""
    conn = get_db_connection()
    try:
        with conn:
            from app.game_engine import update_user_stamina
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT points_total, diya_wicks, tier_level FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"success": False, "error": "User record not found. Send /start first!"}
            
            p_roll = random.randint(1, 6)
            ai_roll = random.randint(1, 6)
            
            if p_roll > ai_roll:
                outcome = "win"
                sparks_awarded = 3
                headline = "🎉 <b>VICTORY! YOU DEFEATED THE AI!</b> 🎉"
            elif p_roll == ai_roll:
                outcome = "tie"
                sparks_awarded = 2
                headline = "🤝 <b>PERFECT TIE!</b> Cosmic stalemate!"
            else:
                outcome = "loss"
                sparks_awarded = 1
                headline = "🤖 <b>AI WINS THIS ROUND!</b> Good effort!"

            new_pts = (u["points_total"] or 0) + sparks_awarded
            new_tier = calculate_tier(new_pts)
            
            # Record points
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, user_id))
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (sparks_awarded,))
            invalidate_event_cache(user_id)
            
            p_die = DICE_EMOJIS[p_roll]
            ai_die = DICE_EMOJIS[ai_roll]
            safe_name = html.escape(first_name or f"Player_{user_id}")
            
            msg = (
                f"🎲 <b>COSMIC DICE DUEL (vs AI)</b> 🎲\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{headline}\n\n"
                f"👤 <b>{safe_name}</b>: {p_die}\n"
                f"🤖 <b>Cosmic Bot AI</b>: {ai_die}\n\n"
                f"⚡ <b>Reward</b>: <b>+{sparks_awarded} Arcade Sparks</b>\n"
                f"📊 <b>Total Sparks</b>: <code>{new_pts:,} Pts</code>\n\n"
                f"<i>Keep rolling to level up or challenge a friend in the group with /duel!</i>"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🎲 Roll Again", "callback_data": f"play_dice_ai:{user_id}"},
                        {"text": "⚔️ RPS Clash", "callback_data": f"play_rps_ai:{user_id}"}
                    ],
                    [
                        {"text": "👥 Create PvP Duel", "callback_data": f"menu_pvp:{user_id}"},
                        {"text": "📊 My Stats", "callback_data": f"cmd_mydata:{user_id}"}
                    ]
                ]
            }
            return {"success": True, "message": msg, "keyboard": keyboard, "outcome": outcome}
    finally:
        conn.close()

def play_rps_vs_ai(user_id: int, first_name: str, player_move: str) -> dict:
    """Player vs Cosmic AI: Elemental Clash (Fire / Water / Earth)."""
    move = player_move.lower().strip()
    if move not in ELEMENT_BEATS:
        move = random.choice(["fire", "water", "grass"])
    
    ai_move = random.choice(["fire", "water", "grass"])
    
    conn = get_db_connection()
    try:
        with conn:
            from app.game_engine import update_user_stamina
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT points_total, diya_wicks, tier_level FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"success": False, "error": "User record not found. Send /start first!"}
            
            if move == ai_move:
                outcome = "tie"
                sparks_awarded = 2
                headline = "🤝 <b>ELEMENTAL DRAW!</b> Dual forces neutralized!"
            elif ELEMENT_BEATS[move] == ai_move:
                outcome = "win"
                sparks_awarded = 3
                headline = "🔥 <b>ELEMENTAL VICTORY!</b> Your element prevailed!"
            else:
                outcome = "loss"
                sparks_awarded = 1
                headline = "🌊 <b>AI COUNTERED YOUR ELEMENT!</b> Try another stance!"

            new_pts = (u["points_total"] or 0) + sparks_awarded
            new_tier = calculate_tier(new_pts)
            
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, user_id))
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (sparks_awarded,))
            invalidate_event_cache(user_id)
            
            safe_name = html.escape(first_name or f"Player_{user_id}")
            p_elem = ELEMENT_NAMES.get(move, move)
            ai_elem = ELEMENT_NAMES.get(ai_move, ai_move)
            
            msg = (
                f"⚔️ <b>ELEMENTAL CLASH (vs AI)</b> ⚔️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{headline}\n\n"
                f"👤 <b>{safe_name}</b> summoned: <b>{p_elem}</b>\n"
                f"🤖 <b>Cosmic Bot</b> cast: <b>{ai_elem}</b>\n\n"
                f"⚡ <b>Reward</b>: <b>+{sparks_awarded} Arcade Sparks</b>\n"
                f"📊 <b>Total Sparks</b>: <code>{new_pts:,} Pts</code>\n\n"
                f"<i>Rules: 🔥 Fire beats 🌿 Earth • 💧 Water beats 🔥 Fire • 🌿 Earth beats 💧 Water</i>"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🔥 Pick Fire", "callback_data": f"rps_ai:{user_id}:fire"},
                        {"text": "💧 Pick Water", "callback_data": f"rps_ai:{user_id}:water"},
                        {"text": "🌿 Pick Earth", "callback_data": f"rps_ai:{user_id}:grass"}
                    ],
                    [
                        {"text": "🎲 Play Dice Duel", "callback_data": f"play_dice_ai:{user_id}"},
                        {"text": "🪙 Satoshi Flip", "callback_data": f"play_coin_ai:{user_id}"}
                    ]
                ]
            }
            return {"success": True, "message": msg, "keyboard": keyboard, "outcome": outcome}
    finally:
        conn.close()

def play_coin_vs_ai(user_id: int, first_name: str, choice: str = "heads") -> dict:
    """Satoshi Coin Flip prediction."""
    user_choice = choice.lower().strip()
    if user_choice not in ("heads", "tails"):
        user_choice = "heads"
        
    coin_result = random.choice(["heads", "tails"])
    is_correct = (user_choice == coin_result)
    sparks_awarded = 3 if is_correct else 1
    
    conn = get_db_connection()
    try:
        with conn:
            from app.game_engine import update_user_stamina
            update_user_stamina(conn, user_id)
            u = conn.execute("SELECT points_total, diya_wicks, tier_level FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if not u:
                return {"success": False, "error": "User record not found. Send /start first!"}
                
            new_pts = (u["points_total"] or 0) + sparks_awarded
            new_tier = calculate_tier(new_pts)
            
            conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, user_id))
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (sparks_awarded,))
            invalidate_event_cache(user_id)
            
            safe_name = html.escape(first_name or f"Player_{user_id}")
            result_icon = "🪙 Heads" if coin_result == "heads" else "🌕 Tails"
            guess_icon = "🪙 Heads" if user_choice == "heads" else "🌕 Tails"
            
            status = "🎉 <b>PREDICTION CORRECT!</b>" if is_correct else "❌ <b>CLOSE CALL!</b>"
            
            msg = (
                f"🪙 <b>SATOSHI COIN FLIP</b> 🪙\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{status}\n\n"
                f"👤 <b>{safe_name}</b> guessed: <b>{guess_icon}</b>\n"
                f"💫 <b>Coin Landed On</b>: <b>{result_icon}</b>\n\n"
                f"⚡ <b>Reward</b>: <b>+{sparks_awarded} Arcade Sparks</b>\n"
                f"📊 <b>Total Sparks</b>: <code>{new_pts:,} Pts</code>\n\n"
                f"<i>Flip again or battle a real player with /duel!</i>"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🪙 Flip Heads", "callback_data": f"coin_ai:{user_id}:heads"},
                        {"text": "🌕 Flip Tails", "callback_data": f"coin_ai:{user_id}:tails"}
                    ],
                    [
                        {"text": "🎲 Dice Duel", "callback_data": f"play_dice_ai:{user_id}"},
                        {"text": "⚔️ RPS Clash", "callback_data": f"play_rps_ai:{user_id}"}
                    ]
                ]
            }
            return {"success": True, "message": msg, "keyboard": keyboard, "is_correct": is_correct}
    finally:
        conn.close()

def create_pvp_dice_challenge(chat_id: int, challenger_id: int, challenger_name: str, target_uid: Optional[int] = None) -> Tuple[str, dict]:
    """Creates a PvP open challenge in a Telegram group."""
    ensure_arcade_duels_table()
    duel_id = f"duel_{uuid.uuid4().hex[:8]}"
    safe_name = html.escape(challenger_name or f"Player_{challenger_id}")
    
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                '''INSERT INTO arcade_duels (id, game_type, chat_id, challenger_id, challenger_name, opponent_id, status)
                   VALUES (?, 'dice', ?, ?, ?, ?, 'pending')''',
                (duel_id, chat_id, challenger_id, safe_name, target_uid)
            )
    finally:
        conn.close()
        
    text = (
        f"⚔️ <b>ARCADE DICE DUEL CHALLENGE!</b> 🎲\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Challenger</b>: <b>{safe_name}</b>\n"
        f"🎮 <b>Arena Game</b>: Cosmic Dice Showdown\n"
        f"🏆 <b>Stakes</b>: <b>+5 Sparks</b> to the winner, <b>+2 Sparks</b> to runner-up!\n\n"
        f"<i>Tap below to accept the challenge and roll your dice!</i>"
    )
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "⚔️ Accept Challenge & Roll Dice! 🎲", "callback_data": f"accept_duel:{duel_id}"}],
            [{"text": "🤖 Practice vs AI", "callback_data": f"play_dice_ai:{challenger_id}"}]
        ]
    }
    return text, keyboard

def accept_pvp_dice_challenge(duel_id: str, opponent_id: int, opponent_name: str) -> dict:
    """Opponent accepts the challenge: bot rolls for both and resolves the match."""
    ensure_arcade_duels_table()
    conn = get_db_connection()
    try:
        with conn:
            duel = conn.execute("SELECT * FROM arcade_duels WHERE id = ?", (duel_id,)).fetchone()
            if not duel:
                return {"success": False, "error": "This duel does not exist or has expired."}
            
            if duel["status"] != "pending":
                return {"success": False, "error": "This duel has already been played or accepted!"}
                
            challenger_id = duel["challenger_id"]
            if opponent_id == challenger_id:
                return {"success": False, "error": "You cannot duel yourself! Share the challenge with friends in the group."}
            
            if duel["opponent_id"] and duel["opponent_id"] != opponent_id:
                return {"success": False, "error": "This challenge was specifically directed to someone else."}
            
            safe_opp = html.escape(opponent_name or f"Player_{opponent_id}")
            safe_chal = duel["challenger_name"]
            
            # Roll dice for both
            c_roll = random.randint(1, 6)
            o_roll = random.randint(1, 6)
            
            if c_roll > o_roll:
                winner_id = challenger_id
                winner_name = safe_chal
                c_pts, o_pts = 5, 2
                headline = f"🏆 <b>{safe_chal} TRIUMPHS!</b> 🏆"
            elif o_roll > c_roll:
                winner_id = opponent_id
                winner_name = safe_opp
                c_pts, o_pts = 2, 5
                headline = f"🏆 <b>{safe_opp} TRIUMPHS!</b> 🏆"
            else:
                winner_id = None
                winner_name = "Draw"
                c_pts, o_pts = 3, 3
                headline = "🤝 <b>PERFECT TIE! BOTH PLAYERS EQUALLY MATCHED!</b> 🤝"

            # Update duel status
            conn.execute(
                "UPDATE arcade_duels SET opponent_id = ?, opponent_name = ?, challenger_move = ?, opponent_move = ?, status = 'completed', winner_id = ? WHERE id = ?",
                (opponent_id, safe_opp, str(c_roll), str(o_roll), winner_id, duel_id)
            )
            
            # Award points to both
            conn.execute("UPDATE users SET points_total = points_total + ? WHERE telegram_id = ?", (c_pts, challenger_id))
            conn.execute("UPDATE users SET points_total = points_total + ? WHERE telegram_id = ?", (o_pts, opponent_id))
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (c_pts + o_pts,))
            
            invalidate_event_cache(challenger_id)
            invalidate_event_cache(opponent_id)
            
            c_die = DICE_EMOJIS[c_roll]
            o_die = DICE_EMOJIS[o_roll]
            
            msg = (
                f"⚔️ <b>DICE DUEL SHOWDOWN COMPLETE!</b> ⚔️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{headline}\n\n"
                f"👤 <b>{safe_chal}</b>: {c_die} (+{c_pts} Sparks)\n"
                f"👤 <b>{safe_opp}</b>: {o_die} (+{o_pts} Sparks)\n\n"
                f"🔥 <i>Match recorded in the Arcade Arena! Good game to both warriors!</i>"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "⚔️ Start New PvP Duel", "callback_data": f"menu_pvp:{opponent_id}"}],
                    [{"text": "🎲 Practice vs AI", "callback_data": f"play_dice_ai:{opponent_id}"}]
                ]
            }
            return {"success": True, "message": msg, "keyboard": keyboard}
    finally:
        conn.close()
