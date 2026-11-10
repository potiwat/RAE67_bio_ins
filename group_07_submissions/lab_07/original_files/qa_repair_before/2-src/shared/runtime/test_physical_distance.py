import unittest
from types import SimpleNamespace
from physical_distance import PhysicalDistance


class Tests(unittest.TestCase):
    def test_invalid_numeric_initial_values_block_startup(self):
        for value in (float('nan'),-1.,401.):
            sensor=SimpleNamespace(data_ready=True,distance=value,start_ranging=lambda:None,stop_ranging=lambda:None,clear_interrupt=lambda:None)
            p=PhysicalDistance(factory=lambda:(sensor,SimpleNamespace(deinit=lambda:None)),clock=lambda:20.)
            try:
                with self.assertRaises(RuntimeError):p.wait_first_sample(timeout_s=.05)
            finally:p.close()

    def test_motion_start_checks_fresh_input_before_position_commands(self):
        from normal_gaze_motor import NormalGaze
        from test_normal_gaze_motor import Bus,NORMAL,ORIGIN
        b=Bus();c=NormalGaze(b,ORIGIN,NORMAL)
        def reject():raise RuntimeError('stale distance')
        with self.assertRaises(RuntimeError):c.start(0.,pre_motion_check=reject)
        self.assertFalse(any(a in (40,42) for i,a,q in b.calls))
    def test_input_worker_returns_centimeters_and_closes_sensor(self):
        flags=[]
        sensor=SimpleNamespace(data_ready=True,distance=27.5,
            start_ranging=lambda:flags.append('start'),stop_ranging=lambda:flags.append('stop'),clear_interrupt=lambda:None)
        bus=SimpleNamespace(deinit=lambda:flags.append('deinit'))
        p=PhysicalDistance(factory=lambda:(sensor,bus),clock=lambda:20.)
        try:
            p.wait_first_sample();sample=p.latest()
            self.assertEqual(sample['distance_cm'],27.5)
            self.assertEqual(sample['received_s'],20.)
            self.assertEqual(sensor.timing_budget,100)
        finally:p.close()
        self.assertEqual(flags,['start','stop','deinit'])

    def test_invalid_initial_sample_blocks_startup(self):
        sensor=SimpleNamespace(data_ready=True,distance=None,start_ranging=lambda:None,stop_ranging=lambda:None,clear_interrupt=lambda:None)
        bus=SimpleNamespace(deinit=lambda:None)
        p=PhysicalDistance(factory=lambda:(sensor,bus),clock=lambda:20.)
        try:
            with self.assertRaises(RuntimeError):p.wait_first_sample(timeout_s=.05)
        finally:p.close()

    def test_startup_waits_for_valid_sample_after_initial_not_ready_value(self):
        class Sensor:
            data_ready=True
            reads=0
            @property
            def distance(self):
                self.reads+=1
                return None if self.reads<3 else 42.
            def start_ranging(self):pass
            def stop_ranging(self):pass
            def clear_interrupt(self):pass
        p=PhysicalDistance(factory=lambda:(Sensor(),SimpleNamespace(deinit=lambda:None)),clock=lambda:20.)
        try:
            p.wait_first_sample(timeout_s=.2)
            self.assertEqual(p.latest()['distance_cm'],42.)
        finally:p.close()
