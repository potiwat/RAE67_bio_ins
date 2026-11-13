import unittest,tempfile,time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from bio_inspire.runtime.presentation_led import service_breathing,COLORS
from .led import build_service,build_driver,OriginalLedRing

class Pixels:
 def __init__(self,fail=False):self.brightness=.03;self.color=None;self.frames=[];self.fail=fail
 def fill(self,color):self.color=color
 def show(self):
  if self.fail:raise ValueError('LED backend error')
  self.frames.append((self.color,self.brightness))
 def deinit(self):pass

class Tests(unittest.TestCase):
 def test_recovery_dark_flag_blocks_every_behavior_until_new_owner(self):
  service=build_service(service_breathing);ring=Mock();m=NS(led_ring=ring,safety_recovery_led_off=True)
  for state in COLORS:service(m,state,True)
  ring.close.assert_called_once();ring.show_color.assert_not_called();self.assertIsNone(m.led_ring)
 def test_dark_driver_supports_all_original_state_methods_without_hardware(self):
  from .auto_recovery import DarkLed
  import led_ring
  methods=('normal','interested','happy','angry','afraid','sleepy')
  with patch.object(led_ring.subprocess,'run',side_effect=AssertionError('Dark output touched GPIO')):
   ring=DarkLed()
   for state in methods:
    getattr(ring,state)()
    self.assertEqual(ring.last_frame[0],COLORS[state])
   ring.close();self.assertIsNone(ring.last_frame)
 def test_live_hooks_install_driver_guard_without_opening_any_devices(self):
  import led_ring
  from .integration import hooks,consent
  from shared.experiments.central_safety_controller_20261110.harness import ROOT,CONFIG
  import json
  original=led_ring.LedRing
  with tempfile.TemporaryDirectory()as d,hooks(ROOT,Path(d),json.loads(CONFIG.read_text()),time.monotonic,trial_consent=consent()):
   ring=led_ring.LedRing();ring.pixels=Pixels();ring.show_color((255,100,0),brightness=.03)
   self.assertEqual(ring.pixels.frames[-1],((255,100,0),.03));self.assertIsNot(led_ring.LedRing,original)
  self.assertIs(led_ring.LedRing,original)
 def test_actual_driver_validator_accepts_every_cpg_level_in_all_states(self):
  service=build_service(service_breathing);driver=build_driver()
  for state in COLORS:
   ring=driver();ring.pixels=Pixels()
   router=NS(happy=NS(rhythm=NS(decoder_phase_cycles=0.),phase_divisor=2.),afraid=NS(rhythm=NS(decoder_phase_cycles=0.)),breathing=NS(rhythm=NS(decoder_phase_cycles=0.)))
   m=NS(rhythm_driver=router,led_ring=ring,now=lambda:0.)
   active=router.happy if state=='happy'else router.afraid if state=='afraid'else router.breathing
   for k in range(65):
    active.rhythm.decoder_phase_cycles=k/64*(2 if state=='happy'else 1);service(m,state,True)
   self.assertFalse(getattr(m,'presentation_led_disabled',False));self.assertAlmostEqual(min(x[1]for x in ring.pixels.frames),.03)
   self.assertAlmostEqual(max(x[1]for x in ring.pixels.frames),.08);self.assertTrue(all(x[0]==COLORS[state]for x in ring.pixels.frames))
 def test_driver_rejects_outside_three_eight_and_original_guard_stays_unchanged(self):
  ring=build_driver()();ring.pixels=Pixels()
  for b in(.0299,.0801,float('nan'),float('inf'),True):
   with self.assertRaises(ValueError):ring.show_color((255,255,255),brightness=b)
  with self.assertRaises(ValueError):OriginalLedRing().show_color((255,255,255),brightness=.03)
 def test_led_value_error_and_cleanup_error_disable_only_decorative_output(self):
  ring=build_driver()();ring.pixels=Pixels(fail=True)
  m=NS(led_ring=ring,now=lambda:0.,rhythm_driver=NS(breathing=NS(rhythm=NS(decoder_phase_cycles=0.))))
  with patch('led_ring.subprocess.run')as pin:
   build_service(service_breathing)(m,'normal',True)
   self.assertTrue(m.presentation_led_disabled);self.assertIsNone(m.led_ring);pin.assert_called_with(['pinctrl','set','10','op','dl'],check=True)
 def test_all_states_real_phase_three_to_eight_with_original_rgb(self):
  service=build_service(service_breathing)
  for state in COLORS:
   router=NS(happy=NS(rhythm=NS(decoder_phase_cycles=0.),phase_divisor=2.),afraid=NS(rhythm=NS(decoder_phase_cycles=0.)),breathing=NS(rhythm=NS(decoder_phase_cycles=0.)))
   m=NS(rhythm_driver=router,led_ring=Mock(),now=lambda:0.)
   driver=router.happy if state=='happy'else router.afraid if state=='afraid'else router.breathing
   for phase,expected in ((0.,.08),(.5,.03),(.25,.055)):
    driver.rhythm.decoder_phase_cycles=phase*(2 if state=='happy'else 1)
    service(m,state,True)
    self.assertAlmostEqual(m.led_ring.show_color.call_args.kwargs['brightness'],expected)
    self.assertEqual(m.led_ring.show_color.call_args.args[0],COLORS[state])
    self.assertGreaterEqual(m.led_ring.show_color.call_args.kwargs['brightness'],.03)
 def test_missing_phase_stays_at_three_and_wall_clock_does_not_advance_cpg(self):
  service=build_service(service_breathing);m=NS(led_ring=Mock(),now=lambda:0.)
  service(m,'happy',True);self.assertEqual(m.presentation_led_output['requested_brightness'],.03)
  m.rhythm_driver=NS(breathing=NS(rhythm=NS(decoder_phase_cycles=.25)))
  service(m,'normal',True);a=m.presentation_led_output['requested_brightness']
  m.now=lambda:100.;service(m,'normal',True);self.assertEqual(a,m.presentation_led_output['requested_brightness'])
