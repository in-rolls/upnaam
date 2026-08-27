"""Token-sequence alignment for accepted cross-source record links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from rapidfuzz.distance import Levenshtein

from upnaam.normalization import tokenize_name

AlignmentKind = Literal["exact", "substitute", "roll_only", "external_only"]


@dataclass(frozen=True, slots=True)
class TokenAlignment:
    """One operation in a minimum-cost token alignment."""

    kind: AlignmentKind
    roll_token: str | None
    external_token: str | None
    normalized_distance: float | None
    roll_position: int | None
    external_position: int | None


def align_names(roll_name: object, external_name: object) -> tuple[TokenAlignment, ...]:
    """Align two names with unit gaps and normalized token edit costs.

    Args:
        roll_name: Name recorded in the electoral roll.
        external_name: Name recorded in the linked source.

    Returns:
        Ordered alignment operations. This is descriptive evidence and does
        not declare substituted tokens equivalent.

    Raises:
        RuntimeError: If the dynamic-programming backtrace is incomplete.
    """
    roll = tuple(token.normalized for token in tokenize_name(roll_name))
    external = tuple(token.normalized for token in tokenize_name(external_name))
    rows = len(roll) + 1
    columns = len(external) + 1
    costs = [[0.0] * columns for _ in range(rows)]
    back: list[list[str | None]] = [[None] * columns for _ in range(rows)]
    for row in range(1, rows):
        costs[row][0] = float(row)
        back[row][0] = "roll_only"
    for column in range(1, columns):
        costs[0][column] = float(column)
        back[0][column] = "external_only"
    priority = {"exact": 0, "substitute": 1, "roll_only": 2, "external_only": 3}
    for row in range(1, rows):
        for column in range(1, columns):
            distance = Levenshtein.normalized_distance(
                roll[row - 1], external[column - 1]
            )
            diagonal_kind = "exact" if distance == 0 else "substitute"
            choices = (
                (costs[row - 1][column - 1] + distance, diagonal_kind),
                (costs[row - 1][column] + 1, "roll_only"),
                (costs[row][column - 1] + 1, "external_only"),
            )
            cost, operation = min(
                choices, key=lambda item: (item[0], priority[item[1]])
            )
            costs[row][column] = cost
            back[row][column] = operation

    operations: list[TokenAlignment] = []
    row = len(roll)
    column = len(external)
    while row or column:
        operation = back[row][column]
        if operation in {"exact", "substitute"}:
            left = roll[row - 1]
            right = external[column - 1]
            operations.append(
                TokenAlignment(
                    kind=cast("AlignmentKind", operation),
                    roll_token=left,
                    external_token=right,
                    normalized_distance=Levenshtein.normalized_distance(left, right),
                    roll_position=row - 1,
                    external_position=column - 1,
                )
            )
            row -= 1
            column -= 1
        elif operation == "roll_only":
            operations.append(
                TokenAlignment("roll_only", roll[row - 1], None, None, row - 1, None)
            )
            row -= 1
        elif operation == "external_only":
            operations.append(
                TokenAlignment(
                    "external_only", None, external[column - 1], None, None, column - 1
                )
            )
            column -= 1
        else:
            raise RuntimeError("alignment backtrace is incomplete")
    return tuple(reversed(operations))
