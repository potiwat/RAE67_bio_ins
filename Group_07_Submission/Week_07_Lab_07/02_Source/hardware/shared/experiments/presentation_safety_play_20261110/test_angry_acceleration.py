import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from acceleration_restore import AccelerationRestore
from .angry_acceleration import acceleration_route


class Base:
    def __init__(self):
        self.pending_sync_goals={2:2633,3:2950};self.range_phase='advance';self.safety_hold=False
        self.c=SimpleNamespace(bus=SimpleNamespace(acceleration_restore=AccelerationRestore(),
            write=Mock(),read=Mock(return_value=b'\3')),normal_tolerances={2:34,3:34})
    def _cancelled(self):return False
    def commit_pending_head(self,goal):self.pending_sync_goals=None;return True
    def step(self,rows):pass
    def cancel(self):pass


class Tests(unittest.TestCase):
    def test_only_acc3_written_and_restore_is_deferred_until_stationary(self):
        r=acceleration_route(Base)();r.commit_pending_head(2700)
        self.assertEqual([x.args for x in r.c.bus.write.call_args_list],[(2,41,b'\3'),(3,41,b'\3')])
        r.range_phase='tilt';r.step([])
        g=r.c.bus.acceleration_restore
        self.assertEqual(g.pending,{2:1,3:1});self.assertFalse(r.trial_acc_active)
        self.assertEqual(r.c.bus.write.call_count,2)
        rows=[dict(id=i,goal_raw=2800,position_raw=2800,mode=0,status_raw=0,torque_raw=1,speed_raw=0,moving_raw=0)for i in (2,3)]
        g.service(rows,r.c.bus.write);g.service(rows,r.c.bus.write)
        self.assertEqual(r.c.bus.write.call_count,2)
        g.service(rows,r.c.bus.write)
        self.assertEqual([x.args for x in r.c.bus.write.call_args_list][-2:],[(2,41,b'\1'),(3,41,b'\1')])

    def test_cancelled_launch_does_not_write_acceleration(self):
        r=acceleration_route(Base)();r._cancelled=lambda:True;r.commit_pending_head(2700)
        r.c.bus.write.assert_not_called()

    def test_partial_profile_failure_still_requests_restore_for_touched_axes(self):
        r=acceleration_route(Base)()
        r.c.bus.write.side_effect=OSError('injected write failure')
        with self.assertRaises(OSError):r.commit_pending_head(2700)
        r.cancel()
        self.assertEqual(r.c.bus.acceleration_restore.pending,{2:1})
        self.assertFalse(r.trial_acc_active)


if __name__=='__main__':unittest.main()
