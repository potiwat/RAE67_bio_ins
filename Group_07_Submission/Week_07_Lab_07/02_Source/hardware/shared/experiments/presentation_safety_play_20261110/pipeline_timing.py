"""Bounded in-memory timing only. No threads, files, or device access."""
import time
from collections import deque
from functools import wraps


class PipelineTiming:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.recent = deque(maxlen=128)
        self.maxima = {}
        self.active = []

    def call(self, label, function, *args, **kwargs):
        start = self.clock()
        frame = dict(operation=label, start_s=start)
        self.active.append(frame)
        try:
            return function(*args, **kwargs)
        finally:
            end = self.clock()
            self.active.remove(frame)
            duration = end-start
            self.maxima[label] = max(duration, self.maxima.get(label, 0.))
            if duration >= .015:
                self.recent.append(dict(operation=label, start_s=start,
                                        end_s=end, duration_s=duration))

    def wrap(self, obj, name, label=None):
        original = getattr(obj, name, None)
        if not callable(original):
            return
        @wraps(original)
        def measured(*args, **kwargs):
            return self.call(label or name, original, *args, **kwargs)
        setattr(obj, name, measured)

    def snapshot(self):
        now = self.clock()
        return dict(max_duration_s=dict(self.maxima),
                    active=[dict(r,elapsed_s=now-r['start_s'])for r in self.active],
                    recent_slow=[dict(r) for r in self.recent if now-r['end_s'] <= 2.])
