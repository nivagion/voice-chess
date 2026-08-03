"""Authoritative geometry and safe lane-path planning for the physical board.

Coordinates are integer half-square units. Even coordinates are square
centres; odd coordinates are lane lines. The planner assumes the lane network
is physically clear and pieces do not extend far enough to collide across a
lane. It deliberately does not perform global obstacle avoidance.
"""

from dataclasses import dataclass
from fractions import Fraction

from physical_config import HORIZONTAL_STEPS_PER_SQUARE, VERTICAL_STEPS_PER_SQUARE


LEFT_GRAVEYARD_COLUMNS = (0, 1)
BOARD_COLUMNS = tuple(range(2, 10))
RIGHT_GRAVEYARD_COLUMNS = (10, 11)
RANKS = tuple(range(8))

MIN_X2, MAX_X2 = -1, 23
MIN_Y2, MAX_Y2 = -1, 15


@dataclass(frozen=True, order=True)
class Point:
    x2: int
    y2: int

    @property
    def is_square_center(self) -> bool:
        return self.x2 % 2 == 0 and self.y2 % 2 == 0

    @property
    def is_on_lane(self) -> bool:
        return self.x2 % 2 != 0 or self.y2 % 2 != 0

    def display(self) -> str:
        return f"({self.x2 / 2:g}, {self.y2 / 2:g})"


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point

    @property
    def axis(self) -> str:
        if self.start.y2 == self.end.y2 and self.start.x2 != self.end.x2:
            return "horizontal"
        if self.start.x2 == self.end.x2 and self.start.y2 != self.end.y2:
            return "vertical"
        raise ValueError(f"Segment is not axis-aligned: {self}")


START_POSITION = Point(11, 7)  # Between D/E and ranks 4/5.


def board_square_center(square_name: str) -> Point:
    if len(square_name) != 2:
        raise ValueError(f"Invalid square: {square_name}")
    file_name, rank_name = square_name.lower()
    if file_name not in "abcdefgh" or rank_name not in "12345678":
        raise ValueError(f"Invalid square: {square_name}")
    column = 2 + ord(file_name) - ord("a")
    rank = int(rank_name) - 1
    return Point(2 * column, 2 * rank)


def graveyard_center(column: int, rank: int) -> Point:
    if column not in LEFT_GRAVEYARD_COLUMNS + RIGHT_GRAVEYARD_COLUMNS:
        raise ValueError(f"Invalid graveyard column: {column}")
    if rank not in RANKS:
        raise ValueError(f"Invalid graveyard rank: {rank}")
    return Point(2 * column, 2 * rank)


def point_within_bounds(point: Point) -> bool:
    return MIN_X2 <= point.x2 <= MAX_X2 and MIN_Y2 <= point.y2 <= MAX_Y2


def _round_fraction(value: Fraction) -> int:
    if value >= 0:
        return (value.numerator * 2 + value.denominator) // (2 * value.denominator)
    return -_round_fraction(-value)


def point_to_motor_steps(point: Point) -> tuple[int, int]:
    """Return absolute calibrated step coordinates relative to startup."""
    x = _round_fraction(Fraction(point.x2 - START_POSITION.x2, 2) * HORIZONTAL_STEPS_PER_SQUARE)
    y = _round_fraction(Fraction(point.y2 - START_POSITION.y2, 2) * VERTICAL_STEPS_PER_SQUARE)
    return x, y


def segment_motor_steps(segment: Segment) -> int:
    """Convert a segment using endpoint differences, avoiding half-step drift."""
    axis = segment.axis
    start_steps = point_to_motor_steps(segment.start)
    end_steps = point_to_motor_steps(segment.end)
    index = 0 if axis == "horizontal" else 1
    return abs(end_steps[index] - start_steps[index])


def _inward_lane(coordinate2: int, minimum_center2: int, maximum_center2: int, toward2: int) -> int:
    if coordinate2 == minimum_center2:
        return coordinate2 + 1
    if coordinate2 == maximum_center2:
        return coordinate2 - 1
    return coordinate2 + (1 if toward2 >= coordinate2 else -1)


def _segments(points: list[Point]) -> tuple[Segment, ...]:
    compact = [points[0]]
    for point in points[1:]:
        if point != compact[-1]:
            compact.append(point)
    result = tuple(Segment(a, b) for a, b in zip(compact, compact[1:]))
    for segment in result:
        segment.axis
        if not point_within_bounds(segment.start) or not point_within_bounds(segment.end):
            raise ValueError(f"Path leaves physical bounds: {segment}")
    return result


def plan_carried_path(source: Point, destination: Point) -> tuple[Segment, ...]:
    """Plan a deterministic centre-to-centre route through clear lane lines.

    The first and last segments are half-square centre/lane transitions. Every
    intermediate segment lies on a lane, so it cannot pass through a square
    centre. At the physical outer edges the selected lane always points inward.
    """
    if not source.is_square_center or not destination.is_square_center:
        raise ValueError("Carried paths must start and end at square centres")
    if source == destination:
        raise ValueError("Source and destination must differ")

    source_y_lane = _inward_lane(source.y2, 0, 14, destination.y2)
    destination_y_lane = _inward_lane(destination.y2, 0, 14, source.y2)
    vertical_x_lane = _inward_lane(source.x2, 0, 22, destination.x2)

    points = [
        source,
        Point(source.x2, source_y_lane),
        Point(vertical_x_lane, source_y_lane),
        Point(vertical_x_lane, destination_y_lane),
        Point(destination.x2, destination_y_lane),
        destination,
    ]
    result = _segments(points)

    for index, segment in enumerate(result):
        if index not in (0, len(result) - 1):
            if not segment.start.is_on_lane or not segment.end.is_on_lane:
                raise AssertionError(f"Carried segment left lane network: {segment}")
    return result


def plan_carriage_path(source: Point, destination: Point) -> tuple[Segment, ...]:
    """Plan predictable magnet-off travel: horizontal first, then vertical."""
    if not point_within_bounds(source) or not point_within_bounds(destination):
        raise ValueError("Carriage path endpoint is outside physical bounds")
    return _segments([source, Point(destination.x2, source.y2), destination])
