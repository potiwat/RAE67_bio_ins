import unittest
import test_automatic_fsm as fixture


class Tests(unittest.TestCase):
    def test_normal_follows_actual_neck_return_without_extra_five_second_wait(self):
        f=fixture.EngagementAdapterTests();m,b,s=f.engaged_motor();c=m.controller
        f.at(m,s,20.1,distance_cm=70.)
        route=c.pose_route;b.pos=dict(route.stage_target);route.phase='complete'
        c.behavior_joint_windows=dict(route.final_windows);c.behavior_joint_allowances={}
        m._finish_button_route()
        f.at(m,s,21.)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        m.now=lambda:22.2;m._service_interested_roll();c.last_rows=b.snapshot()
        f.at(m,s,22.21)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested','Must finish the physical neck return first')
        b.pos[4]=c.normal[4];c.last_rows=b.snapshot()
        c.last_rows[3]['moving_raw']=1
        f.at(m,s,22.23)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')
        c.last_rows=b.snapshot();f.at(m,s,22.25)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.assertEqual(m.behavior_trial,'normal_transition')
        self.assertEqual(m.automatic_fsm.fsm.last_winner['source_id'],'interested_gesture_complete')


if __name__=='__main__':unittest.main()
