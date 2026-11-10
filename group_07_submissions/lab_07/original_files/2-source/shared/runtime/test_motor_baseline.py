import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import motor_baseline as m

def feedback(pos=2000,torque=0,status=0,moving=0):
 return dict(position_raw=pos,torque_raw=torque,status_raw=status,moving_raw=moving,speed_raw=0,voltage_V=7.2,temperature_C=30)

class FakeBus:
 def __init__(self):
  self.pos=2000;self.torque=0;self.status=0;self.calls=[];self.registers={18:12,33:0,40:0,41:0,42:0,46:0,64:0};self.closed=False
 def snapshot(self):
  return [dict(id=i,position_raw=self.pos if i==1 else 2500,mode=0,torque_raw=self.torque if i==1 else 0,status_raw=0) for i in range(1,6)]
 def read(self,sid,addr,count):return self.registers[addr].to_bytes(count,'little')
 def feedback(self):return feedback(self.pos,self.torque,self.status)
 def write_register(self,addr,data):
  val=int.from_bytes(data,'little');self.calls.append((addr,val));self.registers[addr]=val
  if addr==40:self.torque=val
 def hold_actual(self):self.write_register(42,self.pos.to_bytes(2,'little'));return self.feedback()
 def close(self):self.closed=True

class PacketTests(unittest.TestCase):
 def test_only_id1_ram_and_minimum_nonzero_limits(self):
  for sid,addr,data in [(2,40,b'\1'),(254,40,b'\1'),(1,33,b'\0'),(1,46,b'\0\0'),(1,41,b'\0'),(1,40,b'\x80')]:
   with self.assertRaises(ValueError):m.write_packet(sid,addr,data,(2000,2034))
 def test_goal_window_checksum(self):
  for v in (0,1999,2035,4096):
   with self.assertRaises(ValueError):m.write_packet(1,42,v.to_bytes(2,'little'),(2000,2034))
  p=m.write_packet(1,42,(2034).to_bytes(2,'little'),(2000,2034))
  self.assertEqual(p[2:5],bytes([1,5,3]));self.assertEqual(sum(p[2:])&255,255)
 def test_invalid_trial_parameters(self):
  for v in [0,-3,4,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):m.TrialConfig(v,1,1)
  with self.assertRaises(ValueError):m.TrialConfig(3,0,1)
  with self.assertRaises(ValueError):m.TrialConfig(3,1,0)

class SessionTests(unittest.TestCase):
 def test_fresh_hold_precedes_enable(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm()
  self.assertEqual(c.base,2000);self.assertEqual(c.target,2034)
  self.assertLess(b.calls.index((42,2000)),b.calls.index((40,1)))
  self.assertEqual(b.registers[41],1);self.assertEqual(b.registers[46],1)
 def test_one_direct_goal_each_leg_then_hold(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.begin(0)
  self.assertEqual(b.calls[-1],(42,2034))
  b.pos=2034
  for t in [.1,.2,.3]:c.tick(t)
  self.assertEqual(b.calls[-1],(42,2000))
  b.pos=2000
  for t in [.4,.5,.6]:c.tick(t)
  self.assertEqual(c.state,'HOLDING');self.assertEqual(b.torque,1)
  self.assertEqual([v for a,v in b.calls if a==42],[2000,2034,2000])
 def test_stop_holds_actual_without_releasing(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.begin(0);b.pos=2010;c.stop('operator')
  self.assertEqual(b.calls[-1],(42,2010));self.assertEqual(b.torque,1);self.assertEqual(c.state,'STOPPED_HOLDING')
 def test_fault_stops_without_torque_off(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.begin(0);b.pos=2010;b.status=4;c.tick(.2)
  self.assertIn('STOPPED',c.state);self.assertNotIn((40,0),b.calls)
 def test_read_failure_never_claims_successful_hold(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.begin(0)
  def fail():raise TimeoutError('power lost')
  b.feedback=fail;b.hold_actual=fail;c.tick(.1)
  self.assertEqual(c.state,'STOPPED_UNCONFIRMED');self.assertTrue(c.may_be_enabled)
 def test_busy_other_joint_blocks_arm_without_writes(self):
  b=FakeBus();original=b.snapshot
  def snap():
   rows=original();rows[1]['torque_raw']=1;return rows
  b.snapshot=snap;c=m.BaselineSession(b,m.TrialConfig(3,1,1))
  with self.assertRaises(RuntimeError):c.arm()
  self.assertEqual(b.calls,[])
 def test_drift_during_arming_does_not_enable(self):
  b=FakeBus();original=b.write_register
  def write(a,d):
   original(a,d)
   if a==42:b.pos=2010
  b.write_register=write;c=m.BaselineSession(b,m.TrialConfig(3,1,1))
  with self.assertRaises(RuntimeError):c.arm()
  self.assertNotIn((40,1),b.calls)
 def test_release_is_explicit(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.release()
  self.assertEqual(b.torque,0);self.assertEqual(c.state,'RELEASED')


class ActualTransportGuardTests(unittest.TestCase):
 def test_bus_refuses_enable_without_verified_hold(self):
  b=m.BaselineBus.__new__(m.BaselineBus);b.window=(2000,2034);b.enable_checked=False
  with self.assertRaises(RuntimeError):b.write_register(40,b'\1')
 def test_released_torque_is_not_reported_as_holding(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();b.torque=0;c.stop('external torque loss')
  self.assertEqual(c.state,'STOPPED_TORQUE_OFF');self.assertFalse(c.may_be_enabled)



class ArmingStateRegressionTests(unittest.TestCase):
 def test_hold_goal_is_first_before_settings_and_auto_enable_is_accounted(self):
  b=FakeBus();old=b.write_register
  def auto_enable(a,d):
   old(a,d)
   if a==42:b.torque=1;b.registers[40]=1
  b.write_register=auto_enable;c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm()
  self.assertEqual(b.calls[0],(42,2000));self.assertEqual(c.state,'ARMED');self.assertTrue(c.may_be_enabled)
 def test_existing_verified_hold_can_resume(self):
  b=FakeBus();b.torque=1;b.registers[40]=1;b.registers[42]=2000
  c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();self.assertEqual(c.state,'ARMED')
 def test_far_active_goal_is_not_rebased(self):
  b=FakeBus();b.torque=1;b.registers[40]=1;b.registers[42]=1000
  c=m.BaselineSession(b,m.TrialConfig(3,1,1))
  with self.assertRaises(RuntimeError):c.arm()
  self.assertEqual(b.calls,[])
 def test_idle_hold_monitor_does_not_accumulate_motion_samples(self):
  b=FakeBus();c=m.BaselineSession(b,m.TrialConfig(3,1,1));c.arm();c.state='HOLDING';c.goal=c.base
  for i in range(100):c.tick(i*.1)
  self.assertEqual(len(c.samples),0)
if __name__=='__main__':unittest.main()
