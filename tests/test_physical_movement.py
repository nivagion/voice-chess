import unittest

import chess

from physical_config import HORIZONTAL_STEPS_PER_SQUARE, VERTICAL_STEPS_PER_SQUARE
from physical_geometry import (
    MAX_X2,
    MAX_Y2,
    MIN_X2,
    MIN_Y2,
    START_POSITION,
    Point,
    Segment,
    board_square_center,
    graveyard_center,
    plan_carried_path,
    point_within_bounds,
    segment_motor_steps,
)
from physical_hardware import FakeHardwareDriver, HardwareCommand
from physical_movement import (
    CarriageState,
    GraveyardManager,
    PhysicalMoveCoordinator,
    PhysicalMoveExecutor,
    UnsupportedPhysicalMove,
    plan_physical_move,
)


class FakeListener:
    def __init__(self) -> None:
        self.paused = False
        self.pause_count = 0
        self.resume_count = 0

    def pause(self) -> None:
        self.paused = True
        self.pause_count += 1

    def resume(self) -> None:
        self.paused = False
        self.resume_count += 1


class ListeningAwareHardware(FakeHardwareDriver):
    def __init__(self, listener: FakeListener) -> None:
        super().__init__()
        self.listener = listener
        self.all_commands_while_paused = True

    def _check(self) -> None:
        self.all_commands_while_paused &= self.listener.paused

    def move(self, segment: Segment) -> None:
        self._check()
        super().move(segment)

    def magnet_on(self) -> None:
        self._check()
        super().magnet_on()

    def magnet_off(self) -> None:
        self._check()
        super().magnet_off()


def capture_board(captured_color: chess.Color) -> tuple[chess.Board, chess.Move]:
    board = chess.Board(None)
    board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
    if captured_color == chess.BLACK:
        board.set_piece_at(chess.A1, chess.Piece(chess.ROOK, chess.WHITE))
        board.set_piece_at(chess.A8, chess.Piece(chess.ROOK, chess.BLACK))
        board.turn = chess.WHITE
        return board, chess.Move.from_uci("a1a8")
    board.set_piece_at(chess.H8, chess.Piece(chess.ROOK, chess.BLACK))
    board.set_piece_at(chess.H1, chess.Piece(chess.ROOK, chess.WHITE))
    board.turn = chess.BLACK
    return board, chess.Move.from_uci("h8h1")


class GeometryTests(unittest.TestCase):
    def test_initial_carriage_coordinate(self):
        self.assertEqual(START_POSITION, Point(11, 7))

    def test_board_corner_mapping(self):
        self.assertEqual(board_square_center("a1"), Point(4, 0))
        self.assertEqual(board_square_center("h1"), Point(18, 0))
        self.assertEqual(board_square_center("a8"), Point(4, 14))
        self.assertEqual(board_square_center("h8"), Point(18, 14))

    def test_all_graveyard_boundaries(self):
        self.assertEqual(graveyard_center(0, 0), Point(0, 0))
        self.assertEqual(graveyard_center(1, 7), Point(2, 14))
        self.assertEqual(graveyard_center(10, 0), Point(20, 0))
        self.assertEqual(graveyard_center(11, 7), Point(22, 14))
        self.assertEqual((MIN_X2, MAX_X2, MIN_Y2, MAX_Y2), (-1, 23, -1, 15))

    def test_full_square_step_conversion(self):
        self.assertEqual(segment_motor_steps(Segment(Point(4, 0), Point(6, 0))), HORIZONTAL_STEPS_PER_SQUARE)
        self.assertEqual(segment_motor_steps(Segment(Point(4, 0), Point(4, 2))), VERTICAL_STEPS_PER_SQUARE)

    def test_paths_are_axis_aligned_and_bounded(self):
        centers = [Point(column * 2, rank * 2) for column in range(12) for rank in range(8)]
        for source in centers:
            for destination in centers:
                if source == destination:
                    continue
                for segment in plan_carried_path(source, destination):
                    self.assertIn(segment.axis, ("horizontal", "vertical"))
                    self.assertTrue(point_within_bounds(segment.start))
                    self.assertTrue(point_within_bounds(segment.end))

    def test_rank_edges_enter_inward(self):
        low = plan_carried_path(board_square_center("a1"), board_square_center("h8"))[0]
        high = plan_carried_path(board_square_center("h8"), board_square_center("a1"))[0]
        self.assertEqual(low.end.y2, 1)
        self.assertEqual(high.end.y2, 13)

    def test_physical_column_edges_do_not_move_outward(self):
        left = plan_carried_path(graveyard_center(0, 3), board_square_center("a4"))[0]
        right = plan_carried_path(graveyard_center(11, 3), board_square_center("h4"))[0]
        self.assertGreaterEqual(left.end.x2, left.start.x2)
        self.assertLessEqual(right.end.x2, right.start.x2)


