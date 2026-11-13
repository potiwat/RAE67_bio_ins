import unittest
from .state_matrix_inputs import StateDrive,STATES
from bio_inspire.runtime.angry_fsm import AngryFSM
class Tests(unittest.TestCase):
 def test_all_six_use_real_fsm_policy_and_keep_fault_priority(self):
  for state in STATES:
   d=StateDrive();d.select(state);f=AngryFSM(0)
   f.step(1,d.filter(1,[]));self.assertEqual(f.state,state)
   f.step(2,d.filter(2,[dict(kind='fault',source_s=2,source_id='real_fault')]))
   self.assertEqual(f.state,'normal')
 def test_afraid_logical_clear_override_never_changes_input_or_survives_clear(self):
  d=StateDrive();d.select('afraid');events=[dict(kind='clear'),dict(kind='fault')]
  self.assertEqual([x['kind']for x in d.filter(1,events)],['fault','near'])
  self.assertEqual(events,[dict(kind='clear'),dict(kind='fault')])
  d.clear();self.assertIs(d.filter(2,events),events)
 def test_sudden_state_changes_use_same_policy(self):
  for source,target in (('happy','angry'),('interested','happy'),('sleepy','happy'),('afraid','normal')):
   d=StateDrive();f=AngryFSM(0);d.select(source);f.step(1,d.filter(1,[]))
   d.select(target);f.step(2,d.filter(2,[]));self.assertEqual(f.state,target)
