import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from shared.experiments.resistance_id1_20261109.pilot import PAIR
try:
 from shared.experiments.resistance_id1_20261109.trial_view import status_lines,draw
except ImportError:status_lines=draw=None

class Tests(unittest.TestCase):
 def motor(self):return NS(lab07_pair_id=PAIR,operator_stopped=False,fault_message=lambda:'',snapshot_view=lambda:{'state':'READY'},lab07_start_gate=NS(started=True))
 def test_native_states_are_visible_in_simple_view(self):
  self.assertIsNotNone(status_lines)
  m=self.motor();p=NS(phase='RUN',active_s=44.81,attempts=0,started=1.)
  sessions=NS(attempts=[(m,p)])
  self.assertIn('44.8',status_lines(sessions,m)[1]);self.assertIn('45.0',status_lines(sessions,m)[1])
  for phase,text in [('WAIT','RESISTANCE_PAUSE'),('PROBE','SLOW PROBE'),('LATCHED','RESISTANCE_PAUSE'),('COMPLETE','COMPLETE')]:
   p.phase=phase;self.assertIn(text,' '.join(status_lines(sessions,m)))
 def test_fault_and_stop_are_not_covered_by_trial_banner(self):
  self.assertIsNotNone(status_lines)
  m=self.motor();m.operator_stopped=True
  self.assertIsNone(status_lines(NS(attempts=[]),m))
  m.operator_stopped=False;m.fault_message=lambda:'bus failure'
  self.assertIsNone(status_lines(NS(attempts=[]),m))
 def test_other_profiles_are_unchanged(self):
  self.assertIsNotNone(status_lines)
  m=self.motor();m.lab07_pair_id='presentation'
  self.assertIsNone(status_lines(NS(attempts=[]),m))

 def test_r4_banner_shows_cap_and_does_not_promise_retry(self):
  m=self.motor();p=NS(started=1.,phase='RUN',cap_limit=160,active_s=1.,attempts=0)
  sessions=NS(attempts=[(m,p)])
  self.assertIn('R4',status_lines(sessions,m)[0]);self.assertIn('160/1000',status_lines(sessions,m)[1])
  p.phase='LATCHED';self.assertIn('No automatic retry',status_lines(sessions,m)[1])
