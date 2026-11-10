import unittest
from types import SimpleNamespace
from physical_distance import PhysicalDistance,read_distance_frame,distance_input_kind

class Tests(unittest.TestCase):
    def frame(self,status,mm=450):
        data=bytearray(17);data[0]=status;data[13:15]=mm.to_bytes(2,'big')
        return SimpleNamespace(_read_register=lambda address,length:bytes(data))

    def test_no_target_is_not_a_numeric_distance_or_a_sensor_error(self):
        frame=read_distance_frame(self.frame(4,75))
        self.assertEqual(frame['measurement_state'],'no_target')
        self.assertIsNone(frame['distance_cm']);self.assertIsNone(frame['error'])
        self.assertEqual(frame['raw_range_mm'],75)

    def test_phase_warning_is_unreliable_not_clear(self):
        frame=read_distance_frame(self.frame(7,458))
        self.assertEqual(frame['measurement_state'],'unreliable')
        self.assertIsNone(frame['distance_cm'])

    def test_valid_status_keeps_numeric_cm(self):
        frame=read_distance_frame(self.frame(9,150))
        self.assertEqual(frame['distance_cm'],15.)
        self.assertEqual(frame['measurement_state'],'range')

    def test_hardware_status_and_transport_error_are_not_empty_scene(self):
        for status in (1,2,3,17):
            frame=read_distance_frame(self.frame(status))
            self.assertTrue(frame['error']);frame['received_s']=20.
            self.assertEqual(distance_input_kind(frame,20.),'fault')
        def fail(*args):raise OSError('I2C unavailable')
        with self.assertRaises(OSError):read_distance_frame(SimpleNamespace(_read_register=fail))

    def test_no_target_frame_allows_start_but_stale_does_not(self):
        sensor=self.frame(4);sensor.data_ready=True
        sensor.start_ranging=lambda:None;sensor.stop_ranging=lambda:None;sensor.clear_interrupt=lambda:None
        p=PhysicalDistance(factory=lambda:(sensor,SimpleNamespace(deinit=lambda:None)),clock=lambda:20.)
        try:
            p.wait_first_sample(timeout_s=.2);p.require_fresh()
            sample=p.latest();self.assertEqual(distance_input_kind(sample,20.),'no_target')
            self.assertEqual(distance_input_kind(sample,20.2),'fault')
        finally:p.close()
