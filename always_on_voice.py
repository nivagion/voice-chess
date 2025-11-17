import json
import queue
import threading
import time
from typing import Optional, List

import sounddevice as sd
from vosk import Model, KaldiRecognizer


def squares_grammar_words() -> List[str]:
    files = ["a", "b", "c", "d", "e", "f", "g", "h"]
    ranks_words = [
        "one", "two", "three", "four", "five", "six", "seven", "eight",
        "1", "2", "3", "4", "5", "6", "7", "8",
    ]
    squares_spoken = [f"{f} {r}" for f in files for r in ranks_words]
    squares_compact = [f"{f}{r}" for f in files for r in "12345678"]
    return squares_spoken + squares_compact


PIECE_WORDS = ["pawn", "rook", "knight", "bishop", "queen", "king"]
PROMO_WORDS = ["queen", "rook", "bishop", "knight", "q", "r", "b", "n"]
CONTROL_WORDS = [
    "help", "quit", "exit", "resign", "cancel",
    "yes", "no", "yeah", "yep", "continue",
]


class AlwaysOnVoiceListener:
    """
    Simple always-on mic:
      - Single grammar with squares + piece words + control words.
      - Emits full recognized phrases via get_text_nowait().
      - Prints partials if verbose=True.
    """

    def __init__(self, model_dir: str, sample_rate: int = 16000,
                 move_window: float = 5.0, verbose: bool = True) -> None:
        self.model = Model(model_dir)
        self.sample_rate = sample_rate
        self.move_window = move_window  # unused but kept for compatibility
        self.verbose = verbose

        self._audio_q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._out_q: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.RawInputStream] = None

        self._rec = self._make_recognizer()

    def _make_recognizer(self) -> KaldiRecognizer:
        phrases = (
            squares_grammar_words()
            + ["to", "two", "too", "2"]
            + PROMO_WORDS
            + PIECE_WORDS
            + CONTROL_WORDS
        )
        return KaldiRecognizer(self.model, self.sample_rate, json.dumps(phrases))

    # ----- public API -----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _callback(indata, frames, time_info, status):
            try:
                self._audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=_callback,
        )
        self._stream.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._proc_loop, daemon=True)
        self._thread.start()
        if self.verbose:
            print("[Voice] Mic started. Say a move like 'pawn e two to e four'.")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._thread = None
        self._stream = None

    def get_text_nowait(self) -> Optional[str]:
        try:
            return self._out_q.get_nowait()
        except queue.Empty:
            return None

    def _emit(self, text: str) -> None:
        if text:
            self._out_q.put(text)

    def _proc_loop(self) -> None:
        last_partial_print = 0.0
        while not self._stop.is_set():
            try:
                data = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if self._rec.AcceptWaveform(data):
                j = json.loads(self._rec.Result())
                text = j.get("text", "").strip()
                if text:
                    if self.verbose:
                        print(f"[heard] {text}")
                    self._emit(text)
            else:
                pj = json.loads(self._rec.PartialResult())
                partial = pj.get("partial", "").strip()
                now = time.time()
                if self.verbose and partial and now - last_partial_print > 0.8:
                    print(f"[hearing] {partial}")
                    last_partial_print = now
