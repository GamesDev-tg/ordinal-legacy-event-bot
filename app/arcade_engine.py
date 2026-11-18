import random
import uuid
import datetime
import time
import html
from typing import Optional, Dict, Any, Tuple, List
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

# -------------------------------------------------------------
# CONNECT 4 (GRAVITY FOUR-IN-A-ROW)
# -------------------------------------------------------------
_ACTIVE_C4_GAMES: Dict[str, Dict[str, Any]] = {}

def start_c4_game(p1_id: int, p1_name: str, p2_id: Optional[int] = None, p2_name: Optional[str] = None, is_vs_ai: Optional[bool] = None) -> Dict[str, Any]:
    """Starts a Connect 4 game session (7 cols x 6 rows). Supports PvP (replies/mentions/lobbies) or PvAI."""
    game_id = str(uuid.uuid4())[:10]
    
    # Determine mode: if p2_id is explicitly a positive human ID, it's PvP
    if p2_id is not None and p2_id > 0:
        is_vs_ai = False
        p2_name = p2_name or f"Player_{p2_id}"
        status = "playing"
    elif is_vs_ai is False:
        # Open group lobby awaiting Player 2
        p2_id = None
        p2_name = "[Waiting for Opponent...]"
        status = "lobby"
    else:
        # Default solo vs AI
        is_vs_ai = True
        p2_id = -99
        p2_name = p2_name or "🤖 SatoshiAI"
        status = "playing"
    
    # 6 rows, 7 cols (0 empty, 1 P1, 2 P2)
    board = [[0 for _ in range(7)] for _ in range(6)]
    
    game = {
        "id": game_id,
        "p1_id": p1_id,
        "p1_name": p1_name,
        "p2_id": p2_id,
        "p2_name": p2_name,
        "is_vs_ai": is_vs_ai,
        "board": board,
        "turn": 1, # 1 for P1, 2 for P2
        "winner": 0, # 0 ongoing, 1 P1, 2 P2, 3 tie
        "status": status,
        "created_at": datetime.datetime.now().isoformat()
    }
    _ACTIVE_C4_GAMES[game_id] = game
    return game

def join_c4_game(game_id: str, user_id: int, user_name: str) -> Tuple[bool, str]:
    """Allows another group member to accept an open Connect 4 challenge as Player 2."""
    game = _ACTIVE_C4_GAMES.get(game_id)
    if not game:
        return False, "This Connect 4 challenge has expired or not found."
    if game["p1_id"] == user_id:
        return False, "You created this challenge! Waiting for an opponent to accept."
    if game["status"] != "lobby" and game["p2_id"] is not None and game["p2_id"] > 0:
        return False, "This match already has 2 players!"

    game["p2_id"] = user_id
    game["p2_name"] = user_name
    game["is_vs_ai"] = False
    game["status"] = "playing"
    return True, f"Joined match against {game['p1_name']}!"

def switch_c4_to_ai(game_id: str, user_id: int) -> Tuple[bool, str]:
    """Switches an open lobby game to Solo vs AI."""
    game = _ACTIVE_C4_GAMES.get(game_id)
    if not game:
        return False, "Match not found."
    if game["p1_id"] != user_id:
        return False, "Only the challenger can switch to AI."
    game["p2_id"] = -99
    game["p2_name"] = "🤖 SatoshiAI"
    game["is_vs_ai"] = True
    game["status"] = "playing"
    return True, "Switched to solo vs AI!"

def _check_c4_win(board: list, piece: int) -> bool:
    """Checks horizontal, vertical, and diagonals for 4 consecutive pieces."""
    # Horizontal
    for r in range(6):
        for c in range(4):
            if board[r][c] == piece and board[r][c+1] == piece and board[r][c+2] == piece and board[r][c+3] == piece:
                return True
    # Vertical
    for r in range(3):
        for c in range(7):
            if board[r][c] == piece and board[r+1][c] == piece and board[r+2][c] == piece and board[r+3][c] == piece:
                return True
    # Positively sloped diagonals
    for r in range(3):
        for c in range(4):
            if board[r][c] == piece and board[r+1][c+1] == piece and board[r+2][c+2] == piece and board[r+3][c+3] == piece:
                return True
    # Negatively sloped diagonals
    for r in range(3, 6):
        for c in range(4):
            if board[r][c] == piece and board[r-1][c+1] == piece and board[r-2][c+2] == piece and board[r-3][c+3] == piece:
                return True
    return False

def _get_c4_valid_cols(board: list) -> list:
    """Returns columns that are not yet filled."""
    return [c for c in range(7) if board[0][c] == 0]

