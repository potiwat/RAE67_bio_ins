import unittest
from types import SimpleNamespace as NS
from normal_gaze_motor import NormalGaze
from .probe_feedback import install

class Tests(unittest.TestCase):
 def fixture(self):
  normal={i:2000 for i in range(1,6)};normal[4]=1997
  rows=[dict(id=i,mode=0,status_raw=0,torque_raw=1,position_raw=normal[i],speed_raw=0,moving_raw=0)for i in normal];rows[3]['position_raw']=1954
  c=NormalGaze(NS(snapshot=lambda:rows),normal,normal);c.state='READY';c.last_tick=0
  c.pose_route_windows={i:(1900,2100)for i in normal};c.pose_route_windows[4]=(1907,1951)
  errors=[];c.hold=lambda error,**kw:errors.append(error)
  p=NS(active=True,sid=4,io=NS(prepared=True,window=(1907,1997)),phase='PROBING')
  a=NS(m=NS(controller=c,operator_stopped=True),core=NS(phase='WAIT_CLEARANCE'),auto_id1=p,stop_writer=None)
  install(a);return c,a,rows,errors
 def test_real_controller_tick_accepts_reviewed_probe_beyond_old_emotion_window(self):
  c,a,rows,errors=self.fixture();c.tick(1.);self.assertEqual(c.state,'READY');self.assertEqual(errors,[])
  self.assertEqual(c.feedback_window(2),(1900,2100));self.assertEqual(c.feedback_window(4),(1907,1997))
 def test_probe_scope_ends_before_return_and_does_not_hide_native_or_other_axis_fault(self):
  for fault in ('outside_probe','mode','other_axis','scope_ends'):
   c,a,rows,errors=self.fixture()
   if fault=='outside_probe':rows[3]['position_raw']=1998
   if fault=='mode':rows[3]['mode']=1
   if fault=='other_axis':rows[1]['position_raw']=2101
   if fault=='scope_ends':a.core.phase='RETURNING'
   c.tick(1.);self.assertEqual(c.state,'FAULT');self.assertTrue(errors)
 def test_h_and_q_keep_already_verified_probe_hold_bounds_for_cleanup(self):
  from .native_stop import GroupStop
  for phase in ('STOPPING','CLOSED'):
   c,a,rows,errors=self.fixture();a.m.bus=c.bus;a.auto_id1.active=False;a.auto_id1.io.restored=True;a.auto_id1.phase='CLOSED';a.core.phase=phase
   a.stop_writer=NS(verified=True,bus=c.bus,windows={i:((1907,1997)if i==4 else(1900,2100))for i in range(1,6)})
   # Same comprehension used by a new native group stop during H/Q.
   stop=GroupStop({i:c.feedback_window(i)for i in range(1,6)})
   self.assertTrue(stop.windows[4][0]<=1954<=stop.windows[4][1])
   c.tick(1.);self.assertEqual(c.state,'READY');self.assertEqual(errors,[])
 def test_authorized_normal_constructor_keeps_proven_source_during_operator_flag_change(self):
  c,a,rows,errors=self.fixture();a.m.operator_stopped=False;a.return_dispatch=True;a.auto_id1.active=False;a.auto_id1.io.restored=True
  a.m.bus=c.bus;a.stop_writer=NS(verified=True,bus=c.bus,windows={i:((1907,1997)if i==4 else(1800,2100))for i in range(1,6)})
  rows[1]['position_raw']=1850
  # handle_state_key(n) clears operator_stopped before PoseRoute snapshots.
  c.tick(1.);self.assertEqual(c.state,'READY');self.assertEqual(errors,[])
  a.return_dispatch=False
  self.assertEqual(c.feedback_window(4),(1907,1951))
