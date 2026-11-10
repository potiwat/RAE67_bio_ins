import unittest
from probe_observation import ProbeObservation


class ProbeTests(unittest.TestCase):
    def rows(self, position=2030, moving=0):
        return [dict(id=i, position_raw=position if i == 4 else 2000,
                     torque_raw=1, mode=0, status_raw=0, moving_raw=moving if i == 4 else 0,
                     speed_raw=0, sampled_monotonic_s=8.) for i in range(1, 6)]

    def face(self, now):
        return dict(status='TRACKING', source_id=42, captured_s=now-.1,
                    error_xy=[.1, -.1], box=[.3, .3, .2, .2])

    def request(self, recorder, now=1.):
        recorder.request(dict(time_s=now, target_raw=2031, base_raw=1997))

    def test_capture_waits_for_stationary_rows_and_fresh_post_command_face(self):
        recorder = ProbeObservation()
        self.request(recorder)
        recorder.observe(3., self.rows(moving=1), self.face(3.), 'READY')
        self.assertEqual(recorder.samples, [])
        for now in (3.1, 3.2, 3.3, 3.4, 3.5):
            recorder.observe(now, self.rows(), self.face(now), 'READY')
        sample = recorder.samples[-1]
        self.assertTrue(sample['valid_observation'])
        self.assertEqual(sample['actual_raw'], 2030)
        self.assertFalse(sample['calibration_valid'])
        self.assertEqual(sample['source_id_kind'], 'frame_sequence_not_player_identity')

    def test_stale_precommand_and_lost_faces_never_become_measurement(self):
        for face in (dict(status='LOST'), self.face(.8), self.face(1.5)):
            recorder = ProbeObservation()
            self.request(recorder)
            for now in (3., 3.1, 3.2):
                recorder.observe(now, self.rows(), face, 'READY')
            self.assertEqual(recorder.samples, [])
            recorder.observe(12., self.rows(), face, 'READY')
            self.assertFalse(recorder.samples[-1]['valid_observation'])

    def test_no_false_capture_when_motor_has_not_reached_reviewed_tolerance(self):
        recorder = ProbeObservation()
        self.request(recorder)
        for now in (3., 3.1, 3.2):
            recorder.observe(now, self.rows(position=1997), self.face(now), 'READY')
        self.assertEqual(recorder.samples, [])

    def test_superseded_requests_are_labeled_and_records_bounded(self):
        recorder = ProbeObservation()
        for n in range(12):
            self.request(recorder, float(n))
        self.assertEqual(len(recorder.samples), 8)
        self.assertEqual(recorder.samples[-1]['reason'], 'superseded_before_settled_observation')

    def test_saved_rows_are_copied_and_fault_does_not_count_as_valid(self):
        recorder = ProbeObservation()
        self.request(recorder)
        rows = self.rows()
        for now in (3., 3.1, 3.2, 3.3, 3.4):
            recorder.observe(now, rows, self.face(now), 'READY')
        rows[3]['position_raw'] = 100
        self.assertEqual(recorder.samples[-1]['rows'][3]['position_raw'], 2030)
        self.request(recorder, 4.)
        recorder.observe(4.1, rows, self.face(4.1), 'FAULT')
        self.assertFalse(recorder.samples[-1]['valid_observation'])

    def test_frame_captured_during_motion_does_not_become_settled_evidence(self):
        recorder = ProbeObservation()
        self.request(recorder, .5)
        face = self.face(2.95)  # captured 2.85, while motor still moves
        recorder.observe(2.95, self.rows(moving=1), face, 'READY')
        for now in (3., 3.05, 3.1):
            recorder.observe(now, self.rows(), face, 'READY')
        self.assertEqual(recorder.samples, [])
        for now in (3.2, 3.3, 3.4):
            recorder.observe(now, self.rows(), self.face(now), 'READY')
        self.assertTrue(recorder.samples[-1]['valid_observation'])
    def test_pitch_probe_records_id5_instead_of_id4(self):
        recorder=ProbeObservation()
        recorder.request(dict(time_s=1.,joint_id=5,target_raw=2744,base_raw=2710))
        rows=self.rows(position=2000);rows[4]['position_raw']=2741
        for now in (3.,3.1,3.2,3.3,3.4):
            recorder.observe(now,rows,self.face(now),'READY')
        self.assertTrue(recorder.samples[-1]['valid_observation'])
        self.assertEqual(recorder.samples[-1]['actual_raw'],2741)
        self.assertEqual(recorder.samples[-1]['joint_id'],5)
    def test_body_record_selects_actual_id2_or3(self):
        for joint in (2,3):
            recorder=ProbeObservation()
            recorder.request(dict(time_s=1.,joint_id=joint,target_raw=2034,base_raw=2000))
            rows=self.rows(position=1997);rows[joint-1]['position_raw']=2033
            for now in (3.,3.1,3.2,3.3,3.4):recorder.observe(now,rows,self.face(now),'READY')
            self.assertEqual(recorder.samples[-1]['actual_raw'],2033)
            self.assertEqual(recorder.samples[-1]['joint_id'],joint)


if __name__ == '__main__': unittest.main()
