# Voice Chess project instructions

## Project

This project runs on a Raspberry Pi and controls a voice-operated physical
chessboard.

The project may include:

- speech recognition
- python-chess
- pygame
- Stockfish
- stepper motors
- an electromagnet
- Raspberry Pi GPIO
- physical chess-piece movement

## General rules

- Inspect the existing code before making changes.
- Preserve existing working behaviour unless explicitly asked to change it.
- Make small, focused changes rather than rewriting entire files.
- Explain the planned changes before editing.
- Do not rename or move files unless necessary.
- Do not install or remove dependencies without asking.
- Do not commit, push, rebase, reset, or change Git branches.
- After making changes, summarize every changed file.

## Hardware safety

- Never automatically run programs that control motors, GPIO pins,
  electromagnets, microphones, speakers, or other physical hardware.
- Never energize the electromagnet automatically.
- Never move motors automatically.
- Never change GPIO pin assignments unless explicitly requested.
- Never use sudo unless explicitly approved.
- Hardware programs must be tested manually by the user.

## Testing

Safe automatic checks include:

- Python syntax checking
- importing modules when doing so does not initialize hardware
- running existing unit tests that do not control hardware
- `python -m compileall`

Do not run `main.py`, motor-control scripts, magnet-control scripts, or GPIO
scripts unless explicitly approved.

## Implementation style

- Use the project's existing architecture and coding style.
- Prefer clear Python code over unnecessary abstraction.
- Add error handling where hardware or external processes can fail.
- Keep hardware control separate from chess logic when possible.
- Do not remove working features while implementing a new feature.
- Show the Git diff after completing a task.
