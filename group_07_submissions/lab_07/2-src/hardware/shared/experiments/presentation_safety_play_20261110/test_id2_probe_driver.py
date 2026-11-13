import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from .pc_tools import id2_probe_driver as driver
import normal_gaze_motor

class Port:
 def __init__(self,b):self.b=b
 def reset_input_buffer(self):pass
 def write(self,p):
  assert sum(p[2:])&255==255
  if p[4]==131:
   address,width=p[5:7]
   for j in range(7,len(p)-1,width+1):assert p[j]in(2,4);self.b.apply(p[j],address,p[j+1:j+1+width])
  else:assert p[2]in(2,4) and p[4]==3;self.b.apply(p[2],p[5],p[6:-1])
  return len(p)
class Bus:
 def __init__(self,profile,case):
  self.ram={};self.writes=[];self.port=Port(self);self.closed=False;self.case=case;self.fired=False
  for i in range(1,6):
   a=bytearray(100);g=2835 if i==2 else profile['normal_raw'][str(i)];a[14]=80;a[15]=40;a[40]=1;a[41]=8;a[42:44]=g.to_bytes(2,'little');a[46:48]=(600).to_bytes(2,'little');a[48:50]=(1000).to_bytes(2,'little');a[56:58]=(g+(7 if i==2 else 0)).to_bytes(2,'little');a[60:62]=(64 if i==2 else 0).to_bytes(2,'little');a[62]=70;a[67:69]=g.to_bytes(2,'little');a[69:71]=(3 if i==2 else 0).to_bytes(2,'little');p=profile['startup_pid_by_id'][str(i)];a[21:24]=bytes((p['p'],p['d'],p['i']));self.ram[i]=a
  if case=='other_ref':self.ram[3][67:69]=(int.from_bytes(self.ram[3][42:44],'little')+1).to_bytes(2,'little')
 def apply(self,i,address,data):
  self.writes.append((i,address,bytes(data)));a=self.ram[i];a[address:address+len(data)]=data
  if address==42:a[67:69]=data;a[56:58]=(int.from_bytes(data,'little')+7).to_bytes(2,'little')
  if address==40 and len(data)==1:a[67:69]=a[56:58]
  if address==40 and len(data)==8:a[67:69]=a[42:44];a[56:58]=(int.from_bytes(a[42:44],'little')+7).to_bytes(2,'little');a[58:60]=bytes(2);a[66]=0
 def read(self,i,address,count):
  raw=bytes(self.ram[i][address:address+count]);goal=int.from_bytes(self.ram[2][42:44],'little')
  if i==4 and address==33 and self.case=='other_correction'and goal>=2846:
   v=bytearray(raw);v[23:25]=(int.from_bytes(v[23:25],'little')+2).to_bytes(2,'little');v[25:27]=(50).to_bytes(2,'little');v[33]=1;return bytes(v)
  if i==2 and address==33 and goal>=2846 and not self.fired and self.case in('lost_proof','foreign_goal','lost_proof_other_moving'):
   self.fired=True
   if self.case in('lost_proof','lost_proof_other_moving'):
    if self.case=='lost_proof_other_moving':
     a=self.ram[4];a[56:58]=(int.from_bytes(a[42:44],'little')+2).to_bytes(2,'little');a[58:60]=(50).to_bytes(2,'little');a[66]=1
    v=bytearray(raw);v[29]=59;return bytes(v)
   a=self.ram[2];a[42:44]=(goal+1).to_bytes(2,'little');a[67:69]=a[42:44];a[56:58]=(goal+8).to_bytes(2,'little');return bytes(a[33:71])
  return raw
 def _read_response(self,packet,sid,count):
  if packet[5:7]==bytes((14,2)):return bytes(self.ram[sid][14:16])
  if packet[5:7]==bytes((85,1)):return bytes((50,))
  raise AssertionError('Unexpected direct read')
 def close(self):self.closed=True
