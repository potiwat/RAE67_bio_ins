import json
import unittest
from pathlib import Path
from unittest.mock import patch
from camera_motor import CameraMotor

class Tests(unittest.TestCase):
    def test_actual_afraid_profile_reaches_device_boundary(self):
        profile=Path(__file__).resolve().parents[1]/'hardware'/'afraid_pose_trial.json'
        motor=CameraMotor.__new__(CameraMotor)
        # Real profile/real constructor validation; stop before hardware access.
        with patch('camera_motor.open_bus',side_effect=RuntimeError('TEST_DEVICE_BOUNDARY')) as bus:
            with self.assertRaisesRegex(RuntimeError,'TEST_DEVICE_BOUNDARY'):
                motor.__init__(profile)
            bus.assert_called_once()
        self.assertEqual(motor.afraid_crouch_duration_s,6.)

    def test_unapproved_duration_is_rejected_before_device_boundary(self):
        profile=Path(__file__).resolve().parents[1]/'hardware'/'afraid_pose_trial.json'
        config=json.loads(profile.read_text(encoding='utf-8-sig'));config['afraid_crouch_duration_s']=7.
        with patch('camera_motor.Path.read_bytes',return_value=json.dumps(config).encode('utf8')),patch('camera_motor.open_bus') as bus:
            with self.assertRaises(ValueError):CameraMotor(profile)
            bus.assert_not_called()
