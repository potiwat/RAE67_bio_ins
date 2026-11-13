import json,sys,types,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from bio_inspire.runtime import sleepy_trial
from . import sleepy_coordination,test_sleepy_coordination as fixture
from .sleepy_matched_native import bus_write,setter,fold_weight,matched_driver


class Tests(unittest.TestCase):
    def test_adapter_setup_failure_closes_its_uart_before_retry(self):
        from .sleepy_matched_native import open_factory
        class Bus:
            def write(self,*args):pass
        bus=Bus();bus.close=Mock()
        with patch('shared.experiments.presentation_safety_play_20261110.sleepy_matched_native.bus_write',side_effect=RuntimeError('validator source changed')):
            with self.assertRaisesRegex(RuntimeError,'validator source changed'):open_factory(lambda:bus)()
        bus.close.assert_called_once_with()

    def test_exact_authorized_ram_values_only_and_no_pid_guard_change(self):
        from .offline_plant import Clock,Plant
        from normal_gaze_motor import open_bus
        root=Path(__file__).resolve().parents[3]
        profile=json.loads((root/'bio_inspire/hardware/presentation_20261107/play_C1_angry_body25_trial.json').read_text())
        plant=Plant(profile,Clock())
        with patch.dict(sys.modules,{'serial':types.SimpleNamespace(Serial=plant.serial)}):
            b=open_bus()
        try:
            b.motion_speed=600;b.write=types.MethodType(bus_write(type(b).write),b)
            with self.assertRaises(ValueError):b.write(3,46,(50).to_bytes(2,'little'))
            b.sleepy_matched_native_trial=True
            for i,a,v,n in ((3,46,50,2),(5,46,100,2),(5,41,2,1)):
                b.write(i,a,v.to_bytes(n,'little'));self.assertEqual(int.from_bytes(b.read(i,a,n),'little'),v)
            with self.assertRaises(ValueError):b.write(5,41,b'\3')
            with self.assertRaises(ValueError):b.write(2,46,(50).to_bytes(2,'little'))
            with self.assertRaises(ValueError):b.write(2,21,b'\x08\x10\0')
        finally:b.close()

    def test_native_fold_write_and_readback_use_the_same_approved_speed(self):
        m,b=fixture.Tests().motor();c=m.controller
        c.sleepy_native_fold=None
        fn=fold_weight(sleepy_trial.sleepy_native_fold_weight)
        fn(c,20.,lambda:False)
        self.assertEqual(c.sleepy_native_fold['native_speed_raw'],50)
        self.assertEqual(b.reg[3][46],50)

    def test_head_setter_uses_exact_speed100_acc2_and_same_endpoint(self):
        m,b=fixture.Tests().motor();c=m.controller
        c.last_rows=b.snapshot();fn=setter(sleepy_trial.set_sleepy_trial)
        fn(c,True)
        self.assertEqual((b.reg[5][46],b.reg[5][41]),(100,2))
        self.assertEqual(b.reg[5][42],c.normal[5]+273)
        self.assertEqual(c.sleepy_phase_fold_nominal_s,3.5)
        self.assertFalse(c.bus.sleepy_matched_native_trial)

    def test_approved_faster_timing_keeps_the_same_path_and_small_command_steps(self):
        from .sleepy_phase_sync import SleepyPlan
        m,b=fixture.Tests().motor();c=m.controller;c.sleepy_phase_fold_nominal_s=3.5
        p=SleepyPlan(c,b.reg[2][42],20.);trace=[]
        rows=[dict(r)for r in c.last_rows]
        for k in range(81):
            q=p.step(rows,20+k*.05);trace.append(q)
            for row in rows:
                if row['id']in q:row['position_raw']=q[row['id']]
        self.assertTrue(p.commands_done);self.assertEqual(trace[-1],p.target)
        self.assertLessEqual(max(abs(b[3]-a[3])for a,b in zip(trace,trace[1:])),3)
        self.assertLessEqual(max(abs(b[5]-a[5])for a,b in zip(trace,trace[1:])),5)


if __name__=='__main__':unittest.main()
