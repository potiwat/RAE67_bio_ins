"""Camera-only target geometry; no hardware imports or actuator output.

Overlap association is NOT face recognition. Crossing/occlusion can confuse it.
All boxes are normalized (x, y, width, height), image right/down positive.
"""
from dataclasses import dataclass
import math


def finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


@dataclass(frozen=True)
class Observation:
    status: str
    box: tuple | None
    error_xy: tuple | None
    captured_s: float
    processed_s: float
    source_id: int


def overlap(a, b):
    width = max(0., min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    height = max(0., min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return width * height


class FaceTracker:
    def __init__(self, max_age_s):
        if not finite_number(max_age_s) or max_age_s <= 0:
            raise ValueError('max_age_s must be positive and finite')
        self.max_age_s = max_age_s
        self.reset()
        self.sequence = 0

    def reset(self):
        self.previous_box = None
        self.last_captured = None
        self.last_processed = None

    def update(self, boxes, captured_s, processed_s):
        self.sequence += 1

        def result(status, box=None):
            error = None if box is None else (
                2 * (box[0] + box[2] / 2) - 1,
                2 * (box[1] + box[3] / 2) - 1)
            return Observation(status, box, error, captured_s, processed_s, self.sequence)

        if (not finite_number(captured_s) or not finite_number(processed_s)
                or not 0 <= captured_s <= processed_s
                or (self.last_captured is not None and captured_s <= self.last_captured)
                or (self.last_processed is not None and processed_s < self.last_processed)):
            return result('INVALID')
        # Even stale/invalid geometry frames consume their sequence/time.
        self.last_captured, self.last_processed = captured_s, processed_s
        if processed_s - captured_s > self.max_age_s:
            return result('STALE')
        try:
            boxes = [tuple(box) for box in boxes]
            for x, y, w, h in boxes:
                if (not all(finite_number(v) for v in (x, y, w, h))
                        or x < 0 or y < 0 or w <= 0 or h <= 0
                        or x + w > 1 + 1e-9 or y + h > 1 + 1e-9):
                    return result('INVALID')
        except (TypeError, ValueError):
            return result('INVALID')
        if self.previous_box is None:
            if not boxes:
                return result('WAITING')
            selected = min(boxes, key=lambda b: (
                (b[0] + b[2] / 2 - .5) ** 2 + (b[1] + b[3] / 2 - .5) ** 2, b))
            status = 'ACQUIRED'
        else:
            matches = [b for b in boxes if overlap(self.previous_box, b) > 0]
            if not matches:
                return result('LOST')
            if len(matches) != 1:
                return result('AMBIGUOUS')
            selected, = matches
            status = 'TRACKING'
        self.previous_box = selected
        return result(status, selected)