def _drop_c4_piece(board: list, col: int, piece: int) -> int:
    """Drops piece down column col; returns row index or -1 if full."""
    for r in range(5, -1, -1):
        if board[r][col] == 0:
            board[r][col] = piece
            return r
    return -1

def play_c4_turn(game_id: str, user_id: int, col: int) -> Dict[str, Any]:
    """Drops a chip into column col (0-6). If playing vs AI, executes AI reply immediately."""
    game = _ACTIVE_C4_GAMES.get(game_id)
    if not game or game["status"] != "playing":
        return {"success": False, "error": "Game not found or finished."}
        
    curr_turn = game["turn"]
    if curr_turn == 1 and user_id != game["p1_id"]:
        return {"success": False, "error": f"It is {game['p1_name']}'s turn!"}
    if curr_turn == 2 and user_id != game["p2_id"] and not game["is_vs_ai"]:
        return {"success": False, "error": f"It is {game['p2_name']}'s turn!"}
        
    board = game["board"]
    if col not in _get_c4_valid_cols(board):
        return {"success": False, "error": f"Column {col + 1} is already full!"}
        
    row = _drop_c4_piece(board, col, curr_turn)
    if row == -1:
        return {"success": False, "error": "Invalid column drop."}
        
    # Check win
    if _check_c4_win(board, curr_turn):
        game["winner"] = curr_turn
        game["status"] = "finished"
        winner_id = game["p1_id"] if curr_turn == 1 else game["p2_id"]
        loser_id = game["p2_id"] if curr_turn == 1 else game["p1_id"]
        _award_arcade_win(winner_id, 3)
        if not game["is_vs_ai"] and loser_id and loser_id > 0:
            _award_arcade_win(loser_id, 1)
        return {"success": True, "game_over": True, "winner": curr_turn}
        
    if not _get_c4_valid_cols(board):
        game["winner"] = 3 # Tie
        game["status"] = "finished"
        _award_arcade_win(game["p1_id"], 2)
        if not game["is_vs_ai"] and game["p2_id"] and game["p2_id"] > 0:
            _award_arcade_win(game["p2_id"], 2)
        return {"success": True, "game_over": True, "winner": 3}
        
    # Switch turn or AI reply
    if game["is_vs_ai"]:
        valid_cols = _get_c4_valid_cols(board)
        # AI heuristic: win if can, block if player can win, else center preference
        ai_col = valid_cols[0]
        # Check immediate win
        for c in valid_cols:
            b_copy = [row[:] for row in board]
            _drop_c4_piece(b_copy, c, 2)
            if _check_c4_win(b_copy, 2):
                ai_col = c
                break
        else:
            # Check immediate block
            for c in valid_cols:
                b_copy = [row[:] for row in board]
                _drop_c4_piece(b_copy, c, 1)
                if _check_c4_win(b_copy, 1):
                    ai_col = c
                    break
            else:
                # Prefer center columns (3, 2, 4, 1, 5)
                for pref in [3, 2, 4, 1, 5, 0, 6]:
                    if pref in valid_cols:
                        ai_col = pref
                        break
                        
        _drop_c4_piece(board, ai_col, 2)
        if _check_c4_win(board, 2):
            game["winner"] = 2
            game["status"] = "finished"
            return {"success": True, "game_over": True, "winner": 2}
        if not _get_c4_valid_cols(board):
            game["winner"] = 3
            game["status"] = "finished"
            return {"success": True, "game_over": True, "winner": 3}
            
        game["turn"] = 1
    else:
        game["turn"] = 2 if curr_turn == 1 else 1
        
    return {"success": True, "game_over": False}

