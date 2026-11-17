import random
import uuid
import time
import html
from typing import Optional, Dict, Any, List, Tuple
from app.config import settings
from app.database import get_db_connection, is_postgres
from app.cache import invalidate_event_cache

# Color pallette supporting up to 8 players
LUDO_COLORS = [
    {"id": "red", "name": "Red", "emoji": "🔴", "color": "#EF4444"},
    {"id": "green", "name": "Green", "emoji": "🟢", "color": "#10B981"},
    {"id": "yellow", "name": "Yellow", "emoji": "🟡", "color": "#F59E0B"},
    {"id": "blue", "name": "Blue", "emoji": "🔵", "color": "#3B82F6"},
    {"id": "orange", "name": "Orange", "emoji": "🟠", "color": "#F97316"},
    {"id": "purple", "name": "Purple", "emoji": "🟣", "color": "#A855F7"},
    {"id": "cyan", "name": "Cyan", "emoji": "🩵", "color": "#06B6D4"},
    {"id": "pink", "name": "Pink", "emoji": "🩷", "color": "#EC4899"}
]

AI_NAMES = [
    "🤖 SatoshiBot",
    "🤖 HalFinneyBot",
    "🤖 NickSzaboBot",
    "🤖 VitalikBot",
    "🤖 CyberSamurai",
    "🤖 OrdinalOracle",
    "🤖 QuantumAI"
]

# In-memory active game storage with lock-free thread safety
_ACTIVE_LUDO_GAMES: Dict[str, Dict[str, Any]] = {}

def get_color_sequence(num_players: int) -> List[int]:
    """Returns color indices chosen for the player count to maximize contrast."""
    if num_players == 2:
        return [0, 2] # Red vs Yellow (opposite sides)
    elif num_players == 3:
        return [0, 1, 2] # Red, Green, Yellow
    elif num_players == 4:
        return [0, 1, 2, 3] # Red, Green, Yellow, Blue
    elif num_players == 5:
        return [0, 4, 1, 3, 5] # Red, Orange, Green, Blue, Purple
    elif num_players == 6:
        return [0, 4, 2, 1, 3, 5] # Red, Orange, Yellow, Green, Blue, Purple
    elif num_players == 7:
        return [0, 4, 2, 1, 6, 3, 5]
    else: # 8 players
        return [0, 4, 2, 1, 6, 3, 5, 7]

def get_track_config(num_players: int):
    """Returns total track steps, start positions, home entries, and safe stars."""
    if num_players <= 4:
        # Standard 52 step board
        circuit_len = 52
        # For standard 4 positions: Red=0, Green=13, Yellow=26, Blue=39
        std_starts = [0, 13, 26, 39]
        safe_stars = [0, 8, 13, 21, 26, 34, 39, 47]
        starts = {}
        home_entries = {}
        for idx in range(4):
            s = std_starts[idx]
            starts[idx] = s
            home_entries[idx] = (s - 2) % circuit_len
        return circuit_len, starts, home_entries, safe_stars
    else:
        # Extended 80 step board for 5-8 players (10 steps per sector)
        circuit_len = 80
        safe_stars = []
        starts = {}
        home_entries = {}
        for idx in range(8):
            s = idx * 10
            starts[idx] = s
            home_entries[idx] = (s - 2) % circuit_len
            safe_stars.append(s)
            safe_stars.append((s + 8) % circuit_len)
        return circuit_len, starts, home_entries, safe_stars

