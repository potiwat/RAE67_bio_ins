import unittest
import test_small_happy_trial as fixture
from small_happy_trial import SmallHappyTrial
from three_state_behavior import _small_happy_speed,handle_state_key

class ExpandedTests(unittest.TestCase):
    def test_expanded_counterroll_and_bounds(self):
        m,b,_=fixture.Tests().fixture();m.happy_body_acceleration_raw=3
        d=SmallHappyTrial(expanded=True);values=[];requested=[]
        for n in range(601):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
            if n>100:requested.append(d.rhythm.status()['requested_targets_float']);values.append({i:b.reg[i][42]-m.controller.normal[i] for i in (1,2,3,4)})
        self.assertLess(min(q[1] for q in values),-60);self.assertGreater(max(q[1] for q in values),60)
        self.assertLess(min(q[2]-m.controller.normal[2] for q in requested),-45);self.assertGreater(max(q[2]-m.controller.normal[2] for q in requested),45)
        self.assertTrue(all(abs(q[1])<=68 and abs(q[2])<=51 and abs(q[3])<=51 and abs(q[4])<=68 for q in values))
        self.assertTrue(all((q[1]-m.controller.normal[1])*(q[4]-m.controller.normal[4])<=0 for q in requested))
        self.assertAlmostEqual(d.rhythm.status()['requested_period_s_approx'],3.8)
        m.urgent_stop.set();b.calls.clear();d.step(m,31.)
        self.assertEqual(b.calls,[])
    def test_happy1000_all5_and_restore(self):
        m,b,_=fixture.Tests().fixture();m.happy_speed_raw=1000
        _small_happy_speed(m,True)
        self.assertTrue(all(b.reg[i][46]==1000 for i in range(1,6)))
        _small_happy_speed(m,False)
        self.assertTrue(all(b.reg[i][46]==m.controller.motion_speed for i in range(1,6)))

    def test_entry_from_interested_roll_keeps_actual_path_guard(self):
        m,b,_=fixture.Tests().fixture();m.automatic_fsm_enabled=True
        m.behavior_trial='interested';m.happy_expanded_trial=True
        c=m.controller;b.pos[4]=1770;b.reg[4][42]=1860
        c.behavior_joint_windows={4:(1748,2019)};c.behavior_joint_allowances={4:0}
        c.last_rows=b.snapshot();b.calls.clear();handle_state_key(m,ord('d'))
        self.assertEqual(c.happy_roll_entry_raw,1770)
        self.assertFalse(any(i==4 and a==42 and q==c.normal[4] for i,a,q in b.calls))
        d=SmallHappyTrial(expanded=True);d.step(m,0.)
        self.assertLessEqual(c.behavior_joint_windows[4][0],1748)
        self.assertEqual(b.reg[4][42],1770)
        c.tick(c.last_tick+.1)
        self.assertNotEqual(c.state,'FAULT')

    def test_sync_retains_three_axis_packet_and_single_roll_write(self):
        m,b,_=fixture.Tests().fixture();d=SmallHappyTrial(expanded=True)
        packets=[];b.sync_position_trial=True
        def sync(goals,cancelled):
            packets.append(dict(goals))
            for i,q in goals.items():b.write(i,42,q.to_bytes(2,'little'))
            return {'status':'verified'}
        b.sync_positions=sync
        d.step(m,0.)
        b.calls.clear();m.latest_result['observation']['captured_s']=.1;d.step(m,.1)
        self.assertTrue(packets)
        self.assertTrue(all(set(p)=={1,2,3} for p in packets))
        self.assertLessEqual(sum(i==4 and a==42 for i,a,q in b.calls),1)
        m.operator_stopped=True;b.calls.clear();d.step(m,.2)
        self.assertEqual(b.calls,[])
