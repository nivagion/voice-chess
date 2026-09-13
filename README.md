# Voice-Controlled Physical Chess Robot

<!-- Add project photo/GIF here -->

A Raspberry Pi chess system that turns spoken moves into physical board movement. The application recognizes English move commands offline, validates them against the current game, asks Stockfish for the opponent's response, and drives a two-axis carriage and electromagnet to move the real pieces.

The repository separates chess rules, speech recognition, visualization, geometry, motion planning, and GPIO access so that the physical planner can be tested without energizing hardware.

## Demo

A photo or short video of the assembled robot should be added here. The repository currently contains chess-piece sprites for the software viewer, but no media showing the physical system.

## Current Status

This is an active hardware prototype, not a finished consumer product.

- **Implemented:** offline English speech recognition, legal-move validation, Stockfish responses, the software board viewer, fake and Raspberry Pi hardware drivers, lane-based movement planning, ordinary captures, and hardware-free movement tests.
- **In development:** calibration and repeatability testing on the assembled mechanism, physical edge-case validation, recovery procedures, and demo documentation.
- **Planned:** physical castling, en passant and promotion sequences, closed-loop homing or position feedback, and a recorded end-to-end hardware demo.

## Features

- Offline, always-on speech recognition with Vosk and a constrained chess vocabulary
- Spoken move normalization into UCI notation, followed by legality checks with `python-chess`
- Stockfish integration with ten selectable difficulty levels and a random legal-move fallback
- Pygame board visualization with last-move highlighting and physical-movement status
- Raspberry Pi GPIO driver for two stepper control channels and an electromagnet
- Test double for safe development of the movement pipeline without physical hardware
- Deterministic lane-based routes that carry pieces between, rather than across, occupied square centers
- Capture handling that moves the captured piece to a reserved graveyard slot before moving the attacker
- Separate horizontal and vertical steps-per-square calibration
- Safety behavior that pauses microphone input during movement and leaves it paused after a motion error

## How It Works

```text
Voice input
    -> Vosk speech recognition
    -> spoken phrase to UCI move parsing
    -> python-chess legality validation
    -> Stockfish opponent selection
    -> physical movement planner
    -> stepper motors and electromagnet
```

`main.py` owns the game loop. A move is committed to the in-memory board only after the physical movement completes successfully. If the configured Stockfish executable cannot be found, the application explicitly warns and falls back to a random legal move.

## System Architecture

- `always_on_voice.py` runs Vosk recognition in a background thread and exposes pause/resume controls.
- `main.py` normalizes speech, validates moves, coordinates turns, and updates the viewer.
- `bot_engine.py` wraps Stockfish through the `python-chess` UCI engine API.
- `physical_geometry.py` maps chess squares and graveyard slots to carriage coordinates and motor steps.
- `physical_movement.py` plans piece operations, executes them, tracks carriage state, and coordinates recovery behavior.
- `physical_hardware.py` provides real GPIO and fake in-memory drivers behind the same interface.
- `viewer.py` renders the logical board and movement status with Pygame.

## Hardware

The implementation targets a Raspberry Pi connected to:

- two direction/stepper control channels for the XY carriage
- an electromagnet for picking up pieces
- a microphone for spoken commands
- a display for the optional Pygame board view

BCM pin assignments, pulse timing, and calibration values live in `physical_config.py`. Pin assignments should be reviewed against the assembled electronics before running on hardware.

## Physical Movement System

Board square centers and the graveyard columns are represented on a half-square coordinate grid. Odd coordinates form lanes between square centers. When carrying a piece, the planner moves from the source center into an adjacent lane, travels through the lane network, and enters the destination center only for placement. Magnet-off carriage travel uses a predictable horizontal-then-vertical route.

The executor tracks the last known carriage position. A failed motor segment marks the position as unknown, forces the magnet off, and blocks further automatic movement until the operator restores the board and carriage manually.

## Capture Handling

Each piece color has 16 deterministic graveyard positions outside the board. For a normal capture, the planner:

1. reserves the next graveyard slot,
2. removes the captured piece,
3. deposits it in that slot,
4. moves the attacking piece to the destination square.

The reservation is released if execution fails before the captured piece is deposited. Castling, en passant, and physical promotion are deliberately rejected because their multi-piece or replacement sequences are not implemented yet.

## Calibration

`physical_config.py` is the single source of truth for square size, horizontal and vertical steps per square, pulse timing, GPIO pins, and startup states. `calibrate_square_movement.py` is an interactive Raspberry Pi utility for moving exactly one square per key press, stopping motion, toggling the magnet, and reviewing calibration values.

Calibration controls real hardware and must be run manually on the robot. A typical recalculation is:

```text
new_steps = old_steps * target_distance_cm / measured_distance_cm
```

## Software Stack

- Python 3.10+
- Vosk and `sounddevice`
- `python-chess`
- Stockfish
- Pygame
- `gpiozero` and Raspberry Pi `pinctrl`

## Project Structure

```text
main.py                         Game loop and move parsing
always_on_voice.py              Background Vosk listener
bot_engine.py                   Stockfish adapter and difficulty mapping
physical_config.py              GPIO, timing, and calibration values
physical_geometry.py            Board coordinates and lane-path planning
physical_hardware.py            Real and fake hardware drivers
physical_movement.py            Capture planning, execution, and safety state
calibrate_square_movement.py    Manual hardware calibration utility
viewer.py                       Pygame board visualization
tests/                          Hardware-free movement tests
figures/                        Viewer piece sprites
models/                         Offline Vosk model files
```

## Setup

Create a virtual environment and install the Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install python-chess sounddevice vosk pygame gpiozero evdev
```

On Windows, activate the environment with `.venv\Scripts\activate`. Raspberry Pi audio and GPIO packages may also require system libraries appropriate to the OS image.

Install Stockfish through the operating system or place its executable in one of the paths searched by `bot_engine.py`:

```text
engines/windows/stockfish.exe
engines/linux/stockfish
engines/arm64/stockfish
```

Alternatively, set `STOCKFISH_PATH` to an executable file.

## Running

For hardware-free development, explicitly select the fake driver:

```bash
VOICE_CHESS_FAKE_HARDWARE=1 python main.py
```

On the Raspberry Pi, after verifying wiring and calibration, run `python main.py` without that variable to use the GPIO driver. The program asks for a side and Stockfish difficulty, then listens for commands such as `pawn e two to e four`.

Do not run `main.py` or the calibration utility on connected hardware until the pin assignments, carriage origin, emergency-stop procedure, and magnet polarity have been checked.

## Limitations

- Physical execution currently supports ordinary legal moves and ordinary captures only.
- Castling, en passant, and physical piece replacement for promotion are recognized but rejected.
- The lane planner is deterministic and does not perform global obstacle detection.
- Carriage position is tracked in software; there is no closed-loop position feedback in the current code.
- Recovery after partial movement requires the operator to restore the physical board and re-center the carriage.
- Speech commands and the bundled recognition grammar are English-only.
- Hardware operation and calibration require manual testing on the assembled robot.

## Future Work

- Add safe physical sequences for castling, en passant, and promotion.
- Add homing or position sensors for closed-loop recovery.
- Validate movement paths against physical piece dimensions and edge cases on the assembled board.
- Add a recorded hardware demo and assembly documentation.

## Thesis / Academic Context

This project was developed as an academic physical-computing system combining speech interaction, chess software, motion planning, and embedded hardware. Related thesis material and hardware photographs are maintained separately from the runtime code.
