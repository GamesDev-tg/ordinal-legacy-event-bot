import unittest
import time
from app.database import get_db_connection, init_db
from app.ludo_engine import (
    create_ludo_game, join_ludo_game, fill_ludo_with_ai, start_ludo_game,
    roll_ludo_dice, move_ludo_pawn, execute_ai_turn_if_needed,
    get_movable_pawns, apply_pawn_move, render_ludo_view,
    get_track_config, get_color_sequence
)
from app.arcade_engine import (
    start_c4_game, play_c4_turn, _check_c4_win, render_c4_view,
    start_2048_game, move_2048, render_2048_view,
    start_wordle_game, submit_wordle_guess, render_wordle_view
)
from app.game_engine import start_game_session, finish_game_session

class TestLudoAndNewGames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.u1 = 88112233
        self.u2 = 88112244
        conn = get_db_connection()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks) VALUES (?, ?, ?, ?, ?, ?)",
                (self.u1, "ludo_tester1", "Tester1", 1, 100, 10)
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name, gharana_id, points_total, diya_wicks) VALUES (?, ?, ?, ?, ?, ?)",
                (self.u2, "ludo_tester2", "Tester2", 2, 50, 10)
            )
        conn.close()

    def test_ludo_configurations_2_to_8_players(self):
        """Verify color sequences and track configs for 2, 4, 6, and 8 players."""
        # 2 players (opposite colors: Red vs Yellow)
        c2 = get_color_sequence(2)
        self.assertEqual(len(c2), 2)
        self.assertEqual(c2, [0, 2])
        circuit2, starts2, home2, safe2 = get_track_config(2)
        self.assertEqual(circuit2, 52)

        # 4 players
        c4 = get_color_sequence(4)
        self.assertEqual(len(c4), 4)
        self.assertEqual(c4, [0, 1, 2, 3])
        circuit4, starts4, home4, safe4 = get_track_config(4)
        self.assertEqual(circuit4, 52)

        # 6 players
        c6 = get_color_sequence(6)
        self.assertEqual(len(c6), 6)
        circuit6, starts6, home6, safe6 = get_track_config(6)
        self.assertEqual(circuit6, 80)
        self.assertEqual(len(safe6), 16)

        # 8 players
        c8 = get_color_sequence(8)
        self.assertEqual(len(c8), 8)
        circuit8, starts8, home8, safe8 = get_track_config(8)
        self.assertEqual(circuit8, 80)
        self.assertEqual(len(starts8), 8)

    def test_ludo_lobby_creation_and_ai_fill(self):
        """Test creating a 4-player lobby and filling empty spots with AI bots."""
        game = create_ludo_game(self.u1, "Tester1", num_players=4)
        self.assertEqual(game["status"], "lobby")
        self.assertEqual(len(game["players"]), 1)

        # Tester 2 joins
        ok, msg = join_ludo_game(game["id"], self.u2, "Tester2")
        self.assertTrue(ok)
        self.assertEqual(len(game["players"]), 2)

        # Fill remaining with AI
        ok_ai, msg_ai = fill_ludo_with_ai(game["id"])
        self.assertTrue(ok_ai)
        self.assertEqual(len(game["players"]), 4)
        self.assertEqual(game["status"], "playing")
        self.assertTrue(game["players"][2]["is_ai"])
        self.assertTrue(game["players"][3]["is_ai"])

    def test_ludo_move_mechanics_and_capture(self):
        """Verify pawn entering board on 6, moving forward, and capture logic."""
        game = create_ludo_game(self.u1, "Tester1", num_players=2)
        fill_ludo_with_ai(game["id"])
        self.assertEqual(game["status"], "playing")

        # Player 0 roll non-6: no movable pawns
        movable = get_movable_pawns(game, 0, roll=3)
        self.assertEqual(len(movable), 0)

        # Player 0 roll 6: all 4 pawns can enter
        movable6 = get_movable_pawns(game, 0, roll=6)
        self.assertEqual(len(movable6), 4)

        # Apply entry for pawn 0
        res = apply_pawn_move(game, 0, 0, roll=6)
        self.assertTrue(res["success"])
        pawn0 = game["players"][0]["pawns"][0]
        self.assertEqual(pawn0["state"], "track")
        self.assertEqual(pawn0["pos"], 0) # Red starts at 0

        # Move pawn forward 5 steps
        res2 = apply_pawn_move(game, 0, 0, roll=5)
        self.assertEqual(pawn0["pos"], 5)

        # Opponent (Yellow) enters board at 26
        game["players"][1]["pawns"][0]["state"] = "track"
        game["players"][1]["pawns"][0]["pos"] = 9
        # Red is at 5, rolls 4 -> lands on 9 -> captures Yellow!
        res_cap = apply_pawn_move(game, 0, 0, roll=4)
        self.assertTrue(res_cap["captured"])
        self.assertEqual(pawn0["pos"], 9)
        self.assertEqual(game["players"][1]["pawns"][0]["state"], "yard")

    def test_ludo_render_view(self):
        """Verify Telegram markdown message and inline keyboard generation."""
        game = create_ludo_game(self.u1, "Tester1", num_players=4)
        txt, kb = render_ludo_view(game["id"])
        self.assertIn("ORDINAL LUDO MULTIPLAYER ARENA", txt)
        self.assertTrue(len(kb) >= 1)

    def test_connect4_gameplay_and_win(self):
        """Test Connect 4 dropping pieces and 4-in-a-row horizontal win."""
        c4 = start_c4_game(self.u1, "Tester1", self.u2, "Tester2")
        self.assertEqual(c4["status"], "playing")

        # Drop 3 pieces for P1 in cols 0, 1, 2
        play_c4_turn(c4["id"], self.u1, 0)
        play_c4_turn(c4["id"], self.u2, 0) # P2 blocks row above or elsewhere
        play_c4_turn(c4["id"], self.u1, 1)
        play_c4_turn(c4["id"], self.u2, 1)
        play_c4_turn(c4["id"], self.u1, 2)
        play_c4_turn(c4["id"], self.u2, 2)

        # P1 plays col 3 to complete horizontal 4-in-a-row (0, 1, 2, 3)
        res_win = play_c4_turn(c4["id"], self.u1, 3)
        self.assertTrue(res_win["game_over"])
        self.assertEqual(res_win["winner"], 1)
        self.assertEqual(c4["status"], "finished")

        # Check render view
        txt, kb = render_c4_view(c4["id"])
        self.assertIn("CONNECTED 4", txt)

    def test_connect4_pvp_reply_and_lobby(self):
        """Test Connect 4 PvP targeting another user (reply/mention) and open lobby join."""
        from app.arcade_engine import start_c4_game, join_c4_game, switch_c4_to_ai

        # 1. Direct PvP (when replying to a user)
        c4_pvp = start_c4_game(p1_id=self.u1, p1_name="Challenger", p2_id=self.u2, p2_name="Opponent", is_vs_ai=False)
        self.assertFalse(c4_pvp["is_vs_ai"])
        self.assertEqual(c4_pvp["p1_id"], self.u1)
        self.assertEqual(c4_pvp["p2_id"], self.u2)
        self.assertEqual(c4_pvp["p2_name"], "Opponent")
        self.assertEqual(c4_pvp["status"], "playing")

        # P1 plays col 0
        res1 = play_c4_turn(c4_pvp["id"], self.u1, 0)
        self.assertTrue(res1["success"])
        self.assertEqual(c4_pvp["turn"], 2)
        # Verify AI didn't take a turn: column 0 has only 1 piece
        pieces_in_col0 = sum(1 for r in range(6) if c4_pvp["board"][r][0] != 0)
        self.assertEqual(pieces_in_col0, 1)

        # Non-turn player cannot move
        bad_turn = play_c4_turn(c4_pvp["id"], self.u1, 1)
        self.assertFalse(bad_turn["success"])

        # P2 plays col 0
        res2 = play_c4_turn(c4_pvp["id"], self.u2, 0)
        self.assertTrue(res2["success"])
        self.assertEqual(c4_pvp["turn"], 1)

        # 2. Open Lobby (waiting for opponent in group)
        c4_lobby = start_c4_game(p1_id=self.u1, p1_name="Challenger", is_vs_ai=False)
        self.assertEqual(c4_lobby["status"], "lobby")
        self.assertIsNone(c4_lobby["p2_id"])

        # P2 joins
        ok, msg = join_c4_game(c4_lobby["id"], self.u2, "JoiningPlayer")
        self.assertTrue(ok)
        self.assertEqual(c4_lobby["status"], "playing")
        self.assertEqual(c4_lobby["p2_id"], self.u2)
        self.assertFalse(c4_lobby["is_vs_ai"])

    def test_game_2048_mechanics(self):
        """Test 2048 sliding, tile merging, and view generation."""
        g = start_2048_game(self.u1)
        self.assertEqual(len(g["board"]), 4)
        # Force a mergeable row: [2, 2, 0, 0]
        g["board"][0] = [2, 2, 0, 0]
        res = move_2048(self.u1, "left")
        self.assertTrue(res["success"])
        self.assertTrue(res["changed"])
        self.assertEqual(g["board"][0][0], 4)
        self.assertEqual(g["score"], 4)

        txt, kb = render_2048_view(self.u1)
        self.assertIn("2048 SATOSHIS ARCADE", txt)
        self.assertTrue(len(kb) >= 3)

    def test_wordle_game_mechanics(self):
        """Test 5-letter crypto Wordle guess feedback and win condition."""
        w = start_wordle_game(self.u1)
        w["secret"] = "BLOCK"

        # Guess "BRICK"
        res = submit_wordle_guess(self.u1, "BRICK")
        self.assertTrue(res["success"])
        self.assertEqual(res["result"], "continue")
        # 'B' and 'K' should be green
        self.assertTrue(res["pattern"].startswith("🟩"))
        self.assertTrue(res["pattern"].endswith("🟩"))

        # Guess exact secret "BLOCK"
        res_win = submit_wordle_guess(self.u1, "BLOCK")
        self.assertTrue(res_win["success"])
        self.assertEqual(res_win["result"], "won")
        self.assertEqual(res_win["pattern"], "🟩🟩🟩🟩🟩")
        self.assertEqual(w["status"], "won")

        txt, kb = render_wordle_view(self.u1)
        self.assertIn("GENIUS! YOU SOLVED IT", txt)

    def test_database_game_sessions_constraint_expanded(self):
        """Verify database accepts game_type 4 (Ludo), 5 (Connect 4), 6 (2048), 7 (Wordle)."""
        session_ludo = start_game_session(self.u1, 4)
        self.assertIn("session_id", session_ludo)
        self.assertIn("nonce", session_ludo)

        session_c4 = start_game_session(self.u1, 5)
        self.assertIn("session_id", session_c4)

        session_2048 = start_game_session(self.u1, 6)
        self.assertIn("session_id", session_2048)

        session_wordle = start_game_session(self.u1, 7)
        self.assertIn("session_id", session_wordle)

        # Complete session with score 3 and duration >= 3000ms
        finish_res = finish_game_session(
            self.u1,
            session_ludo["session_id"],
            session_ludo["nonce"],
            raw_score=3,
            duration_ms=4500
        )
        self.assertTrue(finish_res["success"])
        self.assertIn(finish_res["points_awarded"], (3, 6))

if __name__ == "__main__":
    unittest.main()
