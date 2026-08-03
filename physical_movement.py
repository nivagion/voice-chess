"""Move classification, planning, transactional execution, and state tracking."""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import chess

from physical_geometry import (
    START_POSITION,
    Point,
    Segment,
    board_square_center,
    graveyard_center,
    plan_carriage_path,
    plan_carried_path,
)
from physical_hardware import HardwareDriver


class MovementState(enum.Enum):
    LISTENING = "LISTENING"
    MOVE_RECOGNIZED = "MOVE_RECOGNIZED"
    PLANNING = "PLANNING"
    MOVING = "MOVING"
    MOVE_COMPLETE = "MOVE_COMPLETE"
    ERROR = "ERROR"


class UnsupportedPhysicalMove(ValueError):
    pass


class PausableListener(Protocol):
    def pause(self) -> None: ...
    def resume(self) -> None: ...


@dataclass(frozen=True)
class GraveyardReservation:
    color: chess.Color
    point: Point


class GraveyardManager:
    """Tracks 16 deterministic slots for each captured-piece color."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._occupied: dict[chess.Color, dict[Point, chess.Piece | None]] = {
            chess.WHITE: {point: None for point in self._ordered_points(chess.WHITE)},
            chess.BLACK: {point: None for point in self._ordered_points(chess.BLACK)},
        }
        self._reserved: set[Point] = set()

    @staticmethod
    def _ordered_points(color: chess.Color) -> tuple[Point, ...]:
        columns = (1, 0) if color == chess.WHITE else (10, 11)
        return tuple(graveyard_center(column, rank) for column in columns for rank in range(8))

    def reserve(self, color: chess.Color) -> GraveyardReservation:
        for point, piece in self._occupied[color].items():
            if piece is None and point not in self._reserved:
                self._reserved.add(point)
                return GraveyardReservation(color, point)
        raise RuntimeError(f"No free {'white' if color else 'black'} graveyard slot")

    def commit(self, reservation: GraveyardReservation, piece: chess.Piece) -> None:
        if reservation.point not in self._reserved:
            raise RuntimeError("Graveyard slot is not reserved")
        if self._occupied[reservation.color][reservation.point] is not None:
            raise RuntimeError("Graveyard slot is already occupied")
        self._occupied[reservation.color][reservation.point] = piece
        self._reserved.remove(reservation.point)

    def release(self, reservation: GraveyardReservation) -> None:
        self._reserved.discard(reservation.point)

    def occupied_points(self, color: chess.Color) -> tuple[Point, ...]:
        return tuple(point for point, piece in self._occupied[color].items() if piece is not None)


@dataclass(frozen=True)
class PieceOperation:
    source: Point
    destination: Point
    carried_segments: tuple[Segment, ...]
    description: str


@dataclass(frozen=True)
class PhysicalMovePlan:
    move: chess.Move
    operations: tuple[PieceOperation, ...]
    captured_piece: chess.Piece | None = None
    graveyard_reservation: GraveyardReservation | None = None


@dataclass
class CarriageState:
    position: Point = START_POSITION
    position_known: bool = True
    magnet_on: bool = False

    def reset_to_board_center(self) -> None:
        """Reset software tracking only after manual physical repositioning."""
        self.position = START_POSITION
        self.position_known = True
        self.magnet_on = False


@dataclass
class ExecutionFailure(RuntimeError):
    message: str
    operation_index: int
    segment_index: int | None
    last_known_position: Point
    position_known: bool

    def __str__(self) -> str:
        segment = "before carried path" if self.segment_index is None else f"at segment {self.segment_index}"
        return f"{self.message}; operation {self.operation_index + 1}, {segment}, last position {self.last_known_position.display()}"


def plan_physical_move(
    board: chess.Board,
    move: chess.Move,
    graveyard: GraveyardManager,
) -> PhysicalMovePlan:
    if move not in board.legal_moves:
        raise ValueError(f"Move is not legal in the current position: {move.uci()}")
    if board.is_castling(move):
        raise UnsupportedPhysicalMove("Castling is recognized but physical execution is not implemented yet.")
    if board.is_en_passant(move):
        raise UnsupportedPhysicalMove("En passant is recognized but physical execution is not implemented yet.")
    if move.promotion is not None:
        raise UnsupportedPhysicalMove("Promotion is recognized but physical execution is not implemented yet.")

    source = board_square_center(chess.square_name(move.from_square))
    destination = board_square_center(chess.square_name(move.to_square))
    attacker = PieceOperation(source, destination, plan_carried_path(source, destination), "move attacking piece")

    if not board.is_capture(move):
        return PhysicalMovePlan(move, (attacker,))

    captured_piece = board.piece_at(move.to_square)
    if captured_piece is None:
        raise ValueError("Capture target has no piece")
    reservation = graveyard.reserve(captured_piece.color)
    captured = PieceOperation(
        destination,
        reservation.point,
        plan_carried_path(destination, reservation.point),
        "remove captured piece",
    )
    return PhysicalMovePlan(move, (captured, attacker), captured_piece, reservation)


class PhysicalMoveExecutor:
    def __init__(self, hardware: HardwareDriver, carriage: CarriageState | None = None) -> None:
        self.hardware = hardware
        self.carriage = carriage or CarriageState()

    def _move_segment(self, segment: Segment, operation_index: int, segment_index: int | None) -> None:
        try:
            self.hardware.move(segment)
        except BaseException as exc:
            # Without feedback, a failed segment may have moved partially.
            self.carriage.position_known = False
            raise ExecutionFailure(
                str(exc), operation_index, segment_index,
                self.carriage.position, self.carriage.position_known,
            ) from exc
        self.carriage.position = segment.end

    def execute(self, plan: PhysicalMovePlan, graveyard: GraveyardManager) -> None:
        if not self.carriage.position_known:
            self.hardware.magnet_off()
            self.carriage.magnet_on = False
            raise RuntimeError("Carriage position is unknown; manually reset it before moving")

        deposited_capture = False
        try:
            for operation_index, operation in enumerate(plan.operations):
                for segment in plan_carriage_path(self.carriage.position, operation.source):
                    self._move_segment(segment, operation_index, None)

                self.hardware.magnet_on()
                self.carriage.magnet_on = True
                for segment_index, segment in enumerate(operation.carried_segments):
                    self._move_segment(segment, operation_index, segment_index)
                self.hardware.magnet_off()
                self.carriage.magnet_on = False

                if operation_index == 0 and plan.graveyard_reservation is not None:
                    graveyard.commit(plan.graveyard_reservation, plan.captured_piece)
                    deposited_capture = True
        except BaseException:
            try:
                self.hardware.magnet_off()
            finally:
                self.carriage.magnet_on = False
            if plan.graveyard_reservation is not None and not deposited_capture:
                graveyard.release(plan.graveyard_reservation)
            raise
        finally:
            if self.carriage.magnet_on:
                try:
                    self.hardware.magnet_off()
                finally:
                    self.carriage.magnet_on = False


class PhysicalMoveCoordinator:
    """Keeps planning/commit on the caller thread and hardware on a worker."""

    def __init__(self, executor: PhysicalMoveExecutor, graveyard: GraveyardManager) -> None:
        self.executor = executor
        self.graveyard = graveyard
        self.state = MovementState.LISTENING
        self.last_error: BaseException | None = None

    def perform_move(
        self,
        board: chess.Board,
        move: chess.Move,
        listener: PausableListener,
        *,
        pump: Callable[[], None] = lambda: None,
        status: Callable[[str], None] = lambda _message: None,
    ) -> PhysicalMovePlan:
        self.state = MovementState.MOVE_RECOGNIZED
        status(f"Move recognized: {move.uci()}")
        self.state = MovementState.PLANNING
        try:
            plan = plan_physical_move(board, move, self.graveyard)
        except UnsupportedPhysicalMove:
            self.state = MovementState.LISTENING
            raise
        except BaseException as exc:
            self.state = MovementState.ERROR
            self.last_error = exc
            status(f"Physical planning error: {exc}")
            raise

        listener.pause()
        self.state = MovementState.MOVING
        status(f"Moving: {move.uci()}")
        outcome: list[BaseException | None] = [None]

        def run_hardware() -> None:
            try:
                self.executor.execute(plan, self.graveyard)
            except BaseException as exc:
                outcome[0] = exc

        worker = threading.Thread(target=run_hardware, name="physical-move", daemon=False)
        worker.start()
        while worker.is_alive():
            pump()
            worker.join(timeout=0.01)
            if worker.is_alive():
                time.sleep(0.005)

        if outcome[0] is not None:
            self.state = MovementState.ERROR
            self.last_error = outcome[0]
            status(f"Physical movement error: {outcome[0]}")
            # Listening deliberately remains paused until explicit recovery.
            raise outcome[0]

        board.push(move)
        self.state = MovementState.MOVE_COMPLETE
        status(f"Move complete: {move.uci()}")
        listener.resume()
        self.state = MovementState.LISTENING
        self.last_error = None
        return plan

    def acknowledge_error_after_manual_recovery(self, listener: PausableListener) -> None:
        """Resume after the user restores all pieces and manually centres the carriage.

        This method never moves a motor. For a partially completed capture, the
        user must also restore the physical pieces to match the unchanged chess
        board before calling it.
        """
        if self.state is not MovementState.ERROR:
            raise RuntimeError("There is no movement error to acknowledge")
        self.executor.hardware.magnet_off()
        self.executor.carriage.reset_to_board_center()
        self.last_error = None
        listener.resume()
        self.state = MovementState.LISTENING
