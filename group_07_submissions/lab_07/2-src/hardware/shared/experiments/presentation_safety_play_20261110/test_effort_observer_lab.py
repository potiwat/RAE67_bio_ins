import unittest
from .effort_observer_lab import shadow_adapter

class Tests(unittest.TestCase):
 def test_resistance_only_authority_is_scoped_and_native_decision_unchanged(self):
  class Base:
   def observe(self,row,decision):
    self.seen=(self.enabled_ids,decision)
    if decision['reason']=='native fault':raise RuntimeError('native fault')
  a=shadow_adapter(Base)();a.enabled_ids={1,2,4}
  d=dict(decision='WOULD_HOLD_DATA',reason='feedback gap')
  a.observe({},d);self.assertEqual(a.seen[0],set());self.assertIs(a.seen[1],d);self.assertEqual(a.enabled_ids,{1,2,4})
  with self.assertRaisesRegex(RuntimeError,'native fault'):a.observe({},dict(reason='native fault'))
  self.assertEqual(a.enabled_ids,{1,2,4})
