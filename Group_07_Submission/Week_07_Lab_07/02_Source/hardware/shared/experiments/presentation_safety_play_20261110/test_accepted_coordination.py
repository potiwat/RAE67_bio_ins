"""End-to-end accepted posture changes through the real Safety runtime."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from . import offline_harness as harness
from .integration import hooks,consent
from .test_auto_release import ProbePlant
from .restart import take_restart
# Keep the real modules loaded before the emulator temporarily replaces
# sys.modules for serial; otherwise patch.dict removes lazy imports on exit
# while namespace-package attributes still refer to the removed module.
from bio_inspire.runtime import sleepy_trial,angry_approach,state_rhythms


class Tests(unittest.TestCase):
    def test_accepted_changes_preserve_contact_recovery_in_every_state(self):
        from . import test_auto_release as cases
        for state in ('normal','interested','happy','angry','afraid','sleepy'):
            for sid in (1,2,4):
                with self.subTest(state=state,id=sid),patch.object(cases,'hooks',lambda *a,**kw:hooks(*a,**{**kw,'accepted_coordination':True})):
                    r,w=cases.AutoReleaseTests().run_case(state,sid)
                self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False))
                self.assertTrue(r['cleanup_confirmed']);self.assertEqual(r['reset']['h'],0.)

    def test_active_fast_fold_contact_stops_and_auto_returns_on_all_selected_axes(self):
        for sid in (1,2,4):
            with self.subTest(id=sid):
                def scenario(w):
                    m=w.motor;c=m.controller;t=w.clock()-w.start
                    if t>2 and not getattr(w,'requested_sleepy',False) and c.state in ('READY','FOLLOWING'):
                        w.requested_sleepy=True;m.key(ord('s'))
                    p=getattr(c,'sleepy_phase_sync_plan',None)
                    if not w.triggered and p is not None and not p.commands_done and min(p.pair.progress.values())>=p.unit*.1:
                        w.triggered=True;w.trigger_time=w.clock();w.fold_contact=True
                        w.plant.contact.add(sid)
                    if w.triggered and w.clock()-w.trigger_time>1.:
                        w.plant.contact.clear();w.clearance=True
                    if take_restart(m,255):w.resumed=True;m.stopping.set()
                def selected(*a,**kw):
                    return hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),
                        'id2_contact_recovery':True,'auto_contacts':True,'isolate_tof':True,
                        'resume_after_normal':True,'accepted_coordination':True})
                with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',selected):
                    r,w=harness.run(Path(d),scenario,seconds=35,enabled_ids=())
                self.assertTrue(getattr(w,'fold_contact',False),(r['error'],r['controller_error'],r['states']))
                self.assertIsNone(r['error']);self.assertTrue(getattr(w,'resumed',False))
                self.assertTrue(r['cleanup_confirmed']);self.assertEqual(r['reset']['h'],0.)
                self.assertTrue(all(x['address']not in(18,21,22,23,33)for x in r['mutations']))

    def test_no_cleanup_uart_before_first_start_or_if_worker_is_still_live(self):
        from types import SimpleNamespace as NS
        from .sleepy_matched_native import cleanup_sessions
        opened=Mock()
        cleanup_sessions(opened,[]);opened.assert_not_called()
        session=NS(closing=True,owner=NS(finished=NS(is_set=lambda:False),cleanup_confirmed=True))
        with self.assertRaises(RuntimeError):cleanup_sessions(opened,[session])
        opened.assert_not_called()


if __name__=='__main__':unittest.main()
