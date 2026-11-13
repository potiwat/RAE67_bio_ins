"""Bounded, device-independent motion evidence. None always means unmeasured."""
import copy
import json
import math
from collections import deque
from pathlib import Path


class MotionTrace:
    def __init__(self, max_events=20000):
        if type(max_events) is not int or not 1 <= max_events <= 100000:
            raise ValueError('Trace capacity must be 1..100000')
        self._events = deque(maxlen=max_events)
        self.dropped = 0

    @property
    def events(self):
        return copy.deepcopy(list(self._events))

    def record(self, event):
        if not isinstance(event, dict):
            raise ValueError('Event must be a dictionary')
        if type(event.get('tick_id')) is not int or event['tick_id'] < 0:
            raise ValueError('Nonnegative tick_id required')
        for key in ('producer', 'clock'):
            if not isinstance(event.get(key), str) or not event[key]:
                raise ValueError(f'{key} required')
        value = event.get('time_s')
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Finite nonnegative event time required')
        # Also rejects non-finite numbers hidden in nested metadata.
        try:
            snapshot = json.loads(json.dumps(event, allow_nan=False))
        except (TypeError, ValueError) as error:
            raise ValueError('Trace must contain finite JSON data') from error
        if len(self._events) == self._events.maxlen:
            self.dropped += 1
        self._events.append(snapshot)

    def export(self, path):
        path = Path(path)
        report = dict(schema='lamp_motion_trace_v1', dropped=self.dropped,
                      capacity=self._events.maxlen, events=self.events)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
