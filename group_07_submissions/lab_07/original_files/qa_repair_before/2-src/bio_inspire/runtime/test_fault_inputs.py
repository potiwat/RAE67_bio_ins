import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from camera_motor import CameraMotor


class Tests(unittest.TestCase):
    def test_fault_cleanup_detaches_digital_inputs_and_is_idempotent(self):
        m=CameraMotor.__new__(CameraMotor);m.controller=SimpleNamespace(state='FAULT')
        touch=Mock();button=Mock();m.physical_touch=touch;m.physical_button=button
        m._close_fault_inputs();m._close_fault_inputs()
        self.assertIsNone(m.physical_touch);self.assertIsNone(m.physical_button)
        touch.close.assert_called_once();button.close.assert_called_once()
        self.assertFalse(m._poll_physical_touch(20.))
        touch.poll.assert_not_called()

    def test_fault_never_polls_closed_touch_even_before_cleanup(self):
        m=CameraMotor.__new__(CameraMotor);m.controller=SimpleNamespace(state='FAULT')
        m.physical_touch=Mock();m.physical_touch.poll.side_effect=RuntimeError('closed device')
        self.assertFalse(m._poll_physical_touch(20.))
        m.physical_touch.poll.assert_not_called()
