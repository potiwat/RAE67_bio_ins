import unittest
from shared.experiments.resistance_id1_20261109.foam_trial import Gate,checked_row

class FoamTests(unittest.TestCase):
 def test_acc4_handoff_is_opt_in_and_changes_only_motion_profile(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import resume_sweep
  from shared.experiments.resistance_id1_20261109.test_brake import Bus
  b=Bus();result=resume_sweep(b,2347,ack=lambda *a:None,native_probe=True,handoff_acc=4)
  self.assertEqual(b.packets[0][5],41);self.assertEqual(b.packets[0][6],4)
  self.assertEqual(b.b[7],1);self.assertEqual(int.from_bytes(b.b[15:17],'little'),160)
  self.assertEqual(result['acc'],4)
  b=Bus()
  with self.assertRaises(ValueError):resume_sweep(b,2347,ack=lambda *a:None,handoff_acc=4)
  self.assertFalse(b.packets)
 def test_assist_restores_acc3_after_two_fresh_moving_samples(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import HandoffAssist
  a=HandoffAssist(2347,1.)
  r=dict(position_raw=2019,speed_raw=100,sampled_monotonic_s=1.1)
  self.assertFalse(a.restore_ready(r,1.1))
  r.update(sampled_monotonic_s=1.16,position_raw=2022);self.assertTrue(a.restore_ready(r,1.16))
 def test_assist_does_not_restore_from_reported_speed_without_encoder_progress(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import HandoffAssist
  a=HandoffAssist(2347,1.)
  for k in range(4):self.assertFalse(a.restore_ready(dict(position_raw=2019,speed_raw=100,sampled_monotonic_s=1.16+k*.02),1.16+k*.02))
 def test_assist_does_not_lower_acc_when_already_near_endpoint_or_reversing(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import HandoffAssist
  a=HandoffAssist(2347,1.)
  for k in range(3):self.assertFalse(a.restore_ready(dict(position_raw=2300,speed_raw=100,sampled_monotonic_s=1.2+k*.02),1.2+k*.02))
  a=HandoffAssist(1691,1.)
  for k in range(3):self.assertFalse(a.restore_ready(dict(position_raw=2019,speed_raw=100,sampled_monotonic_s=1.2+k*.02),1.2+k*.02))
 def test_diagnostic_setup_keeps_normal_and_test_yaw_separate(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import diagnostic_setup
  normal={1:2019,2:2837,3:2746,4:1997,5:2696}
  setup=diagnostic_setup(normal,2317)
  self.assertEqual(setup['normal'],normal);self.assertIsNot(setup['normal'],normal)
  self.assertEqual(setup['diagnostic_yaw'],2317);self.assertEqual(normal[1],2019)
  with self.assertRaises(RuntimeError):diagnostic_setup(normal,2332)
 def test_open_path_qualification_brakes_only_inside_sweep_while_moving(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import qualification_due
  r=dict(position_raw=2019,speed_raw=200)
  self.assertTrue(qualification_due(r,1.,False))
  self.assertFalse(qualification_due(r,.2,False));self.assertFalse(qualification_due(r,1.,True))
  self.assertFalse(qualification_due(dict(r,speed_raw=0),1.,False))
  self.assertFalse(qualification_due(dict(r,position_raw=2340),1.,False))
 def test_resume_packet_combines_run_values_and_goal_without_actual_hold(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import resume_sweep
  from shared.experiments.resistance_id1_20261109.test_brake import Bus
  b=Bus();b.b[8]=1;b.b[13:15]=(17).to_bytes(2,'little')
  result=resume_sweep(b,2347,ack=lambda *a:None)
  self.assertEqual(len(b.packets),1);self.assertEqual(b.packets[0][5],41)
  self.assertEqual(b.packets[0][6:-1],bytes((3,43,9,0,0,88,2)))
  self.assertEqual(b.b[7],1);self.assertEqual(result['target'],2347)
 def test_fixed_profile_resume_writes_only_goal_not_speed_or_acceleration(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import resume_sweep
  from shared.experiments.resistance_id1_20261109.test_brake import Bus
  b=Bus()
  def write(packet):
   self.assertEqual(packet[5],42);b.packets.append(packet);b.b[9:11]=packet[6:8];return len(packet)
  b.write=write
  resume_sweep(b,2347,ack=lambda *a:None,native_probe=True)
  self.assertEqual(len(b.packets),1);self.assertEqual(b.b[8],3);self.assertEqual(int.from_bytes(b.b[13:15],'little'),600)
 def test_resume_requires_healthy_probe_and_confirmed_readback(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import resume_sweep
  from shared.experiments.resistance_id1_20261109.test_brake import Bus
  for at,value in ((0,1),(7,2),(8,3),(15,0),(32,1)):
   b=Bus();b.b[8]=1;b.b[13:15]=(17).to_bytes(2,'little');b.b[at]=value
   with self.assertRaises(RuntimeError):resume_sweep(b,2347,ack=lambda *a:None)
   self.assertFalse(b.packets)
  b=Bus();b.b[8]=1;b.b[13:15]=(17).to_bytes(2,'little');b.corrupt=True
  with self.assertRaises(RuntimeError):resume_sweep(b,2347,ack=lambda *a:None)
 def test_recorded_small_endpoint_residual_does_not_deadlock_sweep(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import endpoint_arrived
  r=dict(goal_raw=2347,internal_target_raw=2347,position_raw=2337,speed_raw=0,moving_raw=0,load_raw=1058,current_raw=1)
  self.assertTrue(endpoint_arrived(r,2347))
  for key,value in [('position_raw',2335),('load_raw',64),('current_raw',3),('speed_raw',50),('moving_raw',1),('internal_target_raw',2337)]:
   self.assertFalse(endpoint_arrived(dict(r,**{key:value}),2347))
 def test_normal_setup_preserves_loaded_body_holds(self):
  from shared.experiments.resistance_id1_20261109.foam_trial import normal_start_goals,first_target
  normal={1:2019,2:2837,3:2746,4:1997,5:2696}
  rows=[dict(id=i,mode=0,torque_raw=1,status_raw=0,speed_raw=0,moving_raw=0,goal_raw=q,position_raw=q) for i,q in normal.items()]
  rows[0].update(goal_raw=2337,position_raw=2337);rows[1]['position_raw']=2858;rows[2]['position_raw']=2765;rows[4].update(goal_raw=2711,position_raw=2711)
  self.assertEqual(normal_start_goals(rows,normal),{1:2019,5:2696})
  self.assertEqual(first_target(2337),1691);self.assertEqual(first_target(1700),2347)
  rows[1]['goal_raw']+=100
  with self.assertRaises(RuntimeError):normal_start_goals(rows,normal)
 def test_five_debounced_releases_not_hold_start_trial(self):
  g=Gate()
  for i in range(5):
   t=i*.3;g.update(True,t);g.update(True,t+.08);g.update(False,t+.1);g.update(False,t+.18)
   self.assertEqual(g.started,i==4)
 def test_initial_held_button_does_not_count_until_clean_release(self):
  g=Gate();g.update(True,0);g.update(True,.1);self.assertFalse(g.started)
 def test_other_torque_modes_and_stale_feedback_are_faults(self):
  row=dict(id=1,sampled_monotonic_s=1.,mode=0,torque_raw=1,status_raw=0,position_raw=2000,cap=160)
  checked_row(row,1.01,False)
  with self.assertRaises(RuntimeError):checked_row(row,1.3,False)
  row['torque_raw']=2
  with self.assertRaises(RuntimeError):checked_row(row,1.01,False)
  checked_row(row,1.01,True)
