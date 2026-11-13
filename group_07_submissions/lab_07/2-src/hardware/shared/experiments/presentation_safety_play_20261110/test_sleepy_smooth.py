import unittest
from .sleepy_smooth import smooth_driver
from bio_inspire.runtime.body_rhythm import BodyRhythmDriver
from bio_inspire.runtime import test_deep_sleepy as fixture
from bio_inspire.runtime.three_state_behavior import handle_state_key


class SleepySmoothTests(unittest.TestCase):
 def setup_motor(self):
  m,b=fixture.DeepSleepyTests().motor();c=m.controller
  c.sleepy_native_fold_enabled=True;c.sleepy_native_fold_degrees=12;c.sleepy_native_fold_speed_raw=1
  old=c.normal[2]+13;b.reg[2][42]=old
  c.rhythm_base_reference={i:c.normal[i]for i in (2,3)}
  handle_state_key(m,ord('s'));c.last_rows=b.snapshot()
  for r in c.last_rows:r['goal_raw']=b.reg[r['id']][42]
  return m,b,old

 def test_entry_keeps_commanded_id2_source_and_same_native_fold(self):
  m,b,old=self.setup_motor();c=m.controller;d=smooth_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
  d.step(m,20.)
  self.assertEqual(b.reg[2][42],old)
  self.assertEqual(b.reg[3][42],c.sleepy_body_reference[3]+137)
  self.assertEqual(b.reg[3][46],1)
  self.assertEqual(b.reg[5][46],25)

 def test_id2_blends_monotonically_without_cpg_tug_during_fold(self):
  m,b,old=self.setup_motor();c=m.controller;d=smooth_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
  goals=[]
  for n in range(81):
   d.step(m,20+n*.05);goals.append(b.reg[2][42]);c.last_rows=b.snapshot()
  target=c.sleepy_body_reference[2]
  self.assertEqual(goals[0],old);self.assertEqual(goals[-1],target)
  self.assertEqual(goals,sorted(goals,reverse=old>target))
  self.assertLessEqual(max(abs(a-b)for a,b in zip(goals,goals[1:])),1)

 def test_operator_stop_preempts_blend_and_normal_uses_original_commands(self):
  m,b,old=self.setup_motor();d=smooth_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
  d.step(m,20.);m.operator_stopped=True;b.calls.clear();d.step(m,20.5)
  self.assertEqual(b.calls,[])
  from bio_inspire.runtime.test_angry import MotionTests
  histories=[]
  for cls in (BodyRhythmDriver,smooth_driver(BodyRhythmDriver)):
   motor,bus=MotionTests().motor();motor.controller.pose_route=None
   driver=cls(sleepy_amplitude_deg=2.);history=[]
   for n in range(30):
    driver.step(motor,20+n*.05);history.append((bus.reg[2][42],bus.reg[3][42]))
   histories.append(history)
  self.assertEqual(*histories)

 def test_oscillator_runs_during_fold_then_cpg_fades_back(self):
  m,b,old=self.setup_motor();c=m.controller;d=smooth_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
  for n in range(61):d.step(m,20+n*.05)
  self.assertGreater(d.rhythm.updates,0)
  self.assertEqual(d.rhythm.modulation_status['sleepy_handoff']['cpg_weight'],0)
  b.pos[3]=c.sleepy_native_fold['target'];c.last_rows=b.snapshot()
  d.step(m,28.1);self.assertEqual(c.sleepy_native_fold['phase'],'breathing')
  d.step(m,30.2)
  self.assertEqual(d.rhythm.modulation_status['sleepy_handoff']['cpg_weight'],1)
  self.assertEqual(d.rhythm.modulation_status['sleepy_handoff']['blend'],1)
  self.assertEqual(b.reg[3][46],c.motion_speed)

 def test_bounds_error_restores_composer_and_does_not_write(self):
  import motion_composer
  m,b,old=self.setup_motor();d=smooth_driver(BodyRhythmDriver)(sleepy_amplitude_deg=2.)
  original=motion_composer.compose_goals
  # Invalid captured source must be rejected by the unchanged composer.
  next(r for r in m.controller.last_rows if r['id']==2)['goal_raw']=4095
  with self.assertRaises(ValueError):d.step(m,20.)
  self.assertIs(motion_composer.compose_goals,original)

if __name__=='__main__':unittest.main()