def create_ludo_game(host_id: int, host_name: str, num_players: int = 4, chat_id: Optional[int] = None, message_id: Optional[int] = None) -> Dict[str, Any]:
    """Creates a new Ludo match lobby."""
    num_players = max(2, min(8, num_players))
    game_id = str(uuid.uuid4())[:12]
    
    color_indices = get_color_sequence(num_players)
    circuit_len, starts, home_entries, safe_stars = get_track_config(num_players)
    
    # Host is Player 0
    host_color_idx = color_indices[0]
    players = [
        {
            "id": host_id,
            "name": host_name,
            "color_idx": host_color_idx,
            "color_name": LUDO_COLORS[host_color_idx]["name"],
            "color_emoji": LUDO_COLORS[host_color_idx]["emoji"],
            "is_ai": False,
            "pawns": [
                {"id": 0, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 1, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 2, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 3, "state": "yard", "pos": -1, "steps_traveled": 0}
            ],
            "rank": None
        }
    ]
    
    game = {
        "id": game_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "host_id": host_id,
        "num_players": num_players,
        "color_indices": color_indices,
        "circuit_len": circuit_len,
        "starts": starts,
        "home_entries": home_entries,
        "safe_stars": safe_stars,
        "status": "lobby", # lobby, playing, finished
        "turn_idx": 0,
        "last_roll": None,
        "consecutive_sixes": 0,
        "awaiting_pawn_choice": False,
        "movable_pawns": [],
        "winners": [],
        "logs": [f"🎲 {host_name} hosted a {num_players}-player Ludo game!"],
        "created_at": time.time(),
        "players": players
    }
    
    _ACTIVE_LUDO_GAMES[game_id] = game
    return game

def join_ludo_game(game_id: str, user_id: int, user_name: str) -> Tuple[bool, str]:
    """Adds a human player to the Ludo lobby."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return False, "Game lobby expired or not found."
    if game["status"] != "lobby":
        return False, "This game is already in progress or finished."
    
    for p in game["players"]:
        if p["id"] == user_id:
            return False, "You have already joined this game lobby!"
            
    if len(game["players"]) >= game["num_players"]:
        return False, "Lobby is full!"
        
    p_slot = len(game["players"])
    color_idx = game["color_indices"][p_slot]
    
    game["players"].append({
        "id": user_id,
        "name": user_name,
        "color_idx": color_idx,
        "color_name": LUDO_COLORS[color_idx]["name"],
        "color_emoji": LUDO_COLORS[color_idx]["emoji"],
        "is_ai": False,
        "pawns": [
            {"id": 0, "state": "yard", "pos": -1, "steps_traveled": 0},
            {"id": 1, "state": "yard", "pos": -1, "steps_traveled": 0},
            {"id": 2, "state": "yard", "pos": -1, "steps_traveled": 0},
            {"id": 3, "state": "yard", "pos": -1, "steps_traveled": 0}
        ],
        "rank": None
    })
    
    game["logs"].append(f"👋 {user_name} joined as {LUDO_COLORS[color_idx]['emoji']} {LUDO_COLORS[color_idx]['name']}!")
    return True, f"Successfully joined as {LUDO_COLORS[color_idx]['emoji']} {LUDO_COLORS[color_idx]['name']}!"

def fill_ludo_with_ai(game_id: str) -> Tuple[bool, str]:
    """Fills empty spots in lobby with AI bots."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return False, "Game not found."
    if game["status"] != "lobby":
        return False, "Game already started."
        
    ai_counter = 0
    while len(game["players"]) < game["num_players"]:
        p_slot = len(game["players"])
        color_idx = game["color_indices"][p_slot]
        ai_name = AI_NAMES[ai_counter % len(AI_NAMES)]
        ai_counter += 1
        
        game["players"].append({
            "id": -(100 + p_slot),
            "name": ai_name,
            "color_idx": color_idx,
            "color_name": LUDO_COLORS[color_idx]["name"],
            "color_emoji": LUDO_COLORS[color_idx]["emoji"],
            "is_ai": True,
            "pawns": [
                {"id": 0, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 1, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 2, "state": "yard", "pos": -1, "steps_traveled": 0},
                {"id": 3, "state": "yard", "pos": -1, "steps_traveled": 0}
            ],
            "rank": None
        })
        game["logs"].append(f"🤖 {ai_name} joined as {LUDO_COLORS[color_idx]['emoji']} {LUDO_COLORS[color_idx]['name']}!")
        
    game["status"] = "playing"
    game["logs"].append("🚀 All seats filled! The Ludo match begins!")
    return True, "All seats filled with AI bots and match started!"

