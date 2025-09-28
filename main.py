#!/usr/bin/env python3
import sys
import re
import random
import chess

import os
import sys
import time

import viewer

import json
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer

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
    s = s.replace(" to ", " ")
    s = s.replace("->", " ")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", "", s) # miče razmake
    return s

def parse_move(board: chess.Board, raw: str) -> chess.Move | None:
    """
        Prihvaća poteze u formatima:
      - e2 to e4
      - e2 e4
      - e2e4
      - e7e8q (promotion in UCI format) (q, r, b, n). UCI format je ono e2e4, e7e8q itd. za razliku od SAN koji je Nf3
    """
    text = normalize_move_text(raw)
    try:
        move = chess.Move.from_uci(text)
    except ValueError:
        return None
    return move if move in board.legal_moves else None

"""ovo koristim da ne moram threadati pygame event loop, nego samo povremeno pumpam, pygame handla eventove"""
"""bio je probllem na Windowsima gdje se window znao zamrznuti ako se ne pumpa event loop"""
"""Python’s built-in input() blocks everything until Enter is pressed."""
def input_pumped(prompt: str) -> str:
    print(prompt, end="", flush=True)
    buf = []
    if os.name == "nt": # Windows path
        import msvcrt
        while True:
            viewer.pump() # window movable/closable
            if msvcrt.kbhit():
                ch = msvcrt.getwch()  # wide char supports arrows/backspace etc.
                if ch in ("\r", "\n"): # If Enter is pressed → stop input, return the typed string.
                    print()
                    return "".join(buf)
                elif ch == "\b":       # backspace
                    if buf:
                        buf.pop() # If Backspace is pressed → remove last char from buf and visually erase it in the console.
                        print("\b \b", end="", flush=True)
                else:
                    buf.append(ch) # Any normal key → add it to the buffer and display it.
                    print(ch, end="", flush=True)
            time.sleep(0.01)
    # POSIX path (Linux/macOS)
    else:
        import select
        while True:
            viewer.pump()
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                line = sys.stdin.readline()
                # echo is already printed by terminal when you type
                return line.rstrip("\n")

def choose_side():
    while True:
        side = input_pumped("Choose side: [w]hite / [b]lack / [r]andom: ").strip().lower()
        if side in ("w", "b", "r"):
            break
        print("Please enter w, b, or r.")
    if side == "r":
        side = random.choice(["w", "b"])
        print(f"Random chose: {side.upper()}")
    return side == "w"

def input_move(board: chess.Board) -> chess.Move | None:
    while True:
        s = input_pumped(
            "Your move ('e2 to e4','e2 e4','e7e8q' (q,r,b,n), 'help', 'quit') — press Enter to speak: "
        ).strip().lower()

        # Empty input ili voice > slušaj mikofon
        if s == "" or s == "voice":
            vm = voice_move_once(board)
            if vm is None:
                # just loop again
                continue
            if vm == "help":
                print("Say moves like 'e two to e four' or 'e seven to e eight queen'.")
                continue
            if vm == "quit":
                return None
            return vm  # chess.Move

        if s in ("q", "quit", "exit", "resign"):
            return None
        if s in ("h", "help"):
            print("Format examples: 'e2 to e4', 'e2 e4', 'e2e4', 'e7e8q' (q,r,b,n). Type 'quit' to exit.")
            print("You can also press Enter with no text and speak your move.")
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

# VOSK CONFIG 
## OVO MOŽDA PREBACITI U POSEBNU SKRIPTU
""" kad stisnemo ENTER zove voice_move_once(), capture pocinje odmah i sluša do timeouta ili dok se ne prepozna nešto, ne stisnut ENTER da završi
nego prestaje slušati kad model prepozna kraj(nema govora) ili kad istekne timeout"""

MODEL_DIR = "models/vosk-model-small-en-us-0.15"  # model za engleski, mali (50MB)
SAMPLE_RATE = 16000

# grammar za improvanje prepoznavanja šahovskih poteza
def _grammar_words():
    files = ["a","b","c","d","e","f","g","h"]
    ranks = ["one","two","three","four","five","six","seven","eight","1","2","3","4","5","6","7","8"]
    squares_spoken = [f"{f} {r}" for f in files for r in ranks] + [f"{f}{r}" for f in files for r in "12345678"]
    keywords = [
        "to", "quit", "exit", "resign", "help",
        "queen", "rook", "bishop", "knight",
        # common misreads you might say:
        "q","r","b","n"
    ]
    return squares_spoken + keywords

def _ensure_vosk_model():
    try:
        return Model(MODEL_DIR)
    except Exception as e:
        print(f"[Vosk] Could not load model at '{MODEL_DIR}'. {e}")
        print("Make sure you downloaded and unzipped a Vosk model and set MODEL_DIR.")
        return None

def _words_to_digit(w: str) -> str:
    m = {
        "one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7","eight":"8",
        # common misreads you might say:
        "tree":"3","free":"3","for":"4","ate":"8"
    }
    return m.get(w, w)

