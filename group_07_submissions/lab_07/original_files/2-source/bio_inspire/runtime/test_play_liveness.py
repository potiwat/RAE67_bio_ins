"""Reproductions of silent waits, using existing fake motor/input fixtures."""
import unittest
import test_automatic_fsm as fixture
from button_look import POSE
from pose_route import PoseRoute


class Tests(unittest.TestCase):
    def test_legacy_direct_lean_without_face_has_an_exit(self):
        f=fixture.EngagementAdapterTests();m,b,s=f.engaged_motor();c=m.controller
        c.interest_head_tracking=True;c.interest_finish_without_face=False
        c.interest_native_body_speed_raw=None;c.interest_gaze_priority=False;c.face_ready_for_interest=False
        f.at(m,s,20.1,distance_cm=70.)
        for n in range(1,160):
            now=20.1+n*.1;b.pos={i:b.reg[i][42] for i in b.pos}
            c.tick(now);f.at(m,s,now)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.assertNotEqual(c.state,'FAULT')

    def test_alternating_moving_flag_cannot_reset_settling_forever(self):
        m,b,s=fixture.EngagementAdapterTests().engaged_motor();c=m.controller
        c.pose_route=PoseRoute(c,c.normal,c.normal,normal_only=True)
        original=b.snapshot;flag=[0]
        def snapshot():
            rows=original();rows[1]['moving_raw']=flag[0];return rows
        b.snapshot=snapshot
        for n in range(60):
            flag[0]=n%2;c.tick(20.1+n*.1)
            if c.state=='FAULT':break
        self.assertEqual(c.state,'FAULT')

    def test_post_glance_face_wait_starts_interested_exit_timer(self):
        f=fixture.EngagementAdapterTests();m,b,s=f.engaged_motor();c=m.controller
        c.interest_head_tracking=True;c.interest_finish_without_face=False;c.face_ready_for_interest=False
        m.physical_button.poll.return_value=True;f.at(m,s,20.1)
        m.physical_button.poll.return_value=False
        for n in range(1,160):
            now=20.1+n*.1
            route=c.pose_route
            if route.phase=='look':b.pos=dict(POSE)
            elif route.phase=='return':b.pos=dict(route.return_pose)
            c.tick(now);f.at(m,s,now)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.assertNotEqual(c.state,'FAULT')

    def test_unreachable_normal_endpoint_does_not_wait_forever(self):
        m,b,s=fixture.EngagementAdapterTests().engaged_motor();c=m.controller
        c.behavior_joint_windows={2:(c.normal[2]-136,c.normal[2]+34)}
        b.pos[2]=c.normal[2]-c.normal_tolerances[2]-1
        c.pose_route=PoseRoute(c,c.normal,c.normal,normal_only=True)
        c.tick(20.1);c.tick(24.9)
        self.assertEqual(c.state,'READY')
        c.tick(25.2)
        self.assertEqual(c.state,'FAULT')
        self.assertIn('settle',c.last_error.lower())
        self.assertEqual(c.pose_route.phase,'cancelled')
        self.assertFalse(any(address==40 and value==0 for _,address,value in b.calls))


if __name__=='__main__':unittest.main()