def start_ludo_game(game_id: str, user_id: int) -> Tuple[bool, str]:
    """Starts the game, filling any remaining empty spots with AI if requested."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return False, "Game not found."
    if game["host_id"] != user_id:
        return False, "Only the game host can start the match."
    if game["status"] != "lobby":
        return False, "Game already started."
        
    if len(game["players"]) < game["num_players"]:
        fill_ludo_with_ai(game_id)
    else:
        game["status"] = "playing"
        game["logs"].append("🚀 The Ludo match begins!")
        
    return True, "Match started!"

def get_movable_pawns(game: Dict[str, Any], player_idx: int, roll: int) -> List[int]:
    """Calculates which pawns of the given player can legally move with `roll`."""
    player = game["players"][player_idx]
    color_idx = player["color_idx"]
    circuit_len = game["circuit_len"]
    home_entry = game["home_entries"][color_idx]
    
    movable = []
    for pawn in player["pawns"]:
        p_id = pawn["id"]
        state = pawn["state"]
        pos = pawn["pos"]
        steps = pawn["steps_traveled"]
        
        if state == "yard":
            # Need a 6 to enter
            if roll == 6:
                movable.append(p_id)
        elif state == "track":
            # Can advance. Check if roll enters or overshoots home
            dist_to_entry = (home_entry - pos) % circuit_len
            if steps + roll > circuit_len:
                # Entering home run
                overshoot = (steps + roll) - (circuit_len + 1)
                if overshoot <= 5: # 5 is Goal
                    movable.append(p_id)
            else:
                movable.append(p_id)
        elif state == "home":
            # In home corridor (pos is 0..4). 5 is goal
            if pos + roll <= 5:
                movable.append(p_id)
        # Goal pawns cannot move
    return movable

def apply_pawn_move(game: Dict[str, Any], player_idx: int, pawn_id: int, roll: int) -> Dict[str, Any]:
    """Executes a pawn move, checks for captures, home goal, and returns event summary."""
    player = game["players"][player_idx]
    color_idx = player["color_idx"]
    circuit_len = game["circuit_len"]
    start_pos = game["starts"][color_idx]
    home_entry = game["home_entries"][color_idx]
    safe_stars = game["safe_stars"]
    
    pawn = player["pawns"][pawn_id]
    captured = False
    reached_goal = False
    captured_player_name = ""
    
    if pawn["state"] == "yard":
        # Enters the board at start_pos
        pawn["state"] = "track"
        pawn["pos"] = start_pos
        pawn["steps_traveled"] = 1
        game["logs"].append(f"✨ {player['color_emoji']} {player['name']}'s Pawn {pawn_id + 1} entered the board at [{start_pos}]!")
    elif pawn["state"] == "track":
        old_pos = pawn["pos"]
        steps_so_far = pawn["steps_traveled"]
        
        # Check if enters home corridor
        if steps_so_far + roll > circuit_len:
            home_step = (steps_so_far + roll) - (circuit_len + 1)
            if home_step == 5:
                pawn["state"] = "goal"
                pawn["pos"] = 5
                pawn["steps_traveled"] = steps_so_far + roll
                reached_goal = True
                game["logs"].append(f"🏆 {player['color_emoji']} {player['name']}'s Pawn {pawn_id + 1} REACHED THE GOAL!")
            else:
                pawn["state"] = "home"
                pawn["pos"] = home_step
                pawn["steps_traveled"] = steps_so_far + roll
                game["logs"].append(f"🌈 {player['color_emoji']} {player['name']}'s Pawn {pawn_id + 1} entered Home Corridor (Step {home_step + 1}/5)!")
        else:
            new_pos = (old_pos + roll) % circuit_len
            pawn["pos"] = new_pos
            pawn["steps_traveled"] += roll
            
            # Check for captures if not a safe star
            if new_pos not in safe_stars:
                for opp_idx, opp in enumerate(game["players"]):
                    if opp_idx == player_idx:
                        continue
                    for opp_pawn in opp["pawns"]:
                        if opp_pawn["state"] == "track" and opp_pawn["pos"] == new_pos:
                            # Capture!
                            opp_pawn["state"] = "yard"
                            opp_pawn["pos"] = -1
                            opp_pawn["steps_traveled"] = 0
                            captured = True
                            captured_player_name = opp["name"]
                            game["logs"].append(f"💥 {player['color_emoji']} {player['name']} CAPTURED {opp['color_emoji']} {opp['name']}'s Pawn at [{new_pos}]!")
    elif pawn["state"] == "home":
        new_home_pos = pawn["pos"] + roll
        if new_home_pos == 5:
            pawn["state"] = "goal"
            pawn["pos"] = 5
            reached_goal = True
            game["logs"].append(f"🏆 {player['color_emoji']} {player['name']}'s Pawn {pawn_id + 1} REACHED THE GOAL!")
        else:
            pawn["pos"] = new_home_pos
            game["logs"].append(f"🌈 {player['color_emoji']} {player['name']}'s Pawn {pawn_id + 1} moved to Home Step {new_home_pos + 1}/5!")

    # Check if player finished all 4 pawns
    all_goal = all(p["state"] == "goal" for p in player["pawns"])
    if all_goal and player["rank"] is None:
        rank = len(game["winners"]) + 1
        player["rank"] = rank
        game["winners"].append(player["id"])
        game["logs"].append(f"🎉 <b>{player['color_emoji']} {player['name']} FINISHED AT RANK #{rank}!</b> 🎉")
        
        # Check if game is over (only 1 player remains)
        unfinished = [p for p in game["players"] if p["rank"] is None]
        if len(unfinished) <= 1:
            game["status"] = "finished"
            game["logs"].append("🏁 <b>The Ludo Game is Officially Completed!</b>")
            _award_ludo_rewards(game)
            return {"success": True, "captured": captured, "reached_goal": reached_goal, "game_over": True}

    return {"success": True, "captured": captured, "reached_goal": reached_goal, "game_over": False}

def _award_ludo_rewards(game: Dict[str, Any]):
    """Awards Sparks/points to human winners and participants in DB."""
    conn = get_db_connection()
    try:
        with conn:
            for idx, p in enumerate(game["players"]):
                if p["is_ai"] or p["id"] <= 0 or p.get("resigned", False):
                    continue
                rank = p["rank"]
                if rank == 1:
                    awarded = 3
                elif rank == 2:
                    awarded = 2
                else:
                    awarded = 1
                    
                conn.execute(
                    "UPDATE users SET points_total = points_total + ? WHERE telegram_id = ?",
                    (awarded, p["id"])
                )
                conn.execute(
                    "UPDATE community_state SET total_sparks = total_sparks + ? WHERE id = 1",
                    (awarded,)
                )
    except Exception as e:
        print(f"[LUDO_AWARD_ERROR]: {e}")
    finally:
        conn.close()
    invalidate_event_cache()

def advance_turn(game: Dict[str, Any], bonus_turn: bool = False):
    """Passes the turn to the next active player unless bonus turn is awarded."""
    game["last_roll"] = None
    game["awaiting_pawn_choice"] = False
    game["movable_pawns"] = []
    
    if game["status"] == "finished":
        return
        
    if bonus_turn:
        # Same player rolls again
        curr = game["players"][game["turn_idx"]]
        game["logs"].append(f"🌟 {curr['color_emoji']} {curr['name']} gets a BONUS ROLL!")
        return

    # Pass to next player who hasn't finished all pawns and has not resigned
    game["consecutive_sixes"] = 0
    total = len(game["players"])
    for i in range(1, total + 1):
        next_idx = (game["turn_idx"] + i) % total
        p = game["players"][next_idx]
        if p["rank"] is None and not p.get("resigned", False):
            game["turn_idx"] = next_idx
            return

def roll_ludo_dice(game_id: str, user_id: int) -> Dict[str, Any]:
    """Rolls dice for current player and determines valid moves."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return {"success": False, "error": "Game not found."}
    if game["status"] != "playing":
        return {"success": False, "error": "Game is not currently active."}
        
    curr_player = game["players"][game["turn_idx"]]
    if curr_player["id"] != user_id and not curr_player["is_ai"]:
        return {"success": False, "error": f"It is not your turn! Waiting for {curr_player['name']}."}
    if game["awaiting_pawn_choice"]:
        return {"success": False, "error": "You must select a pawn to move first!"}
        
    roll = random.randint(1, 6)
    game["last_roll"] = roll
    
    if roll == 6:
        game["consecutive_sixes"] += 1
    else:
        game["consecutive_sixes"] = 0
        
    game["logs"].append(f"🎲 {curr_player['color_emoji']} {curr_player['name']} rolled a <b>{roll}</b>!")
    
    # Check 3 consecutive sixes rule
    if game["consecutive_sixes"] >= 3:
        game["logs"].append(f"⚠️ 3 consecutive sixes! Turn forfeited for {curr_player['name']}.")
        advance_turn(game, bonus_turn=False)
        return {"success": True, "roll": roll, "auto_moved": False, "turn_passed": True}
        
    movable = get_movable_pawns(game, game["turn_idx"], roll)
    
    if not movable:
        game["logs"].append(f"⏭️ No legal moves for {curr_player['name']}. Passing turn.")
        advance_turn(game, bonus_turn=False)
        return {"success": True, "roll": roll, "auto_moved": False, "turn_passed": True}
        
    all_in_yard = all(curr_player["pawns"][p]["state"] == "yard" for p in movable)
    if len(movable) == 1 or all_in_yard:
        # Only 1 valid move (or all movable pawns are in base so choice is identical)
        chosen_pawn = movable[0]
        res = apply_pawn_move(game, game["turn_idx"], chosen_pawn, roll)
        bonus = (roll == 6 and game["consecutive_sixes"] < 3) or res.get("captured", False)
        advance_turn(game, bonus_turn=bonus)
        return {"success": True, "roll": roll, "auto_moved": True, "pawn_id": chosen_pawn, "bonus_turn": bonus}
    else:
        # Multiple choices: await player decision
        game["awaiting_pawn_choice"] = True
        game["movable_pawns"] = movable
        return {"success": True, "roll": roll, "auto_moved": False, "movable_pawns": movable}