def render_c4_view(game_id: str) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Renders visual Connect 4 grid with drop buttons and full PvP/PvAI indicators."""
    game = _ACTIVE_C4_GAMES.get(game_id)
    if not game:
        return "❌ <b>Connect 4 Session Expired.</b>", []
        
    p1 = html.escape(game["p1_name"])
    p2 = html.escape(game["p2_name"])

    # If in open lobby awaiting Player 2:
    if game["status"] == "lobby":
        text = (
            f"🔴 <b>CONNECT 4 OPEN CHALLENGE</b> 🟡\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Challenger</b>: 🔴 <b>{p1}</b>\n"
            f"⚔️ <b>Opponent</b>: <i>Waiting for a challenger to accept...</i>\n\n"
            f"🏆 <b>Stakes</b>: +3 Sparks for Winner, +1 Spark for Runner-up!\n"
            f"<i>Tap below to accept this duel or practice solo vs AI:</i>"
        )
        keyboard = [
            [{"text": "⚔️ Accept Challenge & Play (🟡)", "callback_data": f"c4_join:{game_id}"}],
            [{"text": "🤖 Play vs AI (Solo)", "callback_data": f"c4_ai:{game_id}"}]
        ]
        return text, keyboard

    symbols = {0: "⚪", 1: "🔴", 2: "🟡"}
    board_str = ""
    for r in range(6):
        row_line = "".join(symbols[game["board"][r][c]] for c in range(7))
        board_str += f"{row_line}\n"
    board_str += "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
    
    mode_tag = " [PvP Duel]" if not game["is_vs_ai"] else " [vs AI]"
    
    if game["status"] == "finished":
        if game["winner"] == 1:
            headline = f"🎉 <b>{p1} (🔴) CONNECTED 4 AND WON!</b> 🎉 (+3 Sparks)"
        elif game["winner"] == 2:
            headline = f"🎉 <b>{p2} (🟡) CONNECTED 4 AND WON!</b> 🎉 (+3 Sparks)"
        else:
            headline = "🤝 <b>STALEMATE! THE BOARD IS FULL!</b> (+2 Sparks each)"
        text = (
            f"🔴 <b>CONNECT 4 ARENA COMPLETE{mode_tag}</b> 🟡\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{board_str}\n\n"
            f"{headline}\n\n"
            f"<i>Match registered! Ready for a rematch?</i>"
        )
        if not game["is_vs_ai"] and game["p2_id"] and game["p2_id"] > 0:
            return text, [[{"text": "🔄 Rematch (Swap Colors!)", "callback_data": f"c4_rematch:{game_id}"}]]
        else:
            return text, [[{"text": "🔄 Play Again", "callback_data": f"c4_new:{game['p1_id']}"}]]
        
    turn_name = p1 if game["turn"] == 1 else p2
    turn_color = "🔴" if game["turn"] == 1 else "🟡"
    text = (
        f"🔴 <b>CONNECT 4: {p1} vs {p2}{mode_tag}</b> 🟡\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{board_str}\n\n"
        f"🎯 <b>Turn:</b> {turn_color} <b>{turn_name}</b>\n"
        f"<i>Tap a column number below to drop your chip!</i>"
    )
    
    valid_cols = _get_c4_valid_cols(game["board"])
    col_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
    btn_row = []
    for c in range(7):
        if c in valid_cols:
            btn_row.append({"text": col_emojis[c], "callback_data": f"c4_drop:{game_id}:{c}"})
        else:
            btn_row.append({"text": "✖️", "callback_data": "noop"})
            
    keyboard = [btn_row, [{"text": "🔄 Refresh Grid", "callback_data": f"c4_refresh:{game_id}"}]]
    return text, keyboard
    col_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
    btn_row = []
    for c in range(7):
        if c in valid_cols:
            btn_row.append({"text": col_emojis[c], "callback_data": f"c4_drop:{game_id}:{c}"})
        else:
            btn_row.append({"text": "✖️", "callback_data": "noop"})
            
    keyboard = [btn_row, [{"text": "🔄 Refresh Grid", "callback_data": f"c4_refresh:{game_id}"}]]
    return text, keyboard

# -------------------------------------------------------------
# 2048 SATOSHIS (CRYPTO MERGE PUZZLE)
# -------------------------------------------------------------
_ACTIVE_2048_GAMES: Dict[int, Dict[str, Any]] = {}

def start_2048_game(user_id: int) -> Dict[str, Any]:
    """Starts or resets a 4x4 2048 game for user."""
    board = [[0]*4 for _ in range(4)]
    _spawn_2048_tile(board)
    _spawn_2048_tile(board)
    game = {
        "user_id": user_id,
        "board": board,
        "score": 0,
        "game_over": False,
        "max_tile": 2
    }
    _ACTIVE_2048_GAMES[user_id] = game
    return game

def _spawn_2048_tile(board: list):
    empties = [(r, c) for r in range(4) for c in range(4) if board[r][c] == 0]
    if empties:
        r, c = random.choice(empties)
        board[r][c] = 4 if random.random() < 0.1 else 2

def _compress_and_merge_row(row: list) -> Tuple[list, int]:
    new_row = [x for x in row if x != 0]
    score_gain = 0
    merged = []
    skip = False
    for i in range(len(new_row)):
        if skip:
            skip = False
            continue
        if i + 1 < len(new_row) and new_row[i] == new_row[i+1]:
            val = new_row[i] * 2
            merged.append(val)
            score_gain += val
            skip = True
        else:
            merged.append(new_row[i])
    while len(merged) < 4:
        merged.append(0)
    return merged, score_gain

def move_2048(user_id: int, direction: str) -> Dict[str, Any]:
    """Executes a move: up, down, left, right."""
    game = _ACTIVE_2048_GAMES.get(user_id)
    if not game:
        game = start_2048_game(user_id)
    if game["game_over"]:
        return {"success": False, "error": "Game is already over! Press New Game."}
        
    board = game["board"]
    old_board = [r[:] for r in board]
    total_score = 0
    
    if direction == "left":
        for r in range(4):
            merged_row, pts = _compress_and_merge_row(board[r])
            board[r] = merged_row
            total_score += pts
    elif direction == "right":
        for r in range(4):
            merged_row, pts = _compress_and_merge_row(board[r][::-1])
            board[r] = merged_row[::-1]
            total_score += pts
    elif direction == "up":
        for c in range(4):
            col_vals = [board[r][c] for r in range(4)]
            merged_col, pts = _compress_and_merge_row(col_vals)
            for r in range(4):
                board[r][c] = merged_col[r]
            total_score += pts
    elif direction == "down":
        for c in range(4):
            col_vals = [board[r][c] for r in range(4)][::-1]
            merged_col, pts = _compress_and_merge_row(col_vals)
            merged_col = merged_col[::-1]
            for r in range(4):
                board[r][c] = merged_col[r]
            total_score += pts

    changed = (board != old_board)
    if changed:
        game["score"] += total_score
        _spawn_2048_tile(board)
        max_t = max(max(r) for r in board)
        game["max_tile"] = max(game["max_tile"], max_t)
        
        # Check if game over
        has_empty = any(0 in r for r in board)
        can_merge = False
        if not has_empty:
            for r in range(4):
                for c in range(4):
                    if (r + 1 < 4 and board[r][c] == board[r+1][c]) or (c + 1 < 4 and board[r][c] == board[r][c+1]):
                        can_merge = True
                        break
            if not can_merge:
                game["game_over"] = True
                _award_arcade_win(user_id, min(3, max(1, game["score"] // 1000)))
                
    return {"success": True, "changed": changed, "score": game["score"], "game_over": game["game_over"]}

def render_2048_view(user_id: int) -> Tuple[str, List[List[Dict[str, str]]]]:
    game = _ACTIVE_2048_GAMES.get(user_id)
    if not game:
        game = start_2048_game(user_id)
        
    board = game["board"]
    lines = []
    for r in board:
        row_str = " | ".join(f"{x:4d}" if x > 0 else "   ." for x in r)
        lines.append(f"<code>[{row_str}]</code>")
    grid_txt = "\n".join(lines)
    
    text = (
        f"⚡ <b>2048 SATOSHIS ARCADE</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>Score:</b> {game['score']:,} | <b>Max Tile:</b> {game['max_tile']}\n\n"
        f"{grid_txt}\n\n"
    )
    if game["game_over"]:
        text += "💥 <b>GAME OVER! No more moves possible.</b>\nRewards have been credited to your Sparks balance!"
        keyboard = [[{"text": "🔄 Start Fresh Game", "callback_data": f"2048_new:{user_id}"}]]
    else:
        text += "<i>Slide the Satoshi blocks in any direction!</i>"
        keyboard = [
            [{"text": "⬆️ UP", "callback_data": f"2048_move:{user_id}:up"}],
            [
                {"text": "⬅️ LEFT", "callback_data": f"2048_move:{user_id}:left"},
                {"text": "⬇️ DOWN", "callback_data": f"2048_move:{user_id}:down"},
                {"text": "➡️ RIGHT", "callback_data": f"2048_move:{user_id}:right"}
            ],
            [{"text": "🔄 Reset", "callback_data": f"2048_new:{user_id}"}]
        ]
    return text, keyboard

# -------------------------------------------------------------
# WORDLE SATOSHIS (5-LETTER CRYPTO WORD CLASH)
# -------------------------------------------------------------
WORDLE_DICTIONARY = [
    "BLOCK", "MINER", "TOKEN", "CHAIN", "HALVE", "SATOS", "NODES", "FORTH",
    "PROOF", "SHARD", "GUILD", "RUNES", "STAKE", "YIELD", "LEDGER", "FLAME",
    "LIGHT", "SPARK", "POWER", "ASSET", "TRADE", "VAULT", "QUEST", "SMART"
]
_ACTIVE_WORDLE_GAMES: Dict[int, Dict[str, Any]] = {}

def start_wordle_game(user_id: int) -> Dict[str, Any]:
    secret = random.choice([w for w in WORDLE_DICTIONARY if len(w) == 5])
    game = {
        "user_id": user_id,
        "secret": secret,
        "guesses": [], # list of {"word": "...", "pattern": "🟩🟨⬛⬛🟩"}
        "status": "playing",
        "created_at": time.time()
    }
    _ACTIVE_WORDLE_GAMES[user_id] = game
    return game

def submit_wordle_guess(user_id: int, guess: str) -> Dict[str, Any]:
    game = _ACTIVE_WORDLE_GAMES.get(user_id)
    if not game or game["status"] != "playing":
        game = start_wordle_game(user_id)
        
    guess = guess.strip().upper()
    if len(guess) != 5 or not guess.isalpha():
        return {"success": False, "error": "Guess must be an exact 5-letter word!"}
        
    secret = game["secret"]
    pattern = ["⬛"] * 5
    secret_chars = list(secret)
    
    # First pass: Green matches
    for i in range(5):
        if guess[i] == secret[i]:
            pattern[i] = "🟩"
            secret_chars[i] = None
            
    # Second pass: Yellow matches
    for i in range(5):
        if pattern[i] != "🟩" and guess[i] in secret_chars:
            pattern[i] = "🟨"
            secret_chars[secret_chars.index(guess[i])] = None
            
    pattern_str = "".join(pattern)
    game["guesses"].append({"word": guess, "pattern": pattern_str})
    
    if guess == secret:
        game["status"] = "won"
        _award_arcade_win(user_id, 3)
        return {"success": True, "result": "won", "pattern": pattern_str}
    elif len(game["guesses"]) >= 6:
        game["status"] = "lost"
        _award_arcade_win(user_id, 1)
        return {"success": True, "result": "lost", "pattern": pattern_str, "secret": secret}
    else:
        return {"success": True, "result": "continue", "pattern": pattern_str}

def render_wordle_view(user_id: int) -> Tuple[str, List[List[Dict[str, str]]]]:
    game = _ACTIVE_WORDLE_GAMES.get(user_id)
    if not game:
        game = start_wordle_game(user_id)
        
    lines = []
    for g in game["guesses"]:
        spaced_word = " ".join(list(g["word"]))
        lines.append(f"<code>{spaced_word}</code>  {g['pattern']}")
        
    remaining = 6 - len(game["guesses"])
    for _ in range(remaining):
        lines.append("<code>_ _ _ _ _</code>  ⬛⬛⬛⬛⬛")
        
    guesses_display = "\n".join(lines)
    
    text = (
        f"🔤 <b>CRYPTO WORDLE (5 LETTERS)</b> 🔤\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{guesses_display}\n\n"
    )
    if game["status"] == "won":
        text += f"🎉 <b>GENIUS! YOU SOLVED IT: {game['secret']}!</b> 🎉\nRewarded +3 Sparks to your ledger!"
        keyboard = [[{"text": "🔄 Play Next Word", "callback_data": f"wordle_new:{user_id}"}]]
    elif game["status"] == "lost":
        text += f"💥 <b>Out of tries! The secret word was: {game['secret']}</b>\nBetter luck on the next one!"
        keyboard = [[{"text": "🔄 Try Again", "callback_data": f"wordle_new:{user_id}"}]]
    else:
        text += f"Tries remaining: <b>{remaining}/6</b>\n<i>Send any 5-letter word in chat (or click Quick Guess below)!</i>"
        quick_words = [w for w in WORDLE_DICTIONARY if len(w) == 5 and w not in [g["word"] for g in game["guesses"]]][:3]
        row = [{"text": f"💡 {w}", "callback_data": f"wordle_guess:{user_id}:{w}"} for w in quick_words]
        keyboard = [row, [{"text": "🔄 New Word", "callback_data": f"wordle_new:{user_id}"}]]
        
    return text, keyboard

def _award_arcade_win(user_id: int, points: int):
    """Internal helper to award Sparks for arcade games with atomic tier recalculation."""
    if user_id <= 0 or points <= 0:
        return
    conn = get_db_connection()
    try:
        with conn:
            u = conn.execute("SELECT points_total FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
            if u:
                new_pts = (u["points_total"] or 0) + points
                new_tier = calculate_tier(new_pts)
                conn.execute("UPDATE users SET points_total = ?, tier_level = ? WHERE telegram_id = ?", (new_pts, new_tier, user_id))
            else:
                conn.execute("UPDATE users SET points_total = points_total + ? WHERE telegram_id = ?", (points, user_id))
            conn.execute("UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1", (points,))
    except Exception as e:
        print(f"[AWARD_ARCADE_WIN_ERROR]: {e}")
    finally:
        conn.close()
    invalidate_event_cache(user_id)

