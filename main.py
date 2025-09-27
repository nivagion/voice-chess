#!/usr/bin/env python3
import sys
import re
import random
import chess

# 👇 add this import (make sure viewer.py is next to this file)
import viewer


def choose_side():
    while True:
        side = input("Choose side: [w]hite / [b]lack / [r]andom: ").strip().lower()
        if side in ("w", "b", "r"):
            break
        print("Please enter w, b, or r.")
    if side == "r":
        side = random.choice(["w", "b"])
        print(f"Random chose: {side.upper()}")
    return side == "w"  # ako je covjek bijeli, vrati True


def print_board(board: chess.Board):  # printa ploču s obrubom (oznake redova i stupaca)
    print("\n  a b c d e f g h")
    rows = str(board).split("\n")
    for i, row in enumerate(rows):
        print(f"{8 - i} {row} {8 - i}")
    print("  a b c d e f g h\n")


def normalize_move_text(s: str) -> str:
    s = s.strip().lower()
    # Normalize connectors
    s = s.replace(" to ", " ")
    s = s.replace("->", " ")
    s = s.replace("-", " ")
    # Collapse all spaces
    s = re.sub(r"\s+", "", s)
    return s


def parse_move(board: chess.Board, raw: str) -> chess.Move | None:
    """
    Accepts:
      - e2 to e4
      - e2 e4
      - e2e4
      - e7e8q (promotion in UCI format) (q, r, b, n).
    """
    text = normalize_move_text(raw)
    try:
        move = chess.Move.from_uci(text)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def input_move(board: chess.Board) -> chess.Move | None:
    while True:
        s = input("Your move ('e2 to e4','e2 e4', 'e7e8q' (q,r,b,n), 'help', 'quit'): ").strip().lower()
        if s in ("q", "quit", "exit", "resign"):
            return None
        if s in ("h", "help"):
            print("Format examples: 'e2 to e4', 'e2 e4', 'e2e4', 'e7e8q' (q,r,b,n). Type 'quit' to exit.")
            continue
        move = parse_move(board, s)
        if move is not None:
            return move
        print("Couldn't parse or illegal in this position. Try again.")


def random_bot_move(board: chess.Board) -> chess.Move:
    return random.choice(list(board.legal_moves))


def announce_result(board: chess.Board):
    outcome = board.outcome()
    if outcome is None:
        print("Game over.")
        return
    if outcome.termination == chess.Termination.CHECKMATE:
        winner = "White" if outcome.winner else "Black"
        print(f"Checkmate! {winner} wins.")
    elif outcome.termination == chess.Termination.STALEMATE:
        print("Draw by stalemate.")
    elif outcome.termination == chess.Termination.INSUFFICIENT_MATERIAL:
        print("Draw by insufficient material.")
    elif outcome.termination == chess.Termination.FIFTY_MOVES:
        print("Draw by fifty-move rule.")
    elif outcome.termination == chess.Termination.THREEFOLD_REPETITION:
        print("Draw by threefold repetition.")
    else:
        print(f"Game over: {outcome.termination}")


def main():
    print("Voice Chess)")
    board = chess.Board()
    human_is_white = choose_side()

    # === init the visual viewer (PNG pieces expected in ./figures) ===
    viewer.configure(figures_dir="figures", tile=80)  # optional overrides
    viewer.init()                 # no-op if pygame/assets missing
    viewer.pump()
    viewer.render(board)

    print_board(board)
    if human_is_white:
        print("You are White. You move first.")
    else:
        print("You are Black. Bot moves first.")

    while not board.is_game_over():
        # keep window responsive while waiting for input
        viewer.pump()

        human_turn = (board.turn == chess.WHITE) == human_is_white
        if human_turn:
            # Human turn
            move = input_move(board)
            if move is None:
                print("You resigned / quit. Bye!")
                viewer.close()
                sys.exit(0)
            human_san = board.san(move)  # <-- before push
            board.push(move)
            print(f"You played: {move.uci()} ({human_san})")
            print_board(board)
            viewer.pump(); viewer.render(board)
        else:
            # Bot turn
            bot_move = random_bot_move(board)
            bot_san = board.san(bot_move)  # <-- before push
            board.push(bot_move)
            print(f"Bot played:  {bot_move.uci()} ({bot_san})")
            print_board(board)
            viewer.pump(); viewer.render(board)

    announce_result(board)
    viewer.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        viewer.close()
        print("\nInterrupted. Goodbye!")