# _spoken_square_to_algebraic
# -----------------------------------------------
# Ideja:
#   Pretvara izgovoreno/zapisano polje u standardni algebarski oblik "e2".
#
# Prima:
#   tok (str) – polje u raznim oblicima: "e2", "e 2", "e two", "e-two", "e.two".
#
# Radi:
#   1) Normalizira razmake i interpunkciju (zamijeni '-' i '.' razmakom, trim, lower).
#   2) Ako je oblik "<slovo> <broj/riječ-broja>" (npr. "e two"),
#      koristi _words_to_digit("two") -> "2" i vrati "e2" ako je 1–8.
#   3) Ako je kompaktni oblik "e2", vrati ga direktno.
#
# Vraća:
#   "e2" (str) ako je prepoznato valjano polje; inače None.
def _spoken_square_to_algebraic(tok: str) -> str | None:
    # Accept "e2", "e 2", "e two"
    tok = tok.strip().lower()
    tok = tok.replace("-", " ").replace(".", " ")
    parts = tok.split()
    if len(parts) == 2 and parts[0] in "abcdefgh":
        f = parts[0]
        r = _words_to_digit(parts[1])
        if r in "12345678":
            return f + r
    # compact form like 'e2'
    if len(tok) == 2 and tok[0] in "abcdefgh" and tok[1] in "12345678":
        return tok
    return None

# _normalize_spoken_move
# -----------------------------------------------
# Ideja:
#   Pretvara izgovoreni potez u UCI string (npr. "e2e4" ili "e7e8q").
#   Rješava više varijanti izgovora i tipične krive prepoznavanja STT-a:
#   - "e two to e four"  -> "e2e4"
#   - "e two e four"     -> "e2e4"  (bez "to")
#   - "e two two e four" -> "e2e4"  (drugi "two" tretira kao "to")
#   - Promocije: dodaje "q/r/b/n" ("queen/rook/bishop/knight")
#   - Kontrole: "help", "quit/resign/exit"
#
# Prima:
#   text (str) – cijela izgovorena rečenica za potez.
#
# Radi:
#   1) Normalizira tekst (mala slova, razmaci, točke/crtice).
#   2) Rani izlaz za kontrole ("quit"/"help").
#   3) Definira skupove: file (a–h), riječi/brojevi za rankove, mape promocija.
#   4) Pokušaj A: Ako rečenica počinje kao "<file> <rank>" (npr. "e two"),
#      uzmi to kao izvorno polje, preskoči sve "connectore" (to/two/too/2/tu),
#      pa parsiraj odredište i eventualnu promociju.
#   5) Pokušaj B (fallbackovi):
#      - Split po "to": "e2 to e4" / "e two to e four"
#      - 2/3 tokena: "e2 e4" (+opcijska promocija)
#      - 4/5 tokena: "e two e four" (+opcijska promocija)
#
# Vraća:
#   UCI potez "e2e4" ili s promocijom "e7e8q";
#   "quit"/"help" za kontrole; None ako se ne može pouzdano parsirati.

def _normalize_spoken_move(text: str) -> str | None:
    """
    Converts spoken text to a UCI-like string:
      "e two to e four"           -> "e2e4"
      "e two e four"              -> "e2e4"
      "e two two e four"          -> "e2e4"   (extra 'two' misheard for 'to')
      "e seven to e eight queen"  -> "e7e8q"
    Also supports: "help", "quit/resign/exit"
    """
    t = text.lower().strip()
    t = t.replace("-", " ").replace(".", " ")
    tokens = t.split()

    if any(w in t for w in ["quit","resign","exit"]):
        return "quit"
    if "help" in t:
        return "help"

    files = set("abcdefgh")
    rank_words = {"one","two","three","four","five","six","seven","eight",
                  "1","2","3","4","5","6","7","8"}
    promo_words = {"queen":"q","rook":"r","bishop":"b","knight":"n","q":"q","r":"r","b":"b","n":"n"}
    def is_connector(w: str) -> bool:
        # common "to" homophones from STT
        return w in {"to","two","too","2","tu"}

    # --- Case A: starts like <file> <rank> ... (e two ...)
    src = dst = None
    promo = None

    if len(tokens) >= 2 and tokens[0] in files and tokens[1] in rank_words:
        # parse source square from first two tokens
        src = _spoken_square_to_algebraic(tokens[0] + " " + tokens[1])
        i = 2
        # skip one or more connector tokens ("to", "two", "too", "2")
        while i < len(tokens) and is_connector(tokens[i]):
            i += 1

        # the rest should describe the destination (and maybe promotion)
        # Try pattern: <file> <rank> [promo]
        if i + 1 < len(tokens):
            dst_try = _spoken_square_to_algebraic(tokens[i] + " " + tokens[i+1])
            if dst_try:
                dst = dst_try
                j = i + 2
                # optional promotion word at end
                if j < len(tokens) and tokens[j] in promo_words:
                    promo = tokens[j]
            else:
                # Try compact single token like "e4"
                dst_try2 = _spoken_square_to_algebraic(tokens[i])
                if dst_try2:
                    dst = dst_try2
                    j = i + 1
                    if j < len(tokens) and tokens[j] in promo_words:
                        promo = tokens[j]

    # --- Case B: didn’t match the leading pattern; handle other common forms
    if src is None or dst is None:
        # 1) Explicit "to" (handles "e2 to e4" and "e two to e four")
        left_right = re.split(r"\bto\b", t)
        if len(left_right) == 2:
            left, right = left_right[0].strip(), left_right[1].strip()
            # promotion may be last token of right
            right_parts = right.split()
            if right_parts and right_parts[-1] in promo_words:
                promo = right_parts[-1]
                right = " ".join(right_parts[:-1]).strip()
            src = _spoken_square_to_algebraic(left)
            dst = _spoken_square_to_algebraic(right)

        # 2) Two/three tokens: "e2 e4" or "e two e four" or promotion at end
        if src is None or dst is None:
            parts = tokens
            if len(parts) in (2,3):
                src = _spoken_square_to_algebraic(parts[0])
                dst = _spoken_square_to_algebraic(parts[1]) if len(parts) >= 2 else None
                if len(parts) == 3 and parts[2] in promo_words:
                    promo = parts[2]
            # 3) Four/five tokens: "e two e four" [+ promo]
            elif len(parts) in (4,5):
                src = _spoken_square_to_algebraic(parts[0] + " " + parts[1])
                dst = _spoken_square_to_algebraic(parts[2] + " " + parts[3])
                if len(parts) == 5 and parts[4] in promo_words:
                    promo = parts[4]

    if not src or not dst:
        return None

    if promo:
        p = promo_words[promo]
        return f"{src}{dst}{p}"
    return f"{src}{dst}"


