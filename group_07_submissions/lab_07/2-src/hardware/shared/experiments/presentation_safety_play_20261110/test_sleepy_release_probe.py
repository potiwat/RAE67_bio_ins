import unittest
from .release_plan import ReleasePlan
from .test_release_plan import row


class Tests(unittest.TestCase):
    def test_existing_clear_path_samples_do_not_truncate_at_short_normal_goal(self):
        from .sleepy_release_probe import fullspan_plan
        for goal,q in ((2849,2855),(2855,2861)):
            p=fullspan_plan(ReleasePlan)(2,goal,q,2837,(2700,2900),0.,id2_command_span=32)
            self.assertEqual(p.target,goal-32)
            self.assertEqual(p.command_excursion,32);self.assertEqual(p.excursion,16)
            self.assertEqual(p.duration,1.6)

    def test_immobile_encoder_and_excess_effort_never_pass_release(self):
        from .sleepy_release_probe import fullspan_plan
        p=fullspan_plan(ReleasePlan)(2,2855,2861,2837,(2700,2900),0.,id2_command_span=32)
        for k in range(100):
            t=k*.05;r=row(t,2861,sid=2,goal=p.goal)
            result=p.step(r,t)
            self.assertNotEqual(result['action'],'passed')
            if result['action']in('blocked','fault'):break
        r=row(0.,2861,sid=2,goal=2855);r['current_raw']=41
        p=fullspan_plan(ReleasePlan)(2,2855,2861,2837,(2700,2900),0.,id2_command_span=32)
        self.assertEqual(p.step(r,0.)['action'],'blocked')

    def test_other_axes_calibrated_context_and_reviewed_windows_unchanged(self):
        from .sleepy_release_probe import fullspan_plan
        for sid in (1,4):
            a=ReleasePlan(sid,2000,2000,2100,(1900,2200),0.)
            b=fullspan_plan(ReleasePlan)(sid,2000,2000,2100,(1900,2200),0.)
            self.assertEqual(a.target,b.target)
        p=fullspan_plan(ReleasePlan)(2,2855,2861,2837,(2830,2900),0.,id2_command_span=32)
        self.assertEqual(p.target,2830)


if __name__=='__main__':unittest.main()
