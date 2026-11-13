"""Real runtime, memory UART, ordinary sensor input stress; no hardware."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import offline_harness as harness
from .test_auto_release import ProbePlant
from .integration import hooks,consent


def selected(*a,**kw):
    return hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),
        'accepted_coordination':True,'auto_contacts':True,'resume_after_normal':True,
        'isolate_tof':True,'id2_contact_recovery':True})


def run(scenario,seconds):
    with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',selected):
        return harness.run(Path(d),scenario,seconds=seconds,enabled_ids=())


class Tests(unittest.TestCase):
    def test_repeated_real_input_changes_include_interrupted_sleepy_fold_without_false_stop(self):
        for jitter in (0.,.03,.07):
            def scenario(w):
                t=w.clock()-w.start-jitter
                w.inputs['button'].pressed=any(a<t<a+.22 for a in (2.,33.,34.))
                w.inputs['touch'].pressed=(5.<t<6. or 30.<t<32.
                    or any(a<t<a+.22 for a in (8.,8.55,9.1)))
                w.distance.cm=15. if 10.<t<18. else 50.
            with self.subTest(jitter=jitter):
                r,w=run(scenario,44.)
                self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
                self.assertNotEqual(r['controller_state'],'FAULT',(r['controller_error'],r['states']))
                self.assertEqual(r['stops'],[])
                self.assertTrue(set(('normal','interested','happy','angry','afraid','sleepy'))<=set(r['states']),r['states'])
                self.assertTrue(r['source_profile_unchanged'])

    def test_isolated_tof_and_led_failure_do_not_stop_the_new_postures(self):
        for kind in ('hardware_error','unreliable','stale'):
            def scenario(w):
                t=w.clock()-w.start
                if 2<t<5:w.distance.kind=kind
                else:w.distance.kind='range'
                w.inputs['touch'].pressed=6<t<9
                if (w.motor.behavior_trial=='happy'and w.motor.led_ring is not None
                        and not getattr(w,'led_injected',False)):
                    def fail():raise ValueError('injected LED failure')
                    w.motor.led_ring.pixels.show=fail;w.led_injected=True
            with self.subTest(kind=kind):
                r,w=run(scenario,18.)
                self.assertIsNone(r['error']);self.assertTrue(r['cleanup_confirmed'])
                self.assertNotEqual(r['controller_state'],'FAULT')
                self.assertTrue(w.led_injected);self.assertTrue(w.motor.presentation_led_disabled)
                self.assertEqual(r['stops'],[])


if __name__=='__main__':unittest.main()
