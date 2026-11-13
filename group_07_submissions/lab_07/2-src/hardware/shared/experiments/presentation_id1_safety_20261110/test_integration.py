import ast,inspect,unittest
from shared.experiments.presentation_id1_safety_20261110.integration import patched_worker,forward_key

class HookTests(unittest.TestCase):
 def test_v_reaches_worker_queue_without_uart_on_gui_thread(self):
  import threading
  from types import SimpleNamespace
  from unittest.mock import Mock
  m=SimpleNamespace(lock=threading.Lock(),keys=[]);original=Mock()
  forward_key(m,ord('v'),original);forward_key(m,ord('V'),original)
  self.assertEqual(m.keys,[ord('v'),ord('v')]);original.assert_not_called()
  forward_key(m,ord('h'),original);original.assert_called_once_with(m,ord('h'))
 def test_current_accepted_worker_hooks_are_ordered_and_compile(self):
  from bio_inspire.runtime.camera_motor import CameraMotor
  source=patched_worker(inspect.getsource(CameraMotor._run));ast.parse(source)
  self.assertLess(source.index('self.id1_safety.service()'),source.index('self.controller.tick('))
  self.assertLess(source.index('self.controller.tick('),source.index('self.id1_safety.observe()'))
  self.assertLess(source.index('self.id1_safety.observe()'),source.index('self._service_tuning('))
  self.assertGreater(source.index('self.id1_safety.arm_if_ready()'),source.rindex('service_state_outputs(self)'))
  self.assertGreater(source.index('self.id1_safety.arm_if_ready()'),source.index('prepare_awake(self)'))
  tree=ast.parse(source);loop=next(n for n in ast.walk(tree) if isinstance(n,ast.While))
  self.assertIsInstance(loop.body[0],ast.Try)
  self.assertEqual(loop.body[0].handlers[0].type.id,'_SafetyInterrupt')
 def test_unknown_worker_source_fails_before_hardware_open(self):
  with self.assertRaises(RuntimeError):patched_worker('def _run(self):\n pass')
 def test_actual_worker_handles_uart_safety_interrupt_without_outer_fault_or_queued_motion(self):
  import threading
  from types import SimpleNamespace
  from unittest.mock import Mock
  import test_three_state_behavior
  from bio_inspire.runtime import camera_motor as mod
  from shared.experiments.presentation_id1_safety_20261110.adapter import SafetyInterrupt
  m,b=test_three_state_behavior.Tests().motor()
  m.last_frame=20.;m.latest_result=None;m.keys=[];m.deadband_px=15.;m.trace=[];m.finished=threading.Event()
  m._reset_normal_ahm=Mock();m._publish=Mock();b.close=Mock();m.controller.hold=Mock(return_value=True)
  signal=SafetyInterrupt('resistance',{'id':1})
  def tick(now):
   try:raise signal
   except Exception:self.fail('Behavior handler swallowed safety interrupt')
  m.controller.tick=Mock(side_effect=tick)
  owner=SimpleNamespace(service=lambda:False,handle_interrupt=Mock(side_effect=lambda s:m.stopping.set()))
  source=patched_worker(inspect.getsource(mod.CameraMotor._run))
  scope=dict(mod.__dict__,_SafetyOwner=lambda *a:owner,_SafetyOutput=None,_SafetyInterrupt=SafetyInterrupt)
  exec(compile(source,'worker_test','exec'),scope);scope['_run'](m)
  owner.handle_interrupt.assert_called_once_with(signal)
  self.assertNotEqual(m.controller.state,'FAULT');self.assertTrue(m.finished.is_set());b.close.assert_called_once()
