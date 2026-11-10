import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from joint_tuner import describe,save_favorite

class Tests(unittest.TestCase):
    def view(self,actual=2637):
        return dict(state='READY',error='',rows=[dict(id=5,position_raw=actual,speed_raw=0,moving_raw=0)],active_goal=dict(joint_id=5,raw=2628))
    def test_settings_applied_and_motion_near_target_are_distinct(self):
        t=dict(joint_id=5,applied=dict(p=18,i=0,d=0,speed=1),status='SENT ID5 goal=2628 (readback OK)')
        d=describe(self.view(),t,dict(p=18,i=0,d=0),5)
        self.assertTrue(d['applied']);self.assertIn('ถึงเป้าในเกณฑ์',d['title'])
        t['applied']['p']=1;d=describe(self.view(actual=2696),t,dict(p=1,i=0,d=0),5)
        self.assertTrue(d['applied']);self.assertIn('ยังไม่ถึงเป้า',d['title'])
    def test_staged_value_is_not_labelled_applied(self):
        d=describe(self.view(),dict(joint_id=5,applied=dict(p=18,i=0,d=0),status='APPLIED'),dict(p=16,i=0,d=0),5)
        self.assertFalse(d['applied']);self.assertIn('ยังไม่ได้ใช้',d['settings'])
    def test_saved_good_setting_is_explicit_operator_choice_and_requires_readback(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            p=Path(folder)/'favorites.json';v=dict(p=18,i=0,d=0,speed=1)
            with self.assertRaises(ValueError):save_favorite(p,5,v,dict(joint_id=5,applied=dict(v,p=16)))
            result=save_favorite(p,5,v,dict(joint_id=5,applied=v))
            self.assertEqual(result['5']['values'],v)
            self.assertEqual(result['5']['assessment'],'operator_selected_smooth')

import os
@unittest.skipUnless(os.environ.get('DISPLAY'),'Requires display; uses fake motor, no hardware')
class WidgetTests(unittest.TestCase):
    def test_simple_screen_reads_live_pid_and_enables_motion_without_raw_details(self):
        import tkinter as tk
        from tkinter import ttk
        from joint_tuner import SimpleTuner
        class FakeMotor:
            tuning_id=5
            def poll(self):pass
            def key(self,k):pass
            def snapshot_view(self):return dict(state='READY',error='',rows=[dict(id=5,position_raw=2637,speed_raw=0,moving_raw=0)],active_goal=dict(joint_id=5,raw=2628))
            def tuning_view(self):return dict(joint_id=5,applied=dict(p=18,i=0,d=0,speed=1),status='SENT ID5')
        root=tk.Tk();root.withdraw()
        try:
            app=SimpleTuner(root,tk,ttk,Path('unused.json'));app.motor=FakeMotor();app.poll();root.update_idletasks()
            self.assertEqual(app.desired(),dict(p=18,i=0,d=0))
            self.assertTrue(all('disabled' not in b.state() for b in app.moves))
            self.assertIn('ตั้งค่า',app.settings.cget('text'))
            self.assertFalse(app.details.winfo_manager())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
