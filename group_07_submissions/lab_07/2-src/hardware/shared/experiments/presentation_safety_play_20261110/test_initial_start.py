import unittest
from pathlib import Path
from .initial_start import InitialButtonStart, with_initial_gate

class Input:
 def __init__(self,held=False):
  self.seq=1;self.edges=[dict(sequence=1,pressed=held)];self.closed=False;self.error=None
 def diagnostics(self):return dict(stable_sequence=self.seq,stable_pressed=self.edges[-1]['pressed'],stable_edges=list(self.edges),sampler_error=self.error)
 def edge(self,pressed):
  self.seq+=1;self.edges.append(dict(sequence=self.seq,pressed=pressed))
 def close(self):self.closed=True

class InitialStartTests(unittest.TestCase):
 def make(self,held=False):
  x=Input(held);g=InitialButtonStart(lambda:x);g.open();return x,g
 def cycles(self,x,g,n):
  for _ in range(n):
   x.edge(True);self.assertEqual(g.filter_key(None,255,True),255)
   x.edge(False);key=g.filter_key(None,255,True)
  return key
 def test_five_complete_releases_close_gpio_before_motor_start(self):
  x,g=self.make();self.assertEqual(self.cycles(x,g,4),255);self.assertFalse(x.closed)
  self.assertEqual(self.cycles(x,g,1),ord('m'));self.assertTrue(x.closed)
  self.assertTrue(g.claimed);self.assertEqual(g.filter_key(None,255,True),255)
 def test_boot_held_release_is_not_a_press(self):
  x,g=self.make(True);x.edge(False);g.filter_key(None,255,True)
  self.assertEqual(g.count,0);self.assertEqual(self.cycles(x,g,4),255)
 def test_sampler_starts_unknown_then_boot_held_does_not_count(self):
  x=Input();x.edges=[dict(sequence=1,pressed=None)];g=InitialButtonStart(lambda:x).open()
  x.edge(True);g.filter_key(None,255,True);x.edge(False);g.filter_key(None,255,True)
  self.assertEqual(g.count,0)
  self.assertEqual(self.cycles(x,g,4),255)
 def test_keyboard_and_gui_m_do_not_bypass_initial_gate(self):
  x,g=self.make();self.assertEqual(g.filter_key(None,ord('m'),True),255)
  self.assertFalse(g.claimed);self.assertFalse(x.closed)
 def test_q_and_window_close_win_over_pending_fifth(self):
  for key,visible in [(ord('q'),True),(27,True),(255,False)]:
   x,g=self.make();self.cycles(x,g,4);x.edge(True);x.edge(False)
   self.assertEqual(g.filter_key(None,key,visible),key);self.assertFalse(g.claimed)
 def test_h_cancels_pending_counts_without_starting(self):
  x,g=self.make();self.cycles(x,g,4);x.edge(True);x.edge(False)
  self.assertEqual(g.filter_key(None,ord('h'),True),ord('h'));self.assertEqual(g.count,0)
  self.assertEqual(g.filter_key(None,255,True),255)
 def test_sampler_error_latches_and_does_not_auto_retry(self):
  x,g=self.make();x.error='read failed';self.assertEqual(g.filter_key(None,255,True),255)
  self.assertIn('read failed',g.error);self.assertTrue(x.closed)
  x.error=None;self.assertEqual(g.filter_key(None,ord('m'),True),255)
 def test_post_start_keys_belong_to_existing_restart_logic(self):
  x,g=self.make();self.cycles(x,g,5);motor=object()
  self.assertEqual(g.filter_key(motor,ord('m'),True),ord('m'))
 def test_close_releases_gpio_before_start(self):
  x,g=self.make();g.close();self.assertTrue(x.closed)
 def test_source_injection_preserves_restart_and_priority_order(self):
  from .restart import with_restart_gate
  root=Path(__file__).resolve().parents[3]
  original=(root/'shared/runtime/camera_preview.py').read_text(encoding='utf-8-sig')
  source=with_initial_gate(with_restart_gate(original))
  compile(source,'trial-preview','exec')
  self.assertLess(source.index('trial_initial_gate.filter_key('),source.index('trial_take_restart(motor,key)'))
  self.assertIn('trial_start_after_button(motor,args.normal_profile,CameraMotor,trial_button_restart)',source)
 def test_changed_source_boundary_is_rejected(self):
  with self.assertRaises(RuntimeError):with_initial_gate('unknown viewer')

if __name__=='__main__':unittest.main()