def move_ludo_pawn(game_id: str, user_id: int, pawn_id: int) -> Dict[str, Any]:
    """Moves the player's chosen pawn."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return {"success": False, "error": "Game not found."}
    if not game["awaiting_pawn_choice"]:
        return {"success": False, "error": "Roll the dice before moving a pawn!"}
        
    curr_player = game["players"][game["turn_idx"]]
    if curr_player["id"] != user_id and not curr_player["is_ai"]:
        return {"success": False, "error": f"It is not your turn! Waiting for {curr_player['name']}."}
        
    if pawn_id not in game["movable_pawns"]:
        return {"success": False, "error": f"Pawn {pawn_id + 1} cannot make a legal move with roll {game['last_roll']}!"}
        
    roll = game["last_roll"]
    res = apply_pawn_move(game, game["turn_idx"], pawn_id, roll)
    bonus = (roll == 6 and game["consecutive_sixes"] < 3) or res.get("captured", False)
    advance_turn(game, bonus_turn=bonus)
    return {"success": True, "bonus_turn": bonus, "game_over": res.get("game_over", False)}

def forfeit_or_exit_ludo_game(game_id: str, user_id: int) -> Dict[str, Any]:
    """
    Handles a player quitting/exiting a Ludo game.
    - If 2-player match: Remaining opponent wins immediately.
    - If multiplayer match (> 2 players): The quitting player forfeits/loses,
      and the match continues with the remaining active players.
    """
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return {"success": False, "error": "Game not found."}
        
    if game["status"] == "lobby":
        # In lobby: remove player or cancel if host
        if game["host_id"] == user_id:
            game["status"] = "finished"
            return {"success": True, "game_over": True, "message": "Host left. Lobby cancelled."}
        else:
            game["players"] = [p for p in game["players"] if p["id"] != user_id]
            game["logs"].append(f"🚪 A player left the lobby.")
            return {"success": True, "game_over": False, "message": "You left the lobby."}

    if game["status"] != "playing":
        return {"success": False, "error": "Game is not currently active."}

    # Find the player quitting
    p_idx = None
    for idx, p in enumerate(game["players"]):
        if p["id"] == user_id:
            p_idx = idx
            break

    if p_idx is None:
        return {"success": False, "error": "You are not a player in this game."}

    quitter = game["players"][p_idx]
    if quitter.get("resigned", False):
        return {"success": False, "error": "You have already resigned from this match."}

    quitter["resigned"] = True
    quitter["rank"] = len(game["players"]) # Last place
    game["logs"].append(f"🚪 {quitter['color_emoji']} <b>{quitter['name']} quit and forfeited!</b>")

    active_players = [p for p in game["players"] if not p.get("resigned", False) and p.get("rank") is None]

    # Rule: 2-player game OR only 1 player left -> opponent wins immediately!
    if game["num_players"] == 2 or len(active_players) <= 1:
        game["status"] = "finished"
        winner = active_players[0] if active_players else [p for p in game["players"] if p["id"] != user_id][0]
        winner["rank"] = 1
        if winner["id"] not in game["winners"]:
            game["winners"].append(winner["id"])
        game["logs"].append(f"👑 {winner['color_emoji']} <b>{winner['name']} wins the match by forfeit!</b>")
        _award_ludo_rewards(game)
        return {
            "success": True,
            "game_over": True,
            "winner": winner["name"],
            "message": f"🏳️ {quitter['name']} forfeited! {winner['name']} wins!"
        }
    else:
        # Multiplayer (> 2 players): The game continues!
        # If it was the quitting player's turn, advance turn and trigger AI if needed
        if game["turn_idx"] == p_idx:
            advance_turn(game, bonus_turn=False)
            execute_ai_turn_if_needed(game_id)
        return {
            "success": True,
            "game_over": False,
            "message": f"🚪 {quitter['name']} left the match. Game continues with {len(active_players)} players!"
        }

def execute_ai_turn_if_needed(game_id: str) -> List[str]:
    """Executes AI turns automatically with heuristic decision making."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game or game["status"] != "playing":
        return []
        
    steps_executed = []
    max_consecutive_ai_turns = 12
    ai_turns = 0
    
    while ai_turns < max_consecutive_ai_turns:
        curr = game["players"][game["turn_idx"]]
        if not curr["is_ai"] or game["status"] != "playing":
            break
            
        ai_turns += 1
        roll_res = roll_ludo_dice(game_id, curr["id"])
        roll = roll_res.get("roll", 1)
        
        if roll_res.get("auto_moved") or roll_res.get("turn_passed"):
            steps_executed.append(f"{curr['name']} rolled {roll}")
            continue
            
        if game["awaiting_pawn_choice"]:
            # Pick best move with strategic heuristic
            movable = game["movable_pawns"]
            best_pawn = movable[0]
            best_score = -999
            
            for p_id in movable:
                pawn = curr["pawns"][p_id]
                score = 0
                if pawn["state"] == "yard" and roll == 6:
                    score += 60 # Leaving yard is very valuable
                elif pawn["state"] == "track":
                    new_pos = (pawn["pos"] + roll) % game["circuit_len"]
                    # Check capture
                    if new_pos not in game["safe_stars"]:
                        for opp_idx, opp in enumerate(game["players"]):
                            if opp_idx != game["turn_idx"]:
                                for op in opp["pawns"]:
                                    if op["state"] == "track" and op["pos"] == new_pos:
                                        score += 150 # Massive reward for capture!
                    if new_pos in game["safe_stars"]:
                        score += 45 # Landing on star is safe
                    score += pawn["steps_traveled"] # Advance furthest pawn
                elif pawn["state"] == "home":
                    if pawn["pos"] + roll == 5:
                        score += 120 # Reaching Goal!
                    else:
                        score += 30
                        
                if score > best_score:
                    best_score = score
                    best_pawn = p_id
                    
            move_res = move_ludo_pawn(game_id, curr["id"], best_pawn)
            steps_executed.append(f"{curr['name']} rolled {roll} & moved Pawn {best_pawn + 1}")
            
    return steps_executed