class Tests(unittest.TestCase):
 def run_case(self,case,staircase=False):
  base=Path(__file__).resolve().parents[3];profile=json.loads((base/'bio_inspire/hardware/presentation_20261107/play_C1_angry_body25_trial.json').read_text());bus=Bus(profile,case);clock=NS(t=0.)
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);h=root/'shared/experiments/presentation_safety_play_20261110';h.mkdir(parents=True);(h/'profile.json').write_text(json.dumps(profile))
   with patch.object(normal_gaze_motor,'open_bus',return_value=bus),patch.object(driver.time,'monotonic',side_effect=lambda:clock.t),patch.object(driver.time,'sleep',side_effect=lambda dt:setattr(clock,'t',clock.t+dt)),patch('shared.experiments.presentation_safety_play_20261110.id2_probe_io.receive_write_ack',return_value=None),patch('shared.experiments.presentation_safety_play_20261110.native_stop.receive_write_ack',return_value=None):report=driver.main(root/'out',root,staircase=staircase)
   return report,bus
 def test_loaded_success_retains_preload_and_returns_original_goal_before_cap(self):
  r,b=self.run_case('normal');self.assertEqual(r['status'],'PASS',r.get('error'));self.assertTrue(r['cap400_support_verified']);self.assertTrue(r['profile_config_restored']);self.assertTrue(r['active_static_hold_verified']);self.assertFalse(r['needs_inspection']);self.assertTrue(r['pid_unchanged']);self.assertTrue(b.closed)
  self.assertEqual(b.writes[0],(2,48,(400).to_bytes(2,'little')));self.assertTrue(all(i==2 and address in(42,48)for i,address,data in b.writes));self.assertEqual(int.from_bytes(b.ram[2][42:44],'little'),2835);self.assertEqual(int.from_bytes(b.ram[2][56:58],'little'),2842);self.assertEqual(b.writes[-1],(2,48,(1000).to_bytes(2,'little')))
 def test_lost_write_proof_still_captures_and_restores_supported_hold(self):
  r,b=self.run_case('lost_proof');self.assertEqual(r['status'],'FAIL');self.assertTrue(r.get('abort_supported_hold_restored'),r.get('recovery_error'));self.assertTrue(r['profile_config_restored']);self.assertTrue(r['active_static_hold_verified']);self.assertFalse(r['needs_inspection']);self.assertTrue(r['native_captures']);self.assertTrue(all(i==2 for i,a,data in b.writes));self.assertEqual(int.from_bytes(b.ram[2][42:44],'little'),2853);self.assertEqual(int.from_bytes(b.ram[2][56:58],'little'),2860)
 def test_unknown_goal_is_stopped_but_cannot_authorize_cap_increase(self):
  r,b=self.run_case('foreign_goal');self.assertEqual(r['status'],'FAIL');self.assertTrue(r['native_captures']);self.assertTrue(r['needs_inspection']);self.assertFalse(r['active_static_hold_verified']);self.assertEqual(int.from_bytes(b.ram[2][48:50],'little'),400);self.assertFalse(any(a==48 and int.from_bytes(data,'little')==1000 for i,a,data in b.writes))
 def test_other_axis_pending_reference_refuses_before_any_cap_change(self):
  r,b=self.run_case('other_ref');self.assertEqual(r['status'],'FAIL');self.assertFalse(b.writes)
 def test_staircase_visits_every_tick_both_directions_and_restores(self):
  r,b=self.run_case('normal',staircase=True);self.assertEqual(r['status'],'PASS',r.get('error'))
  goals=[int.from_bytes(v,'little')for i,a,v in b.writes if a==42]
  self.assertTrue(set(range(2819,2852)).issubset(goals));self.assertTrue(all(abs(x-y)==1 for x,y in zip([2835]+goals,goals)))
  self.assertTrue(r['active_static_hold_verified']);self.assertTrue(r['profile_config_restored'])
  self.assertEqual(r['diagnostic_plan'],'two_one_tick_staircases_pm16_300ms')
 def test_small_other_axis_native_correction_with_frozen_goal_is_not_new_command(self):
  r,b=self.run_case('other_correction',staircase=True)
  self.assertEqual(r['status'],'PASS',r.get('error'));self.assertTrue(r['profile_config_restored']);self.assertTrue(r['active_static_hold_verified'])
 def test_abort_recovery_uses_verified_other_axis_capture_not_obsolete_source_goal(self):
  r,b=self.run_case('lost_proof_other_moving');self.assertEqual(r['status'],'FAIL')
  self.assertTrue(r.get('abort_supported_hold_restored'),r.get('recovery_error'));self.assertTrue(r['profile_config_restored']);self.assertTrue(r['active_static_hold_verified']);self.assertFalse(r['needs_inspection'])

class LauncherTests(unittest.TestCase):
 def test_failed_tests_prevent_any_ssh_or_motor_command(self):
  from .pc_tools import run_id2_probe as launch
  with patch('sys.argv',['test','--execute','--authorized-cap400-id2']),patch.object(launch.subprocess,'run',return_value=NS(returncode=1,stdout='fake failure',stderr='failure'))as run:
   with self.assertRaises(SystemExit):launch.main()
   self.assertEqual(run.call_count,1);self.assertIn('unittest',run.call_args.args[0]);self.assertNotIn('wsl',run.call_args.args[0])
