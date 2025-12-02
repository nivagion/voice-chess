#!/usr/bin/env python3
import os
import re
import sys
import time
import random
import chess

import viewer
from always_on_voice import AlwaysOnVoiceListener


def print_board(board: chess.Board):
    print("\n  a b c d e f g h")
    rows = str(board).split("\n")
    for i, row in enumerate(rows):
        print(f"{8 - i} {row} {8 - i}")
    print("  a b c d e f g h\n")


def normalize_move_text(s: str) -> str:
    # Normalizira tekst poteza u čisti UCI format (uklanja razmake, "to", strelice, crtice, velika slova)
    s = s.strip().lower()
    s = s.replace(" to ", " ")
    s = s.replace("->", " ")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", "", s)
    return s


def parse_move(board: chess.Board, raw: str) -> chess.Move | None:
    # Pokušava parsirati tekst poteza u chess.Move i provjerava je li potez legalan u trenutnoj poziciji
    text = normalize_move_text(raw)
    try:
        move = chess.Move.from_uci(text)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


# ---- "pumped" input (konzolni unos koji usput održava viewer responzivnim) ----
def input_pumped(prompt: str) -> str:
    print(prompt, end="", flush=True)
    buf = []
    if os.name == "nt":
        import msvcrt
        while True:
            viewer.pump()  # osvježava prozor ploče i evente
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    print()
                    return "".join(buf)
                elif ch == "\b":
                    if buf:
                        buf.pop()
                        print("\b \b", end="", flush=True)
                else:
                    buf.append(ch)
                    print(ch, end="", flush=True)
            time.sleep(0.01)
    else:
        import select
        while True:
            viewer.pump()
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                line = sys.stdin.readline()
                return line.rstrip("\n")


def choose_side():
    # U konzoli pita igrača želi li igrati bijelim, crnim ili nasumično odabranim bojama
    while True:
        side = input_pumped("Choose side: [w]hite / [b]lack / [r]andom: ").strip().lower()
        if side in ("w", "b", "r"):
            break
        print("Please enter w, b, or r.")
    if side == "r":
        side = random.choice(["w", "b"])
        print(f"Random chose: {side.upper()}")
    return side == "w"


