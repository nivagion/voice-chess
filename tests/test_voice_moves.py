from io import StringIO
import unittest
from unittest.mock import patch

import chess

from main import wait_for_voice_move


class FakeVoice:
    def __init__(self, *phrases):
        self.phrases = iter(phrases)
        self.calls = 0

    def get_text_nowait(self):
        self.calls += 1
        return next(self.phrases)


class VoiceMoveTests(unittest.TestCase):
    def test_legal_move_in_check_needs_no_confirmation(self):
        board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        self.assertTrue(board.is_check())
        voice = FakeVoice("king e one to e two")
        with patch("main.viewer.pump"), patch("sys.stdout", new_callable=StringIO) as output:
            move = wait_for_voice_move(board, voice)
        self.assertEqual(move, chess.Move.from_uci("e1e2"))
        self.assertEqual(voice.calls, 1)
        self.assertNotIn("Quit game?", output.getvalue())

    def test_legal_pinned_piece_move_needs_no_confirmation(self):
        board = chess.Board("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        voice = FakeVoice("rook e two to e three")
        with patch("main.viewer.pump"), patch("sys.stdout", new_callable=StringIO) as output:
            move = wait_for_voice_move(board, voice)
        self.assertEqual(move, chess.Move.from_uci("e2e3"))
        self.assertEqual(voice.calls, 1)
        self.assertNotIn("Quit game?", output.getvalue())

    def test_stray_quit_word_does_not_confirm_a_legal_move(self):
        board = chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1")
        voice = FakeVoice("king e one to e two quit")
        with patch("main.viewer.pump"):
            move = wait_for_voice_move(board, voice)
        self.assertEqual(move, chess.Move.from_uci("e1e2"))
        self.assertEqual(voice.calls, 1)

    def test_stray_standalone_quit_is_ignored(self):
        voice = FakeVoice("quit", "pawn e two to e four")
        with patch("main.viewer.pump"), patch("sys.stdout", new_callable=StringIO) as output:
            move = wait_for_voice_move(chess.Board(), voice)
        self.assertEqual(move, chess.Move.from_uci("e2e4"))
        self.assertEqual(voice.calls, 2)
        self.assertNotIn("(confirm)", output.getvalue())

    def test_explicit_quit_requires_yes_or_confirm(self):
        for response in ("yes", "confirm"):
            with self.subTest(response=response):
                voice = FakeVoice("quit game", response)
                with patch("main.viewer.pump"), patch("sys.stdout", new_callable=StringIO) as output:
                    move = wait_for_voice_move(chess.Board(), voice)
                self.assertIsNone(move)
                self.assertEqual(voice.calls, 2)
                self.assertIn("Quit game?", output.getvalue())

    def test_cancel_quit_returns_to_move_input(self):
        voice = FakeVoice("quit game", "no", "pawn e two to e four")
        with patch("main.viewer.pump"), patch("sys.stdout", new_callable=StringIO) as output:
            move = wait_for_voice_move(chess.Board(), voice)
        self.assertEqual(move, chess.Move.from_uci("e2e4"))
        self.assertEqual(voice.calls, 3)
        self.assertIn("Okay, continuing.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