class PlanningAndExecutionTests(unittest.TestCase):
    def test_normal_move_has_one_piece_operation(self):
        board = chess.Board()
        plan = plan_physical_move(board, chess.Move.from_uci("e2e4"), GraveyardManager())
        self.assertEqual(len(plan.operations), 1)

    def test_capture_removes_target_first(self):
        board, move = capture_board(chess.BLACK)
        plan = plan_physical_move(board, move, GraveyardManager())
        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(plan.operations[0].description, "remove captured piece")
        self.assertEqual(plan.operations[0].source, board_square_center("a8"))
        self.assertEqual(plan.operations[1].description, "move attacking piece")

    def test_captured_colors_use_correct_graveyards(self):
        for color, expected_x2 in ((chess.WHITE, 2), (chess.BLACK, 20)):
            board, move = capture_board(color)
            plan = plan_physical_move(board, move, GraveyardManager())
            self.assertEqual(plan.graveyard_reservation.point.x2, expected_x2)

    def test_occupied_graveyard_slot_is_not_reused(self):
        manager = GraveyardManager()
        first = manager.reserve(chess.WHITE)
        manager.commit(first, chess.Piece(chess.PAWN, chess.WHITE))
        second = manager.reserve(chess.WHITE)
        self.assertNotEqual(first.point, second.point)

    def test_listening_is_paused_for_all_hardware_commands(self):
        listener = FakeListener()
        hardware = ListeningAwareHardware(listener)
        board = chess.Board()
        coordinator = PhysicalMoveCoordinator(PhysicalMoveExecutor(hardware), GraveyardManager())
        coordinator.perform_move(board, chess.Move.from_uci("e2e4"), listener)
        self.assertTrue(hardware.all_commands_while_paused)
        self.assertEqual(listener.pause_count, 1)
        self.assertEqual(listener.resume_count, 1)
        self.assertFalse(listener.paused)

    def test_failure_does_not_push_and_forces_magnet_off(self):
        listener = FakeListener()
        hardware = FakeHardwareDriver(fail_at_command=1)
        board = chess.Board()
        original_fen = board.fen()
        coordinator = PhysicalMoveCoordinator(PhysicalMoveExecutor(hardware), GraveyardManager())
        with self.assertRaises(Exception):
            coordinator.perform_move(board, chess.Move.from_uci("e2e4"), listener)
        self.assertEqual(board.fen(), original_fen)
        self.assertTrue(listener.paused)
        self.assertEqual(listener.resume_count, 0)
        self.assertIn(HardwareCommand("magnet_off"), hardware.commands)

    def test_carriage_ends_at_piece_destination(self):
        board = chess.Board()
        executor = PhysicalMoveExecutor(FakeHardwareDriver(), CarriageState())
        coordinator = PhysicalMoveCoordinator(executor, GraveyardManager())
        coordinator.perform_move(board, chess.Move.from_uci("e2e4"), FakeListener())
        self.assertEqual(executor.carriage.position, board_square_center("e4"))

    def test_special_moves_are_rejected_before_board_change(self):
        cases = [
            (chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), "e1g1"),
            (chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"), "e5d6"),
            (chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1"), "a7a8q"),
        ]
        for board, uci in cases:
            before = board.fen()
            with self.assertRaises(UnsupportedPhysicalMove):
                plan_physical_move(board, chess.Move.from_uci(uci), GraveyardManager())
            self.assertEqual(board.fen(), before)


if __name__ == "__main__":
    unittest.main()