# ---- normalizator izgovorenog poteza (speech -> UCI string) ----
def _normalize_spoken_move(text: str) -> str | None:
    """
    Primjeri:
      "pawn e two to e four"        -> "e2e4"
      "rook a one a eight"          -> "a1a8"
      "e seven to e eight queen"    -> "e7e8q"

    Vraća:
      - "quit"  ako se prepozna naredba za prekid (quit / resign / exit)
      - "help"  ako se prepozna zahtjev za pomoć
      - "e2e4" / "e7e8q" ... za poteze
      - None    ako se ne može ispravno parsirati
    """
    t = (
        text.lower()
            .strip()
            .replace("-", " ")
            .replace(".", " ")
    )
    tokens = t.split()

    if not tokens:
        return None

    # ----- kontrolne riječi (prekid, pomoć, itd.) -----
    if any(w in tokens for w in ("quit", "resign", "exit")):
        return "quit"
    if "help" in tokens:
        return "help"

    # ----- makni riječi za figure + "filer" riječi tipa "from", "the" itd. -----
    PIECE_WORDS = {"pawn", "rook", "knight", "bishop", "queen", "king", "piece"}
    FILLER = {"on", "from", "to", "the", "my", "your", "at"}
    tokens = [w for w in tokens if w not in PIECE_WORDS and w not in FILLER]

    files = set("abcdefgh")
    rank_words = {
        "one", "two", "three", "four", "five", "six", "seven", "eight",
        "1", "2", "3", "4", "5", "6", "7", "8",
    }
    promo_words = {
        "queen": "q", "rook": "r", "bishop": "b", "knight": "n",
        "q": "q", "r": "r", "b": "b", "n": "n",
    }

    # dozvoli neke uobičajene krivo prepoznate brojeve
    def words_to_digit(w: str) -> str:
        m = {
            "one": "1",
            "two": "2", "too": "2", "to": "2",
            "three": "3", "tree": "3", "free": "3",
            "four": "4", "for": "4",
            "five": "5",
            "six": "6",
            "seven": "7",
            "eight": "8", "ate": "8",
        }
        return m.get(w, w)

    def is_connector(w: str) -> bool:
        # tretiramo samo "to"/"two"/"too"/"2" kao riječi koje povezuju početno i završno polje
        return w in {"to", "two", "too", "2"}

    def spoken_square_to_alg(words: list[str]) -> str | None:
        """
        Prihvaća:
          ["e", "two"]  -> "e2"
          ["e2"]        -> "e2"
        """
        if not words:
            return None

        # kompaktni oblik npr. "e2"
        if len(words) == 1 and len(words[0]) == 2:
            f, r = words[0][0], words[0][1]
            if f in files and r in "12345678":
                return words[0]

        # razdvojeni oblik npr. ["e", "two"]
        if len(words) >= 2 and words[0] in files and words[1] in rank_words:
            r = words_to_digit(words[1])
            if r in "12345678":
                return words[0] + r

        return None

    src = dst = None
    promo = None
    n = len(tokens)

    # ---------- Strategija 1: početak oblika "e two ..." ---------- 
    i = 0
    if n >= 2 and tokens[0] in files and tokens[1] in rank_words:
        src = spoken_square_to_alg(tokens[0:2])
        i = 2

        # preskoči konektore ("to", "two", ...)
        while i < n and is_connector(tokens[i]):
            i += 1

        # odredi odredišno polje, može biti u split ili compact obliku
        if i + 1 < n:
            dst_candidate = spoken_square_to_alg(tokens[i:i+2])
            if dst_candidate:
                dst = dst_candidate
                i += 2
            else:
                dst_candidate = spoken_square_to_alg(tokens[i:i+1])
                if dst_candidate:
                    dst = dst_candidate
                    i += 1

        # provjeri ima li riječi za promociju na kraju
        if i < n and tokens[i] in promo_words:
            promo = tokens[i]

    # ---------- Strategija 2: razdvajanje po riječi "to" ----------
    if src is None or dst is None:
        joined = " ".join(tokens)
        left_right = re.split(r"\bto\b", joined)
        if len(left_right) == 2:
            left = left_right[0].strip()
            right = left_right[1].strip()
            right_parts = right.split()

            # promocija na kraju desne strane?
            if right_parts and right_parts[-1] in promo_words:
                promo = right_parts[-1]
                right_parts = right_parts[:-1]

            src = spoken_square_to_alg(left.split())
            dst = spoken_square_to_alg(right_parts)

    # ---------- Strategija 3: jednostavni uzorci ----------
    if src is None or dst is None:
        parts = tokens

        # e2 e4 / e2 e4 q
        if len(parts) in (2, 3):
            src = spoken_square_to_alg(parts[0:1])
            dst = spoken_square_to_alg(parts[1:2])
            if len(parts) == 3 and parts[2] in promo_words:
                promo = parts[2]

        # e two e four / e two e four queen
        elif len(parts) in (4, 5):
            src = spoken_square_to_alg(parts[0:2])
            dst = spoken_square_to_alg(parts[2:4])
            if len(parts) == 5 and parts[4] in promo_words:
                promo = parts[4]

    if not src or not dst:
        return None

    if promo:
        return f"{src}{dst}{promo_words[promo]}"
    return f"{src}{dst}"


