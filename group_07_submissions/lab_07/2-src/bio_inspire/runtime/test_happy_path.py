import hashlib
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared/runtime'))
from happy_path import HappyReferencePath, CpgPhaseProgress, CalibrationRequired, build_symmetric_path
from body_rhythm import BodyRhythm


class HappyPathTests(unittest.TestCase):
    def test_player_view_left_right_and_height_symmetry(self):
        path = HappyReferencePath()
        for n in range(101):
            a, b = path.sample(n / 200), path.sample(.5 + n / 200)
            self.assertAlmostEqual(a.position[0], -b.position[0])
            self.assertAlmostEqual(a.position[1], b.position[1])
        self.assertLess(path.sample(.125).position[0], 0)
        self.assertGreater(path.sample(.625).position[0], 0)
        self.assertGreater(path.sample(.125).position[1], path.sample(.375).position[1])

    def test_closed_path_position_and_tangent_continuity(self):
        path = HappyReferencePath()
        a, b = path.sample(0.), path.sample(1.)
        self.assertEqual(a.position, b.position)
        self.assertEqual(a.tangent, b.tangent)
        for boundary in (.5, 1.):
            a, b = path.sample(boundary - 1e-8), path.sample(boundary + 1e-8)
            for name in ('position', 'tangent', 'curvature_vector'):
                for left, right in zip(getattr(a, name), getattr(b, name)):
                    self.assertAlmostEqual(left, right, delta=1e-4)

    def test_reference_cannot_emit_raw_motor_goals_without_calibration(self):
        point = HappyReferencePath().sample(.25)
        self.assertEqual(point.units, 'dimensionless')
        self.assertEqual(point.frame, 'player_view_reference')
        self.assertIsNone(point.motor_goals)
        self.assertFalse(point.hardware_validated)
        for calibration in (None, {}, {'verified': False}, {'verified': True}):
            with self.assertRaises(CalibrationRequired):
                build_symmetric_path([], None, calibration)

    def test_raw_teaching_poses_unchanged(self):
        source = ROOT / 'shared/hardware/pose_observations_20261102.json'
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        for n in range(100):
            HappyReferencePath().sample(n / 100)
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_phase_follows_existing_so2_without_restart_or_waypoint_stops(self):
        oscillator = BodyRhythm(phi=.1, time_scale=.5)
        phase = CpgPhaseProgress()
        values = []
        for n in range(1201):
            now = n / 20
            oscillator.advance(now, active=not 8 <= now <= 12, exclusive=8 <= now <= 12)
            values.append(phase.advance(oscillator.o1, oscillator.o2, oscillator.updates, now))
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))
        self.assertGreater(values[240], values[160])
        self.assertGreater(values[-1] - values[0], 8.)
        self.assertGreater(math.hypot(*HappyReferencePath().sample(.5).tangent), 0)

    def test_phase_rejects_stale_clock_missing_updates_and_invalid_pair(self):
        phase = CpgPhaseProgress()
        phase.advance(1., 0., 0, 0.)
        with self.assertRaises(ValueError): phase.advance(1., 0., 0, -.1)
        with self.assertRaises(ValueError): phase.advance(.9, -.1, 3, .3)
        for pair in ((0., 0.), (float('nan'), 0.)):
            with self.assertRaises(ValueError): CpgPhaseProgress().advance(*pair, 0, 0.)
        for progress in (True, float('inf'), -.1):
            with self.assertRaises(ValueError): HappyReferencePath().sample(progress)


if __name__ == '__main__': unittest.main()


class JointLoopPreviewTests(unittest.TestCase):
    def preview(self):
        import json
        from happy_path import JointLoopPreview
        return JointLoopPreview.from_template(json.loads((ROOT/'bio_inspire/hardware/happy_loop_template.json').read_text()))
    def test_preview_has_mirrored_yaw_and_same_body_heights_both_lobes(self):
        loop=self.preview()
        for n in range(101):
            a,b=loop.sample(n/200),loop.sample(.5+n/200)
            self.assertAlmostEqual(a[0]+b[0],2*loop.center_yaw)
            self.assertAlmostEqual(a[1],b[1]);self.assertAlmostEqual(a[2],b[2])
    def test_both_body_joints_follow_teaching_direction_together(self):
        loop=self.preview();a,b=loop.sample(.125),loop.sample(.375)
        self.assertLess(a[1],b[1]);self.assertLess(a[2],b[2])
    def test_cycle_is_continuous_at_wrap_and_uses_no_head_joint_commands(self):
        loop=self.preview()
        self.assertEqual(len(loop.sample(0)),3)
        for a,b in zip(loop.sample(0),loop.sample(1)):self.assertAlmostEqual(a,b)
        h=1e-5
        left=[(a-b)/h for a,b in zip(loop.sample(1),loop.sample(1-h))]
        right=[(a-b)/h for a,b in zip(loop.sample(h),loop.sample(0))]
        for a,b in zip(left,right):self.assertAlmostEqual(a,b,delta=.2)
    def test_template_is_not_mutated_and_invalid_data_rejected(self):
        import json
        from happy_path import JointLoopPreview
        data=json.loads((ROOT/'bio_inspire/hardware/happy_loop_template.json').read_text());before=json.dumps(data,sort_keys=True)
        loop=JointLoopPreview.from_template(data)
        data['upper_body_raw']['2']=float('nan')
        self.assertTrue(all(math.isfinite(v) for v in loop.sample(.1)))
        with self.assertRaises(ValueError):JointLoopPreview.from_template(data)
        self.assertNotEqual(json.dumps(data,sort_keys=True),before)
    def test_preview_cannot_be_used_as_a_physical_path(self):
        loop=self.preview()
        self.assertFalse(loop.hardware_validated)
        with self.assertRaises(CalibrationRequired):build_symmetric_path(loop,None,None)
