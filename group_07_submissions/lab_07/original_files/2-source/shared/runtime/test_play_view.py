import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from play_view import status_text
class Tests(unittest.TestCase):
    def test_before_start_is_ready_without_motor_access(self):
        self.assertEqual(status_text(None),'Ready - press Start')
    def test_stop_and_fault_are_clear_without_diagnostic_jargon(self):
        m=Mock();m.operator_stopped=True
        self.assertEqual(status_text(m),'Stopped - press Start to resume')
        m.operator_stopped=False;m.fault_message.return_value='UART timeout private details'
        self.assertEqual(status_text(m),'Stopped - check lamp, then Start')
    def test_live_state_and_startup_are_named(self):
        m=Mock();m.operator_stopped=False;m.fault_message.return_value=''
        m.snapshot_view.return_value={'state':'NORMAL_STARTUP'}
        self.assertEqual(status_text(m),'Starting - moving to Normal')
        m.snapshot_view.return_value={'state':'READY','emotion':'happy'}
        self.assertEqual(status_text(m),'Happy')

    def test_simple_start_stop_buttons_cover_full_large_button_height(self):
        from behavior_panel import BehaviorPanel
        cv=SimpleNamespace(EVENT_LBUTTONUP=4,setMouseCallback=lambda *a:None)
        p=BehaviorPanel(cv,'play',automatic=True,simple=True);p.top=228;p.width=320
        p.click(4,40,280,0,None);self.assertEqual(p.take(None),ord('m'))
        p.click(4,240,280,0,None);self.assertEqual(p.take(None),ord('h'))
    def test_desktop_launcher_never_requests_boot_or_auto_start(self):
        import runpy
        from pathlib import Path
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[2]
        with patch('os.chdir'),patch('os.execv') as execute:
            runpy.run_path(str(root/'bio_inspire/deploy/open_play.py'),run_name='__main__')
        args=execute.call_args.args[1]
        self.assertIn('--simple-ui',args)
        self.assertNotIn('--auto-normal-start',args);self.assertNotIn('--boot-ready',args)

    def test_retired_boot_service_has_no_motion_command(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[2]/'bio_inspire/deploy/lelamp.service').read_text(encoding='utf8')
        self.assertIn('ExecStart=/usr/bin/true',text)
        self.assertNotIn('--auto-normal-start',text);self.assertNotIn('--boot-park',text)
