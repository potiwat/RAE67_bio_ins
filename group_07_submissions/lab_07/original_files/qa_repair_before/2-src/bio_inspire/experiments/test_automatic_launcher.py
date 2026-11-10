import json,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class Tests(unittest.TestCase):
    def test_six_profiles_change_no_motion_parameters(self):
        from bio_inspire.runtime.automatic_trial import validate
        base=json.loads((ROOT/'bio_inspire/hardware/boot_ready_c1.json').read_text())
        extra={'lab07_recording_seconds','lab07_start_button_presses','lab07_automatic_script','lab07_pair_id','normal_ahm_condition'}
        for pair in ('P1','P2','P3'):
            for condition in ('C0','C1'):
                p=json.loads((ROOT/f'bio_inspire/hardware/lab07_automatic_{pair}_{condition}.json').read_text())
                self.assertTrue(validate(p));self.assertEqual(p['lab07_pair_id'],pair)
                self.assertEqual(p['normal_ahm_condition'],condition)
                self.assertEqual({k:v for k,v in p.items() if k not in extra},{k:v for k,v in base.items() if k not in extra})

    def test_launcher_opens_viewer_without_motor_auto_start(self):
        import runpy,sys
        from unittest.mock import patch
        with patch.object(sys,'argv',['open_lab07_auto.py','--condition','C0','--pair','P1']),patch('os.chdir'),patch('os.execv') as launch:
            runpy.run_path(str(ROOT/'bio_inspire/deploy/open_lab07_auto.py'),run_name='__main__')
        args=launch.call_args.args[1]
        self.assertIn('--simple-ui',args)
        self.assertNotIn('--auto-normal-start',args)
        self.assertNotIn('--boot-ready',args)
        self.assertTrue(args[args.index('--normal-profile')+1].endswith('lab07_automatic_P1_C0.json'))
