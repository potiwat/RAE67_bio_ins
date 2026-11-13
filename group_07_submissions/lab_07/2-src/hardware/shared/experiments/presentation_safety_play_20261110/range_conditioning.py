"""Distance views for Present Safety. One filter update per VL53L1X result."""
from collections import deque
import math
from statistics import median

from physical_distance import distance_input_kind


class RangeFilter:
    def __init__(self):
        self.history = deque(maxlen=3)
        self.previous = None

    def frame(self, cm, stamp, sequence, error, metadata):
        sample = dict(metadata, distance_cm=cm, received_s=stamp, sequence=sequence, error=error)
        valid = (distance_input_kind(sample, stamp) == 'range'
                 and sample.get('measurement_state', 'range') == 'range'
                 and sample.get('range_status_raw', 9) in (8, 9))
        previous = self.previous
        if (not valid or previous is None or sequence != previous[0] + 1
                or not 0 < stamp - previous[1] <= .12 + 1e-9):
            self.history.clear()
        self.previous = (sequence, stamp) if valid else None
        filtered = None
        if valid:
            if not self.history:
                self.history.append(cm)  # Seed the median with the first measured value.
            self.history.append(cm)
            filtered = median(self.history)
        guard = min(cm, filtered) if valid else None
        # Existing protective consumers read distance_cm. They see every raw approach
        # immediately and cannot certify a departure on one distant outlier.
        return dict(sample, raw_distance_cm=cm, filtered_distance_cm=filtered,
                    guard_distance_cm=guard, distance_cm=guard)


def behavior_frame(sample):
    if not sample or 'filtered_distance_cm' not in sample:
        return sample
    return dict(sample, distance_cm=sample['filtered_distance_cm'])


def conditioned_source(original):
    class ConditionedDistance(original):
        def __init__(self, *args, **kwargs):
            self.range_filter = RangeFilter()
            self.sequence_base = 0
            self.last_sequence = 0
            super().__init__(*args, **kwargs)

        def _publish(self, cm, error, sequence, **metadata):
            seq = self.sequence_base + sequence
            self.last_sequence = seq
            frame = self.range_filter.frame(cm, self.clock(), seq, error, metadata)
            with self.lock:
                self.sample = frame
            self.ready.set()

        def _run(self):
            retry_s = .25
            while not self.stop.is_set():
                before = self.last_sequence
                try:
                    super()._run()  # The retained worker opens, reads and closes its own bus.
                except OSError as error:
                    self._publish(None, str(error), self.last_sequence-self.sequence_base)
                if self.stop.is_set():
                    return
                if self.last_sequence > before:
                    retry_s = .25
                if self.stop.wait(retry_s):
                    return
                self.sequence_base = self.last_sequence
                self.range_filter = RangeFilter()
                retry_s = min(2., retry_s*2)
    return ConditionedDistance


def read_stimulus(m, now, details=None):
    """Combine debounced GPIO with confirmed behavioral Near, independently of range outages."""
    source = getattr(m, 'physical_distance', None)
    sample = behavior_frame(source.latest() if source is not None else getattr(m, 'distance_view', None))
    channels = [getattr(m, 'physical_'+ch, None) for ch in ('button','touch')]
    if any(ch is None for ch in channels):
        return None
    views = [ch.diagnostics() for ch in channels]
    now = max(now, getattr(m, 'now', lambda: now)())
    kind = distance_input_kind(sample, now)
    near = bool(getattr(getattr(m, 'distance_gate', None), 'near', False))
    if kind == 'no_target':
        near = False
    elif kind == 'range':
        near = sample['distance_cm'] < 28. if near else sample['distance_cm'] <= 20.
    if details is not None:
        details.update(views=views, near=near, tof_quality=kind, tof_frame=sample)
    for view in views:
        stamp = view.get('last_sample_s')
        if (view.get('sampler_error') or type(view.get('stable_pressed')) is not bool
                or type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not 0 <= now-stamp <= .12+1e-9):
            return None
    return float(near or any(view['stable_pressed'] for view in views))

