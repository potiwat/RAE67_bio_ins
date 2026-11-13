import unittest
from types import SimpleNamespace
from .pipeline_timing import PipelineTiming


class Tests(unittest.TestCase):
    def test_preserves_result_exception_and_bounded_recent_timing(self):
        t=[0.]
        timing=PipelineTiming(lambda:t[0])
        def call(value):
            t[0]+=.231
            if value is None:raise ValueError('same error')
            return value
        obj=SimpleNamespace(run=call)
        timing.wrap(obj,'run','disk')
        self.assertEqual(obj.run(7),7)
        with self.assertRaisesRegex(ValueError,'same error'):obj.run(None)
        self.assertAlmostEqual(timing.snapshot()['max_duration_s']['disk'],.231)
        for _ in range(200):obj.run(1)
        self.assertEqual(len(timing.recent),128)
        t[0]+=3
        self.assertEqual(timing.snapshot()['recent_slow'],[])

    def test_fast_operations_do_not_grow_trace(self):
        timing=PipelineTiming(lambda:0.)
        self.assertEqual(timing.call('fast',lambda:3),3)
        self.assertEqual(len(timing.recent),0)

    def test_snapshot_includes_still_running_enclosing_operation(self):
        t=[1.];timing=PipelineTiming(lambda:t[0])
        def pending():
            t[0]+=.231
            return timing.snapshot()
        d=timing.call('outer',pending)
        self.assertEqual(d['active'][0]['operation'],'outer')
        self.assertAlmostEqual(d['active'][0]['elapsed_s'],.231)
        self.assertEqual(timing.active,[])
