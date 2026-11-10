import json
import tempfile
import unittest
from pathlib import Path
from motion_trace import MotionTrace


class TraceTests(unittest.TestCase):
    def test_trace_distinguishes_sent_readback_and_actual_times(self):
        trace = MotionTrace(3)
        trace.record(dict(tick_id=1, producer='cpg', time_s=1., clock='virtual',
                          sent_tick=2019, sent_s=1., readback_tick=2019,
                          readback_s=1.01, actual_tick=None, actual_s=None,
                          missing_reason='hardware_not_connected'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace.json'
            trace.export(path)
            row = json.loads(path.read_text())['events'][0]
        self.assertLess(row['sent_s'], row['readback_s'])
        self.assertIsNone(row['actual_s'])

    def test_missing_measurement_remains_na_and_storage_is_bounded(self):
        trace = MotionTrace(2)
        for i in range(4):
            trace.record(dict(tick_id=i, producer='test', clock='virtual', time_s=i,
                              actual_tick=None, missing_reason='not_measured'))
        self.assertEqual([r['tick_id'] for r in trace.events], [2, 3])
        self.assertEqual(trace.dropped, 2)
        self.assertIsNone(trace.events[0]['actual_tick'])

    def test_snapshot_is_not_mutable_and_invalid_values_rejected(self):
        trace = MotionTrace(2)
        row = dict(tick_id=0, producer='test', clock='virtual', time_s=0., nested={'a': 1})
        trace.record(row)
        row['nested']['a'] = 5
        trace.events[0]['nested']['a'] = 9
        self.assertEqual(trace.events[0]['nested']['a'], 1)
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                trace.record(dict(tick_id=1, producer='x', clock='virtual', time_s=value))


if __name__ == '__main__':
    unittest.main()
