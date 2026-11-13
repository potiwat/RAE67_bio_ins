import unittest
from pathlib import Path
from .id2_small_motion import SmallMotionPlan
class Tests(unittest.TestCase):
 def test_goals_are_pinned_small_and_change_only_one_tick(self):
  p=SmallMotionPlan(2837,2841,(2815,2850));previous=2837;seen=set()
  for k in range(400):
   r=p.step(k*.05);g=r['goal'];self.assertLessEqual(abs(g-previous),1);self.assertTrue(2815<=g<=2850);self.assertLessEqual(abs(g-2841),16);seen.add(g);previous=g
  self.assertTrue({2829,2833,2837,2841,2845}<=seen);self.assertTrue(r['done']);self.assertEqual(g,2837)
 def test_loaded_joint_offset_does_not_move_the_command_anchor(self):
  p=SmallMotionPlan(2837,2859,(2815,2850));seen=set()
  for k in range(400):
   r=p.step(k*.05);seen.add(r['goal']);self.assertTrue(2829<=r['goal']<=2845)
  self.assertEqual(p.anchor_q,2859);self.assertEqual(r['goal'],2837)
  self.assertEqual((min(seen),max(seen)),(2829,2845))
 def test_unreviewed_entry_and_invalid_clock_rejected(self):
  for g,q in ((2848,2848),(2837,2860)):
   with self.assertRaises(ValueError):SmallMotionPlan(g,q,(2815,2850))
  p=SmallMotionPlan(2837,2841,(2815,2850));p.step(1.)
  with self.assertRaises(ValueError):p.step(.5)


class DriverTests(unittest.TestCase):
 def test_open_path_driver_writes_only_small_id2_goals_and_preserves_support_profile(self):
  import tempfile,json,os
  from unittest.mock import patch
  from .pc_tools import small_motion_driver as driver
  from .id2_small_motion import SmallMotionPlan
  import normal_gaze_motor
  from types import SimpleNamespace as NS
  profile=json.loads((Path(__file__).resolve().parents[3]/'bio_inspire/hardware/presentation_20261107/play_C1_angry_body25_trial.json').read_text())
  class Bus:
   def __init__(self):
    self.port=NS();self.ram={};self.writes=[];self.closed=False
    for i in range(1,6):
     a=bytearray(100);g=profile['normal_raw'][str(i)];q=g+(4 if i==2 else 0);a[40]=1;a[41]=8;a[42:44]=g.to_bytes(2,'little');a[46:48]=(600).to_bytes(2,'little');a[48:50]=(1000).to_bytes(2,'little');a[56:58]=q.to_bytes(2,'little');a[60:62]=(48).to_bytes(2,'little');a[62]=71;a[67:69]=g.to_bytes(2,'little');a[69:71]=(2).to_bytes(2,'little');p=profile['startup_pid_by_id'][str(i)];a[21:24]=bytes((p['p'],p['d'],p['i']));self.ram[i]=a
   def read(self,i,a,n):return bytes(self.ram[i][a:a+n])
   def write(self,i,a,data):
    self.writes.append((i,a,int.from_bytes(data,'little')));self.ram[i][a:a+len(data)]=data
    if a==42:self.ram[i][67:69]=data;self.ram[i][56:58]=(int.from_bytes(data,'little')+4).to_bytes(2,'little')
   def close(self):self.closed=True
  b=Bus();clock=NS(t=0.);original=os.getcwd()
  try:
   with tempfile.TemporaryDirectory()as folder:
    root=Path(folder);sub=root/'shared/experiments/presentation_safety_play_20261110';sub.mkdir(parents=True);(sub/'profile.json').write_text(json.dumps(profile))
    with patch.object(normal_gaze_motor,'open_bus',return_value=b),patch.object(driver.time,'monotonic',side_effect=lambda:clock.t),patch.object(driver.time,'sleep',side_effect=lambda t:setattr(clock,'t',clock.t+t)):
     report=driver.main(root/'output',root)
    os.chdir(original)
    self.assertEqual(report['status'],'PASS',report);self.assertTrue(report['pid_unchanged']);self.assertTrue(report['support_profile_unchanged']);self.assertTrue(b.closed)
    os.chdir(original)
    self.assertTrue(b.writes);self.assertTrue(all(i==2 and a==42 and 2829<=g<=2845 for i,a,g in b.writes))
  finally:os.chdir(original)
