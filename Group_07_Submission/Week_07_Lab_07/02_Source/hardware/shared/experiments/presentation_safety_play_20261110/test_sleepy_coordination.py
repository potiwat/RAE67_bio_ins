import unittest
from unittest.mock import patch
from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
from bio_inspire.runtime import sleepy_trial
from bio_inspire.runtime.three_state_behavior import handle_state_key
from .sleepy_coordination import sleepy_setter,coordinated_driver
from . import test_sleepy_smooth as fixtures


class Tests(unittest.TestCase):
    def motor(self):
        # Build the same approved profile, but intercept the first head endpoint.
        from bio_inspire.runtime import test_deep_sleepy
        m,b=test_deep_sleepy.DeepSleepyTests().motor();c=m.controller
        c.sleepy_native_fold_enabled=True;c.sleepy_native_fold_degrees=12;c.sleepy_native_fold_speed_raw=1
        c.rhythm_base_reference={i:c.normal[i]for i in (2,3)}
        c.last_pitch_goal=c.normal[5];b.reg[2][42]=c.normal[2]+13
        with patch.object(sleepy_trial,'set_sleepy_trial',sleepy_setter(sleepy_trial.set_sleepy_trial)):
            handle_state_key(m,ord('s'))
        c.last_rows=b.snapshot()
        for r in c.last_rows:r['goal_raw']=b.reg[r['id']][42]
        return m,b

    def test_head_starts_from_saved_command_and_native_caps_are_unchanged(self):
        m,b=self.motor();c=m.controller
        self.assertEqual(b.reg[5][42],c.normal[5])
        self.assertEqual(b.reg[5][46],25)
        d=coordinated_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
        d.step(m,20.)
        self.assertEqual(b.reg[3][42],c.sleepy_entry_positions[3])
        self.assertEqual(b.reg[3][46],1)

    def test_three_axes_share_endpoint_time_without_new_offsets(self):
        m,b=self.motor();c=m.controller
        d=coordinated_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.);trace=[]
        for k in range(161):
            d.step(m,20+k*.05)
            trace.append({i:b.reg[i][42]for i in (2,3,5)})
            c.last_rows=b.snapshot()
        self.assertEqual(trace[-1][2],c.sleepy_body_reference[2])
        self.assertEqual(trace[-1][3],c.sleepy_body_reference[3]+137)
        self.assertEqual(trace[-1][5],c.sleepy_coordinated_head['target'])
        for sid in (2,3,5):
            values=[q[sid]for q in trace]
            self.assertEqual(values,sorted(values,reverse=values[0]>values[-1]))
            self.assertLessEqual(max(abs(a-b)for a,b in zip(values,values[1:])),4)

    def test_stop_preempts_trajectory_and_restores_composer(self):
        import motion_composer
        m,b=self.motor();d=coordinated_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
        d.step(m,20.);m.operator_stopped=True;b.calls.clear();original=motion_composer.compose_goals
        d.step(m,21.)
        self.assertEqual(b.calls,[]);self.assertIs(motion_composer.compose_goals,original)
        self.assertEqual(d.active_joint_ids,(2,3))


if __name__=='__main__':unittest.main()
