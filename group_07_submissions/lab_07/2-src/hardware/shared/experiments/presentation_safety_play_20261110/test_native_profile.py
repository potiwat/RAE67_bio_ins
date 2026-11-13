import unittest
from types import SimpleNamespace as NS
from .native_profile import require_default_caps
class Tests(unittest.TestCase):
 def test_dirty_probe_caps_cannot_silently_be_used_for_presentation_motion(self):
  for dirty in (1,2,4):
   b=NS(read=lambda i,address,count:bytes(15)+(400 if i==dirty==2 else 160 if i==dirty else 1000).to_bytes(2,'little')+bytes(21))
   with self.assertRaisesRegex(RuntimeError,'not restored'):require_default_caps(b)
  self.assertEqual(require_default_caps(NS(read=lambda *args:bytes(15)+(1000).to_bytes(2,'little')+bytes(21))),{i:1000 for i in range(1,6)})
