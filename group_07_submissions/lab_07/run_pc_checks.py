"""Mocked PC checks only. Does not start camera/GPIO/UART/ROS."""
from pathlib import Path
import os,sys,unittest
root=Path(__file__).resolve().parent/'2-src';os.chdir(root)
sys.path[:0]=[str(root),str(root/'bio_inspire/runtime'),str(root/'shared/runtime')]
names=['bio_inspire.experiments.test_automatic_component','bio_inspire.experiments.test_all_state_compare',
       'bio_inspire.experiments.test_ahm_cpg_compare','test_interested_player_reference',
       'test_button_look','test_three_state_behavior','test_interested_head','test_native_posture',
       'test_lab07_start_gate','test_session_recording','test_led_ring','bio_inspire.experiments.test_ros13']
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
raise SystemExit(not result.wasSuccessful())