def render_ludo_view(game_id: str) -> Tuple[str, List[List[Dict[str, str]]]]:
    """Generates the Telegram message text and inline button keyboard for the Ludo match."""
    game = _ACTIVE_LUDO_GAMES.get(game_id)
    if not game:
        return "❌ <b>Ludo Game Expired or Not Found.</b>", []
        
    num = game["num_players"]
    status = game["status"]
    
    if status == "lobby":
        curr_count = len(game["players"])
        text = (
            f"🎲 <b>ORDINAL LUDO MULTIPLAYER ARENA</b> 🎲\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Capacity:</b> {curr_count}/{num} Players\n"
            f"⚔️ <b>Stakes:</b> Top finishes earn Sparks & Diya Blessings!\n\n"
            f"<b>Roster:</b>\n"
        )
        for i, p in enumerate(game["players"]):
            bot_tag = " [BOT]" if p["is_ai"] else ""
            text += f"{p['color_emoji']} <b>{p['color_name']}:</b> {html.escape(p['name'])}{bot_tag}\n"
            
        for slot in range(curr_count, num):
            color_idx = game["color_indices"][slot]
            text += f"{LUDO_COLORS[color_idx]['emoji']} <b>{LUDO_COLORS[color_idx]['name']}:</b> <i>[Open Seat]</i>\n"
            
        text += (
            f"\n<i>Click below to join or fill remaining seats with AI to begin!</i>"
        )
        
        keyboard = []
        if curr_count < num:
            keyboard.append([{"text": f"⚔️ Join Match ({curr_count}/{num})", "callback_data": f"ludo_join:{game_id}"}])
            keyboard.append([{"text": "🤖 Fill with AI & Start", "callback_data": f"ludo_ai:{game_id}"}])
        else:
            keyboard.append([{"text": "🚀 Launch Game Now!", "callback_data": f"ludo_start:{game_id}"}])
            
        keyboard.append([{"text": "🚪 Leave Lobby", "callback_data": f"ludo_exit:{game_id}"}])
        return text, keyboard
        
    # Active Game or Finished
    curr_player = game["players"][game["turn_idx"]]
    recent_logs = "\n".join(game["logs"][-6:]) if game["logs"] else "Game initialized."
    
    text = (
        f"🎲 <b>ORDINAL LUDO SHOWDOWN ({num} Players)</b> 🎲\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    if status == "finished":
        text += "🏁 <b>MATCH COMPLETED! FINAL PODIUM:</b>\n"
        for p in sorted(game["players"], key=lambda x: x["rank"] if x["rank"] else 99):
            resigned_tag = " <i>(Forfeited)</i>" if p.get("resigned", False) else ""
            rank_str = f"#{p['rank']}" if p["rank"] else "DNF"
            text += f"{p['color_emoji']} <b>{rank_str} - {html.escape(p['name'])}</b>{resigned_tag}\n"
        text += f"\n🏆 Rewards distributed to all participants!\n\n"
        text += f"<i>Recent action:</i>\n{recent_logs}"
        return text, [[{"text": "🔄 Play New Game", "callback_data": "ludo_new"}]]

    text += f"🎯 <b>Turn:</b> {curr_player['color_emoji']} <b>{html.escape(curr_player['name'])}</b>"
    if game["last_roll"]:
        text += f" (Rolled: 🎲 <b>{game['last_roll']}</b>)\n"
    else:
        text += " (Awaiting Roll)\n"
        
    text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    text += "<b>Pawns Status:</b>\n"
    for p in game["players"]:
        if p.get("resigned", False):
            text += f"{p['color_emoji']} <s>{html.escape(p['name'])}</s>: <i>[Forfeited]</i>\n"
            continue
        pawn_summary = []
        for pw in p["pawns"]:
            st = pw["state"]
            if st == "yard":
                pawn_summary.append("🏠Base")
            elif st == "track":
                pawn_summary.append(f"📍{pw['pos']}")
            elif st == "home":
                pawn_summary.append(f"🌈H{pw['pos']+1}")
            elif st == "goal":
                pawn_summary.append("🏆Goal")
        summary_str = " | ".join(pawn_summary)
        is_turn = " 👈" if p["id"] == curr_player["id"] else ""
        text += f"{p['color_emoji']} <b>{html.escape(p['name'])}:</b> [{summary_str}]{is_turn}\n"
        
    text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📜 <i>Log:</i>\n{recent_logs}\n"
    
    keyboard = []
    if not game["awaiting_pawn_choice"]:
        keyboard.append([{"text": f"🎲 Roll Dice ({curr_player['name']})", "callback_data": f"ludo_roll:{game_id}"}])
    else:
        pawn_buttons = []
        for p_id in game["movable_pawns"]:
            pw = curr_player["pawns"][p_id]
            desc = "Exit Base" if pw["state"] == "yard" else f"Pawn {p_id+1}"
            pawn_buttons.append({"text": f"{curr_player['color_emoji']} {desc}", "callback_data": f"ludo_move:{game_id}:{p_id}"})
        # Arrange in rows of 2
        for i in range(0, len(pawn_buttons), 2):
            keyboard.append(pawn_buttons[i:i+2])
            
    keyboard.append([
        {"text": "🔄 Refresh Board", "callback_data": f"ludo_refresh:{game_id}"},
        {"text": "🚪 Quit / Exit Match", "callback_data": f"ludo_exit:{game_id}"}
    ])
    return text, keyboard