def transcribe_once(timeout_sec: float = 6.0) -> str | None:
    """
    Listens once and returns final recognized text, or None on failure/timeouts.
    Uses a constrained grammar for chess vocabulary.
    """
    model = _ensure_vosk_model()
    if model is None:
        return None

    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(_grammar_words()))
    q = queue.Queue()

    def _callback(indata, frames, time_info, status):
        if status:
            # you can print(status) for debugging the audio callback
            pass
        q.put(bytes(indata))

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
                               channels=1, callback=_callback):
            sd.default.samplerate = SAMPLE_RATE
            sd.default.channels = 1

            import time as _time
            deadline = _time.time() + timeout_sec
            partial_last_print = 0.0

            while _time.time() < deadline:
                try:
                    data = q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if rec.AcceptWaveform(data):
                    j = json.loads(rec.Result())
                    text = j.get("text", "").strip()
                    return text if text else None
                else:
                    # Optional: show partials every ~1s
                    now = _time.time()
                    if now - partial_last_print > 1.0:
                        pj = json.loads(rec.PartialResult())
                        partial = pj.get("partial", "")
                        if partial:
                            print(f"[hearing]: {partial}")
                        partial_last_print = now

            # timeout, take final best guess if any
            j = json.loads(rec.FinalResult())
            text = j.get("text", "").strip()
            return text if text else None
    except Exception as e:
        print(f"[Vosk] Audio error: {e}")
        return None

def voice_move_once(board: chess.Board) -> chess.Move | str | None:
    """
    Returns:
      - chess.Move  -> a parsed legal move
      - "quit" / "help" strings for control commands
      - None if nothing usable was heard
    """
    print("🎤 Speak your move (e.g., 'e two to e four', or 'e seven to e eight queen')...")
    heard = transcribe_once(timeout_sec=7.0)
    if not heard:
        print("Didn't catch that.")
        return None

    print(f"You said: {heard}")
    norm = _normalize_spoken_move(heard)
    if norm == "quit":
        return "quit"
    if norm == "help":
        return "help"
    if not norm:
        print("Couldn't interpret speech into a move.")
        return None

    move = parse_move(board, norm)
    if move is None:
        print("Parsed your speech but the move is illegal in this position.")
        return None
    return move

def main():
    print("Voice Chess)")
    board = chess.Board()
    human_is_white = choose_side()

    viewer.configure(figures_dir="figures", tile=80)
    viewer.init()
    viewer.pump()
    viewer.render(board)

    print_board(board)
    if human_is_white:
        print("You are White. You move first.")
    else:
        print("You are Black. Bot moves first.")

    while not board.is_game_over():
        # drži prozor responzivnim dok čeka input
        viewer.pump()

        human_turn = (board.turn == chess.WHITE) == human_is_white
        if human_turn:
            move = input_move(board)
            if move is None:
                print("You resigned / quit. Bye!")
                viewer.close()
                sys.exit(0)
            human_san = board.san(move) # ovo je zapis koji se koristi u šahu (npr. Nf3, e4, O-O, exd5) samo za debugging, nepotrebno je
            board.push(move)
            print(f"You played: {move.uci()} ({human_san})")
            print_board(board)
            viewer.pump(); viewer.render(board)
        else:
            bot_move = random_bot_move(board) ## PLACEHOLDER FOR BOT MOVE
            bot_san = board.san(bot_move)
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
