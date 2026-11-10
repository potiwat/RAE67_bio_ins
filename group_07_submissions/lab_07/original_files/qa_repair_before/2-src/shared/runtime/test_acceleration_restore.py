import unittest
from acceleration_restore import AccelerationRestore

class Tests(unittest.TestCase):
    def test_pinned_awake_floor_waits_for_release_and_three_new_stationary_samples(self):
        g=AccelerationRestore();g.pin(2,8,34);g.defer(2,1);writes=[]
        row=dict(id=2,position_raw=2837,goal_raw=2837,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1)
        for _ in range(10):g.service([row],lambda *v:writes.append(v))
        self.assertEqual(writes,[])
        g.unpin(2,1)
        for _ in range(2):g.service([row],lambda *v:writes.append(v))
        self.assertEqual(writes,[])
        g.service([row],lambda *v:writes.append(v));self.assertEqual(writes,[(2,41,b'\1')])
    def test_repin_interrupts_sleep_restoration_without_late_low_write(self):
        g=AccelerationRestore();g.pin(5,6);g.unpin(5,1);writes=[]
        row=dict(id=5,position_raw=2696,goal_raw=2696,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1)
        for _ in range(2):g.service([row],lambda *v:writes.append(v))
        g.pin(5,6)
        for _ in range(5):g.service([row],lambda *v:writes.append(v))
        self.assertEqual(writes,[]);self.assertNotIn(5,g.pending)
    def test_moving_exit_keeps_braking_acceleration_and_restores_after_three_arrivals(self):
        g=AccelerationRestore();g.protect(4,12)
        self.assertTrue(g.defer(4,1));writes=[]
        row=dict(id=4,position_raw=2350,goal_raw=1997,speed_raw=200,moving_raw=1,status_raw=0,mode=0,torque_raw=1)
        for _ in range(4):g.service([row],lambda i,a,v:writes.append((i,a,v)))
        self.assertEqual(writes,[])
        row.update(position_raw=1999,speed_raw=0,moving_raw=0)
        for _ in range(2):g.service([row],lambda i,a,v:writes.append((i,a,v)))
        self.assertEqual(writes,[])
        g.service([row],lambda i,a,v:writes.append((i,a,v)))
        self.assertEqual(writes,[(4,41,b'\1')]);self.assertFalse(g.defer(4,1))
    def test_preemption_new_destination_resets_settling_and_reentry_cancels(self):
        g=AccelerationRestore();g.protect(4,12);g.defer(4,1);writes=[]
        row=dict(id=4,position_raw=1997,goal_raw=1997,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1)
        for _ in range(2):g.service([row],lambda *v:writes.append(v))
        row['goal_raw']=2100;g.service([row],lambda *v:writes.append(v));self.assertEqual(writes,[])
        g.protect(4,12);self.assertFalse(g.pending)
    def test_no_protection_and_fault_never_trigger_restore(self):
        g=AccelerationRestore();self.assertFalse(g.defer(4,1));g.protect(4,12);g.defer(4,1)
        row=dict(id=4,position_raw=1997,goal_raw=1997,speed_raw=0,moving_raw=0,status_raw=1,mode=0,torque_raw=1)
        writes=[]
        for _ in range(5):g.service([row],lambda *v:writes.append(v))
        self.assertEqual(writes,[])

    def test_accepted_34_tick_joint_residual_restores_before_motion_resumes(self):
        g=AccelerationRestore();g.protect(3,8,tolerance=34);g.defer(3,1);writes=[]
        row=dict(id=3,position_raw=2774,goal_raw=2746,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1)
        for _ in range(3):g.service([row],lambda *v:writes.append(v))
        self.assertEqual(writes,[(3,41,b'\1')]);self.assertFalse(g.pending)
