import unittest
from types import SimpleNamespace as NS
from .restart_settle import settle_snapshot,restart_scope,wrap_start

def rows(speed=0,delta=0):
 return [dict(id=i,mode=0,status_raw=0,torque_raw=1,goal_raw=2000,internal_target_raw=2000,position_raw=2000+delta,speed_raw=speed if i==1 else 0,moving_raw=0)for i in range(1,6)]

class Tests(unittest.TestCase):
 def clock(self):
  c=NS(t=0.);return c,lambda:c.t,lambda dt:setattr(c,'t',c.t+dt)
 def test_quantized_speed_sample_waits_for_real_two_idle_snapshots(self):
  c,now,wait=self.clock();samples=[rows(32818,1),rows(0,1),rows(0,1)];calls=[]
  def read():calls.append(1);return samples.pop(0)
  out=settle_snapshot(read,{i:2000 for i in range(1,6)},{i:2000 for i in range(1,6)},now,wait,lambda:False)
  self.assertEqual(len(calls),3);self.assertEqual(out[0]['speed_raw'],0)
 def test_fault_changed_goal_and_travel_fail_without_retry(self):
  for change in ({'status_raw':1},{'goal_raw':2001},{'position_raw':2003},{'torque_raw':0}):
   c,now,wait=self.clock();a=rows();a[0].update(change)
   with self.subTest(change=change),self.assertRaises(RuntimeError):settle_snapshot(lambda:a,{i:2000 for i in range(1,6)},{i:2000 for i in range(1,6)},now,wait,lambda:False)
   self.assertEqual(c.t,0.)
 def test_persistent_motion_timeout_and_cancellation_never_succeed(self):
  c,now,wait=self.clock()
  with self.assertRaises(RuntimeError):settle_snapshot(lambda:rows(50),{i:2000 for i in range(1,6)},{i:2000 for i in range(1,6)},now,wait,lambda:False)
  self.assertLessEqual(c.t,.251)
  with self.assertRaises(RuntimeError):settle_snapshot(lambda:rows(),{i:2000 for i in range(1,6)},{i:2000 for i in range(1,6)},now,wait,lambda:True)
 def test_wrapper_only_applies_inside_verified_restart_scope(self):
  c,now,wait=self.clock();calls=[];bus=NS(snapshot=lambda:(calls.append(1)or rows()))
  controller=NS(bus=bus,origin={i:2000 for i in range(1,6)})
  wrapped=wrap_start(lambda self,*a,**kw:self.bus.snapshot(),now,wait,lambda:False)
  wrapped(controller,0.);self.assertEqual(len(calls),1)
  original=bus.snapshot
  with restart_scope({i:2000 for i in range(1,6)}):wrapped(controller,0.)
  self.assertEqual(len(calls),3);self.assertIs(bus.snapshot,original)


class ActualStartTests(unittest.TestCase):
 def test_original_controller_start_rechecks_transient_without_early_goal_writes(self):
  from normal_gaze_motor import NormalGaze
  class Bus:
   def __init__(self):self.n=0;self.writes=[]
   def snapshot(self):
    self.n+=1;return rows(32818,1)if self.n==3 else rows(0,1)
   def read(self,i,address,count):return {18:12,64:0,42:2000,46:600,41:1}[address].to_bytes(count,'little')
   def write(self,i,address,data):self.writes.append((self.n,i,address,bytes(data)))
  b=Bus();c=NS(t=0.);now=lambda:c.t;wait=lambda dt:setattr(c,'t',c.t+dt)
  motor=NormalGaze(b,{i:2000 for i in range(1,6)},{i:2000 for i in range(1,6)},manual_tuning=True,tracking_speed=600,tracking_acceleration=3,yaw_range_deg=30,motion_speed=600)
  wrapped=wrap_start(NormalGaze.start,now,wait,lambda:False)
  with restart_scope({i:2000 for i in range(1,6)}):wrapped(motor,0.)
  self.assertEqual(motor.state,'NORMAL_STARTUP');self.assertGreaterEqual(b.n,5)
  self.assertTrue(all(n>=5 for n,i,a,data in b.writes));self.assertTrue(all(a==42 for n,i,a,data in b.writes))
