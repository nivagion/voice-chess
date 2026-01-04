import json
import queue
import threading
import time
from typing import Optional, List

import sounddevice as sd
from vosk import Model, KaldiRecognizer


def squares_grammar_words() -> List[str]:
    files = ["a","b","c","d","e","f","g","h"]
    ranks_words = ["one","two","three","four","five","six","seven","eight"]
    return [f"{f} {r}" for f in files for r in ranks_words]


PIECE_WORDS = ["pawn", "rook", "knight", "bishop", "queen", "king"]
PROMO_WORDS = ["queen", "rook", "bishop", "knight", "q", "r", "b", "n"]
CONTROL_WORDS = [
    "help", "quit", "exit", "resign", "cancel",
    "yes", "no", "yeah", "yep", "continue",
]


class AlwaysOnVoiceListener:
    """
    Jednostavan "always-on" slušatelj mikrofona:
      - Koristi jednu gramatičku listu (polja, figure, kontrolne riječi).
      - Emitsa kompletne prepoznate fraze preko get_text_nowait().
      - Ispisuje djelomične rezultate (partial) ako je verbose=True.
    """

    def __init__(self, model_dir: str, sample_rate: int = 16000,
                 move_window: float = 5.0, verbose: bool = True) -> None:
        # Učitavanje VOSK modela i inicijalna konfiguracija
        self.model = Model(model_dir)
        self.sample_rate = sample_rate
        self.move_window = move_window  # trenutno se ne koristi, ostavljeno za kompatibilnost
        self.verbose = verbose

        self._audio_q: "queue.Queue[bytes]" = queue.Queue(maxsize=64)  # bafer za audio blokove iz callbacka
        self._out_q: "queue.Queue[str]" = queue.Queue()                # bafer za prepoznati tekst
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.RawInputStream] = None

        self._rec = self._make_recognizer()

    def _make_recognizer(self) -> KaldiRecognizer:
        # Kreira KaldiRecognizer s listom dozvoljenih fraza (gramatika) za poboljšanje prepoznavanja
        phrases = (
            squares_grammar_words()
            + ["to", "two", "too"]
            + PROMO_WORDS
            + PIECE_WORDS
            + CONTROL_WORDS
        )
        return KaldiRecognizer(self.model, self.sample_rate, json.dumps(phrases))

    # ----- javni API -----
    def start(self) -> None:
        # Pokreće audio stream i pozadinski thread koji procesa audio i šalje tekst u _out_q
        if self._thread and self._thread.is_alive():
            return

        def _callback(indata, frames, time_info, status):
            # Audio callback: dobiveni blok zvuka se stavlja u red
            try:
                self._audio_q.put_nowait(bytes(indata))
            except queue.Full:
                # ako je red pun, jednostavno odbaci najnoviji blok
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
        # Zaustavlja pozadinski thread i audio stream
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._thread = None
        self._stream = None

    def get_text_nowait(self) -> Optional[str]:
        # Ne-blokirajuće dohvaćanje sljedeće prepoznate fraze (ili None ako nema ništa)
        try:
            return self._out_q.get_nowait()
        except queue.Empty:
            return None

    def _emit(self, text: str) -> None:
        # Stavlja kompletno prepoznati tekst u izlazni red
        if text:
            self._out_q.put(text)

    def _proc_loop(self) -> None:
        # Glavna petlja u pozadinskom threadu: čita audio blokove, šalje ih u VOSK i obrađuje rezultate
        last_partial_print = 0.0
        while not self._stop.is_set():
            try:
                data = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if self._rec.AcceptWaveform(data):
                # Kad je prepoznata cijela fraza, Result() vraća konačan tekst
                j = json.loads(self._rec.Result())
                text = j.get("text", "").strip()
                if text:
                    if self.verbose:
                        print(f"[heard] {text}")
                    self._emit(text)
            else:
                # Inače koristimo PartialResult za djelomične (trenutno slušane) fraze
                pj = json.loads(self._rec.PartialResult())
                partial = pj.get("partial", "").strip()
                now = time.time()
                if self.verbose and partial and now - last_partial_print > 0.8:
                    print(f"[hearing] {partial}")
                    last_partial_print = now
