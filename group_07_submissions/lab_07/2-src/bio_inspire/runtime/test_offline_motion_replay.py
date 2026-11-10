import json
import builtins
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared/runtime'))
from offline_motion_replay import replay_motion


class ReplayTests(unittest.TestCase):
    def profile(self):
        return json.loads((ROOT / 'bio_inspire/hardware/normal_gaze_trial.json').read_text(encoding='utf-8-sig'))

    def clocks(self, seconds=24):
        return [i / 20 for i in range(seconds * 20 + 1)]

    def test_replay_never_opens_uart_or_camera(self):
        original_import = builtins.__import__
        def forbid_devices(name, *args, **kwargs):
            if name.split('.')[0] in ('serial', 'picamera2', 'libcamera', 'gpiozero', 'board', 'busio'):
                raise AssertionError(f'Device dependency imported: {name}')
            return original_import(name, *args, **kwargs)
        with patch('bio_inspire.runtime.camera_motor.open_bus', side_effect=AssertionError('UART opened')), \
             patch('normal_gaze_motor.open_bus', side_effect=AssertionError('UART opened')), \
             patch('bio_inspire.runtime.camera_motor.CameraMotor.__init__', side_effect=AssertionError('live worker opened')), \
             patch('led_ring.LedRing', side_effect=AssertionError('LED opened')), \
             patch('builtins.__import__', side_effect=forbid_devices):
            rows = replay_motion(self.profile(), [], self.clocks(4))
        self.assertTrue(any(r['controller_state'] == 'READY' for r in rows))
        self.assertTrue(all(r['actual_tick'] is None and r['actual_s'] is None for r in rows))
        self.assertEqual({r['joint_id'] for r in rows}, set(range(1, 6)))

    def test_replay_is_deterministic_with_direct_state_changes_and_stop(self):
        events = [dict(time_s=3., kind='state', state='sleepy'),
                  dict(time_s=7., kind='state', state='interested'),
                  dict(time_s=13., kind='touch', pressed=True),
                  dict(time_s=14., kind='touch', pressed=False),
                  dict(time_s=17., kind='stop')]
        rows = replay_motion(self.profile(), events, self.clocks())
        self.assertEqual(rows, replay_motion(self.profile(), events, self.clocks()))
        self.assertTrue({'normal', 'sleepy', 'interested', 'happy'} <= {r['behavior'] for r in rows})
        stopped = [r for r in rows if r['time_s'] >= 18.]
        self.assertTrue(all(r['operator_stopped'] for r in stopped))
        self.assertTrue(all(r['cpg_envelope'] == 0 for r in stopped))
        self.assertTrue(all(not r['writes'] for r in stopped))

    def test_touch_held_is_one_edge_and_keyboard_cannot_enter_happy(self):
        events = [dict(time_s=2., kind='state', state='happy'),
                  dict(time_s=3., kind='touch', pressed=True)]
        rows = replay_motion(self.profile(), events, self.clocks(8))
        self.assertFalse(any(r['behavior'] == 'happy' for r in rows if r['time_s'] < 3.))
        self.assertEqual(max(r['touch_sequence'] for r in rows), 1)
        startup = replay_motion(self.profile(), [dict(time_s=0., kind='touch', pressed=True)], self.clocks(4))
        self.assertEqual(max(r['touch_sequence'] for r in startup), 0)

    def test_stale_face_is_not_presented_as_fresh_and_phase_keeps_advancing(self):
        rows = replay_motion(self.profile(), [dict(time_s=2., kind='face', status='TRACKING',
                                                  error_xy=[0., .8], age_s=1.)], self.clocks(5))
        stale = [r for r in rows if r['time_s'] > 2.]
        self.assertTrue(all(not r['face_fresh'] for r in stale))
        self.assertGreater(stale[-1]['cpg_updates'], stale[0]['cpg_updates'])

    def test_single_fresh_observation_ages_without_new_camera_sample(self):
        rows = replay_motion(self.profile(), [dict(time_s=2., kind='face', status='TRACKING',
                                                  error_xy=[.2, .2], age_s=0.)], self.clocks(4))
        self.assertTrue(all(r['face_fresh'] for r in rows if r['time_s'] == 2.))
        self.assertTrue(all(not r['face_fresh'] for r in rows if r['time_s'] > 2.5))
        samples = [r for r in rows if r['time_s'] >= 2.]
        self.assertEqual(len({r['face_captured_s'] for r in samples}), 1)
        self.assertEqual(len({r['face_source_id'] for r in samples}), 1)

    def test_all_directed_behavior_pairs_at_three_phase_offsets(self):
        states = ('normal', 'interested', 'sleepy', 'happy')
        def request(state, when):
            if state == 'happy':
                return [dict(time_s=when, kind='touch', pressed=True),
                        dict(time_s=when+1., kind='touch', pressed=False)]
            return [dict(time_s=when, kind='state', state=state)]
        for source in states:
            for target in states:
                if source == target:
                    continue
                for phase_offset in (0., .85, 2.65):
                    with self.subTest(source=source, target=target, phase=phase_offset):
                        when = 9. + phase_offset
                        events = ([] if source == 'normal' else request(source, 2.)) + request(target, when)
                        rows = replay_motion(self.profile(), events, self.clocks(18))
                        self.assertFalse(any(r['controller_state'] == 'FAULT' for r in rows))
                        self.assertEqual(rows[-1]['behavior'], target)
                        if target != 'normal':
                            self.assertFalse(any(r['behavior'] == 'normal_transition' for r in rows if r['time_s'] >= when))

    def test_invalid_inputs_fail_before_replay(self):
        for clocks in ([0., 0.], [1., 0.], [0., float('nan')]):
            with self.assertRaises(ValueError):
                replay_motion(self.profile(), [], clocks)
        with self.assertRaises(ValueError):
            replay_motion(self.profile(), [dict(time_s=1., kind='state', state='invented')], self.clocks(2))


if __name__ == '__main__':
    unittest.main()
