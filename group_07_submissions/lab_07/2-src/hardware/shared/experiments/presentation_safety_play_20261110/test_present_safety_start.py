import tempfile
import unittest
from pathlib import Path
from . import present_safety_start as entry


class ShortcutOwnerTests(unittest.TestCase):
 def test_terminal_parent_is_not_a_motor_owner(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for pid,comm in ((10,'lxterminal'),(11,'sh')):
    p=root/str(pid);p.mkdir();(p/'comm').write_text(comm)
    (p/'cmdline').write_bytes(b'/bin/sh\0-c\0python present_safety_start.py\0')
   self.assertEqual(entry.existing_owners(root,99),[])

 def test_other_python_lamp_is_blocked_but_self_is_not(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for pid in (20,21):
    p=root/str(pid);p.mkdir();(p/'comm').write_text('python3.13')
    (p/'cmdline').write_bytes(b'python\0-B\0present_safety_start.py\0')
   found=entry.existing_owners(root,20)
   self.assertEqual([v[0] for v in found],[21])

 def test_normal_original_presentation_is_still_blocked(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'30';p.mkdir();(p/'comm').write_text('python')
   (p/'cmdline').write_bytes(b'python\0bio_inspire/deploy/open_presentation.py\0')
   self.assertEqual(entry.existing_owners(root,99)[0][0],30)

if __name__=='__main__':unittest.main()
