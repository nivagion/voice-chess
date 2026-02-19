#!/usr/bin/env python3
import os
import shutil
from dataclasses import dataclass

import chess
import chess.engine

import sys

def _clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


# Rough mapping you asked for (1..10 -> ~Elo target)
# Note: UCI_Elo is an engine calibration target, not “real” FIDE Elo. :contentReference[oaicite:6]{index=6}
DIFFICULTY_ELO_MAP = {
    1: 800,
    2: 978,
    3: 1156,
    4: 1333,
    5: 1511,
    6: 1689,
    7: 1867,
    8: 2044,
    9: 2222,
    10: 2400,
}


def difficulty_to_elo(level_1_to_10: int) -> int:
    lvl = _clamp(level_1_to_10, 1, 10)
    return DIFFICULTY_ELO_MAP[lvl]


def difficulty_to_skill(level_1_to_10: int) -> int:
    # Stockfish Skill Level is 0..20 :contentReference[oaicite:7]{index=7}
    lvl = _clamp(level_1_to_10, 1, 10)
    return int(round((lvl - 1) * 20 / 9))


def difficulty_to_think_time(level_1_to_10: int) -> float:
    # Keep small so it feels responsive
    lvl = _clamp(level_1_to_10, 1, 10)
    t_min, t_max = 0.05, 0.80
    return float(t_min + (lvl - 1) * (t_max - t_min) / 9)


def print_difficulty_table() -> None:
    print("Bot difficulty mapping (rough):")
    for d in range(1, 11):
        print(f"  {d}: ~{DIFFICULTY_ELO_MAP[d]} Elo target")


def find_stockfish_path() -> str | None:
    env = os.getenv("STOCKFISH_PATH")
    if env and os.path.isfile(env):
        return env

    here = os.path.dirname(__file__)

    # pick subfolder by platform
    if os.name == "nt":
        candidates = [os.path.join(here, "engines", "windows", "stockfish.exe")]
    elif sys.platform == "linux":
        # you can refine this later for arm64 detection if you want
        candidates = [
            os.path.join(here, "engines", "linux", "stockfish"),
            os.path.join(here, "engines", "arm64", "stockfish"),
        ]
    else:
        candidates = [os.path.join(here, "engines", "linux", "stockfish")]

    for p in candidates:
        if os.path.isfile(p):
            return p

    return shutil.which("stockfish")


@dataclass
class StockfishBotConfig:
    level: int = 5
    threads: int = 1
    hash_mb: int = 64


class StockfishBot:
    """
    Wraps Stockfish via python-chess UCI engine API. :contentReference[oaicite:8]{index=8}
    Uses UCI_LimitStrength + UCI_Elo (overrides Skill Level when enabled). :contentReference[oaicite:9]{index=9}
    """
    def __init__(self, engine_path: str, cfg: StockfishBotConfig):
        self.engine_path = engine_path
        self.cfg = cfg
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.think_time = 0.1
        self.set_difficulty(cfg.level)

    def set_difficulty(self, level_1_to_10: int) -> None:
        lvl = _clamp(level_1_to_10, 1, 10)
        self.cfg.level = lvl

        elo = difficulty_to_elo(lvl)
        skill = difficulty_to_skill(lvl)
        self.think_time = difficulty_to_think_time(lvl)

        opts: dict[str, int | bool] = {}

        # Light settings (good for Pi too)
        if "Threads" in self.engine.options:
            opts["Threads"] = int(_clamp(self.cfg.threads, 1, 32))
        if "Hash" in self.engine.options:
            opts["Hash"] = int(_clamp(self.cfg.hash_mb, 16, 1024))

        # Strength limiting:
        has_limit = "UCI_LimitStrength" in self.engine.options
        has_elo   = "UCI_Elo" in self.engine.options

        if has_limit and has_elo:
            elo_opt = self.engine.options["UCI_Elo"]
            min_elo = int(elo_opt.min)
            max_elo = int(elo_opt.max)

            if elo < min_elo:
                # This Stockfish build can't go that low -> use Skill Level instead
                opts["UCI_LimitStrength"] = False
            else:
                opts["UCI_LimitStrength"] = True
                opts["UCI_Elo"] = int(_clamp(elo, min_elo, max_elo))

        # Also set Skill Level if present (won’t matter if LimitStrength overrides) :contentReference[oaicite:11]{index=11}
        if "Skill Level" in self.engine.options:
            opts["Skill Level"] = int(_clamp(skill, 0, 20))

        if opts:
            self.engine.configure(opts)

    def choose_move(self, board: chess.Board) -> chess.Move:
        result = self.engine.play(board, chess.engine.Limit(time=self.think_time))
        if result.move is None:
            raise RuntimeError("Engine returned no move.")
        return result.move

    def close(self) -> None:
        try:
            self.engine.quit()
        except Exception:
            pass
