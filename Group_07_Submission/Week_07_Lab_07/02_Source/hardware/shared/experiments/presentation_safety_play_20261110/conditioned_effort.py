"""Frozen, pose-conditioned ID2 evidence. No device access or online learning.

Unknown coverage is not clearance. This is an experimental extra stop request,
not a force sensor or a certified collision detector. Existing faults/limits
and conventional evidence remain in charge independently.
"""
import json
import math
import time
from collections import deque


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


class ContextEffortEvidence:
    def __init__(self, reference):
        if reference.get('schema_version') != 1:
            raise ValueError('Unsupported frozen reference')
        sources = reference.get('sources', [])
        points = reference.get('points', [])
        if len(sources) < 2 or not 8 <= len(points) <= 10000:
            raise ValueError('Independent reference recordings required')
        self.points = []
        for p in points:
            x, y = p['x'], p['y']
            if (len(x) != 3 or len(y) != 3 or
                not all(finite(v) for v in x+y) or
                not 0 <= x[0] <= 4095 or not 0 <= x[2] <= 4095 or
                any(v < 0 for v in y) or
                type(p['source']) is not int or not 0 <= p['source'] < len(sources) or
                type(p['speed_cap']) is not int or type(p['acc']) is not int):
                raise ValueError('Invalid frozen reference point')
            self.points.append((tuple(x), tuple(y), p['speed_cap'], p['acc'], p['source']))
        self.previous = None
        self.support = None
        self.history = deque()
        self.last = {}
        self.stats = dict(id2_samples=0, covered_samples=0, candidate_points=0,
                          max_update_ms=0., immutable_reference=True)

    @classmethod
    def from_path(cls, path):
        return cls(json.loads(path.read_text()))

    def update(self, row, decision):
        begin = time.perf_counter()
        try:
            result = self._update(row, decision)
            if row.get('id') == 2:
                self.last = result
            return result
        finally:
            self.stats['max_update_ms'] = max(self.stats['max_update_ms'],
                                             (time.perf_counter()-begin)*1000)

    def _update(self, row, decision):
        out = dict(candidate_stop=False, covered=False, advisory_only=True,
                   physically_validated=False, path='context_reference')
        sid, t = row.get('id'), row.get('time_s')
        if sid not in (2, 3):
            return out
        valid = (finite(t) and decision.get('decision') == 'MONITOR' and
                 row.get('complete_feedback') is True and
                 row.get('controller_state') in ('READY', 'FOLLOWING') and
                 row.get('operator_stopped') is False and row.get('mode') == 0 and
                 row.get('torque_raw') == 1 and row.get('status_raw') == 0)
        if sid == 3:
            ref = row.get('internal_target_raw')
            self.support = (t, ref) if valid and type(ref) is int and 0 <= ref <= 4095 else None
            if self.support is None:
                self.history.clear()
            return out
        self.stats['id2_samples'] += 1
        keys = ('internal_target_raw', 'position_raw', 'current_raw', 'load_raw',
                'target_speed_raw', 'acceleration_raw')
        old = self.previous
        if not valid or any(type(row.get(k)) is not int for k in keys):
            self.previous = None
            self.history.clear()
            return out
        self.previous = (t, row['internal_target_raw'])
        if (old is None or not 0 < t-old[0] <= .2 or self.support is None or
                not 0 <= t-self.support[0] <= .1):
            self.history.clear()
            return out
        ref = row['internal_target_raw']
        velocity = (ref-old[1])/(t-old[0])
        matches = []
        # A nearby resting pose is not a moving-load reference. Without
        # same-direction motion examples this channel reports uncovered;
        # conventional effort/blocked and native fault paths stay active.
        for x, y, speed, acc, source in self.points:
            if (speed == row['target_speed_raw'] and acc == row['acceleration_raw'] and
                abs(ref-x[0]) <= 30 and abs(velocity-x[1]) <= 100 and
                (velocity == 0 or velocity*x[1] > 0) and
                abs(self.support[1]-x[2]) <= 60):
                matches.append((y, source))
        origins = {s for _, s in matches}
        out.update(matched_samples=len(matches), reference_recordings=len(origins))
        if len(matches) < 8 or len(origins) < 2:
            self.history.clear()
            return out
        self.stats['covered_samples'] += 1
        maxima = [max(y[k] for y, _ in matches) for k in range(3)]
        values = [row['current_raw'], row['load_raw'] & 1023, abs(row['internal_target_raw']-row['position_raw'])]
        out.update(covered=True, reference_max=maxima, values=values)
        # A target catching up toward a sagged/overshot encoder is unloading
        # an existing residual, not demanding motion farther against it.
        # Frozen reference maxima alone cannot distinguish that transition.
        # Conventional high-effort/blocked detectors remain independent.
        if (ref-row['position_raw'])*(ref-old[1]) < 0:
            self.history.clear()
            out['reason'] = 'reference is closing existing tracking residual'
            return out
        if not all(a-b > margin for a, b, margin in zip(values, maxima, (3, 20, 3))):
            self.history.clear()
            return out
        self.stats['candidate_points'] += 1
        error=abs(ref-row['position_raw'])
        self.history.append((t, ref, error))
        while len(self.history) > 1 and t-self.history[1][0] >= .15:
            self.history.popleft()
        span = max(x[1] for x in self.history)-min(x[1] for x in self.history)
        duration = t-self.history[0][0]
        growth=error-self.history[0][2]
        out['error_growth_ticks']=growth
        if len(self.history) >= 4 and duration >= .15-1e-9 and span >= 6 and growth > 0:
            out.update(candidate_stop=True, duration_s=duration, reference_span_ticks=span,
                       reason='effort exceeds frozen similar-motion reference while target advances and tracking residual grows')
        return out