def wait_for_voice_move(board: chess.Board, voice: AlwaysOnVoiceListener) -> chess.Move | None:
    # Glavna petlja za čekanje glasovnog poteza: čita tekst iz AlwaysOnVoiceListener-a,
    # normalizira ga, provjerava kontrolne naredbe (quit/help) i vraća legalni potez.
    print("Say: 'pawn e two to e four' (or 'help', 'quit').")
    while True:
        viewer.pump()
        text = voice.get_text_nowait()
        if not text:
            time.sleep(0.01)
            continue

        print(f"You said: {text}")
        norm = _normalize_spoken_move(text)

        # ---- quit / resign / exit → glasovna potvrda ----
        if norm == "quit":
            print("Say 'yes' to confirm resign and quit, or 'no' to continue.")
            confirm_deadline = time.time() + 7.0
            while time.time() < confirm_deadline:
                viewer.pump()
                reply = voice.get_text_nowait()
                if not reply:
                    time.sleep(0.05)
                    continue
                print(f"You said (confirm): {reply}")
                low = reply.lower()
                if any(w in low.split() for w in ("yes", "yeah", "yep")):
                    return None
                if any(w in low.split() for w in ("no", "cancel", "continue")):
                    print("Okay, continuing. Say a move like 'pawn e two to e four'.")
                    break
            # ako istekne vrijeme ili korisnik kaže "no" → nastavi slušati poteze
            continue

        # ---- pomoć ili neuspješno parsiranje ----
        if norm == "help" or norm is None:
            print("Say moves like 'pawn e two to e four' or 'e seven to e eight queen'.")
            continue

        # ---- pokušaj parsirati kao šahovski potez ----
        move = parse_move(board, norm)
        if move:
            return move

        print("Parsed speech, but move is illegal in this position. Try again.")


def random_bot_move(board: chess.Board) -> chess.Move:
    # Vrati nasumično odabran legalan potez za bota
    return random.choice(list(board.legal_moves))


def announce_result(board: chess.Board):
    # Na temelju završnog stanja ploče ispiše kako je partija završila
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
        print("Draw by fifty-move rule.")
    elif outcome.termination == chess.Termination.THREEFOLD_REPETITION:
        print("Draw by threefold repetition.")
    else:
        print(f"Game over: {outcome.termination}")


def main():
    # Glavni ulaz u program: postavlja ploču, viewer, glasovni sustav i glavnu game-loop petlju
    print("Voice Chess)")
    board = chess.Board()
    human_is_white = choose_side()

    viewer.configure(figures_dir="figures", tile=80)
    viewer.init()
    viewer.pump()
    viewer.render(board)

    # Always-on mic (VOSK model za engleski)
    MODEL_DIR = "models/vosk-model-small-en-us-0.15"
    SAMPLE_RATE = 16000
    voice = AlwaysOnVoiceListener(MODEL_DIR, sample_rate=SAMPLE_RATE, move_window=5.0, verbose=True)
    voice.start()

    try:
        print_board(board)
        if human_is_white:
            print("You are White. You move first.")
        else:
            print("You are Black. Bot moves first.")

        # Glavna petlja partije: izmjena poteza čovjek ↔ bot dok igra ne završi
        while not board.is_game_over():
            viewer.pump()
            human_turn = (board.turn == chess.WHITE) == human_is_white
            if human_turn:
                # Čekaj potez preko mikrofona
                move = wait_for_voice_move(board, voice)
                if move is None:
                    print("You resigned / quit. Bye!")
                    viewer.close()
                    sys.exit(0)
                human_san = board.san(move)
                board.push(move)
                print(f"You played: {move.uci()} ({human_san})")
                print_board(board)
                viewer.pump()
                viewer.render(board)
            else:
                # Bot odigra nasumičan legalan potez
                bot_move = random_bot_move(board)
                bot_san = board.san(bot_move)
                board.push(bot_move)
                print(f"Bot played:  {bot_move.uci()} ({bot_san})")
                print_board(board)
                viewer.pump()
                viewer.render(board)
    finally:
        # Na izlazu pokušaj uredno zaustaviti glasovni thread i audio stream
        try:
            voice.stop()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        viewer.close()
        print("\nInterrupted. Goodbye!")
