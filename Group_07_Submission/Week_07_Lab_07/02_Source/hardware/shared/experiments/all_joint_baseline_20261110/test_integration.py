import ast,inspect,unittest
from shared.experiments.all_joint_baseline_20261110.integration import patched_worker

class Tests(unittest.TestCase):
 def test_real_worker_binds_recorder_before_first_tick_and_adds_no_motion(self):
  from bio_inspire.runtime.camera_motor import CameraMotor
  original=__import__('textwrap').dedent(inspect.getsource(CameraMotor._run));patched=patched_worker(original);ast.parse(patched)
  self.assertLess(patched.index('self.bus.all_joint_baseline.motor=self'),patched.index('while not self.stopping'))
  self.assertEqual(patched.replace('        self.bus.all_joint_baseline.motor=self\n',''),original)
 def test_unknown_runtime_fails_closed(self):
  with self.assertRaises(RuntimeError):patched_worker('def _run(self): pass')
