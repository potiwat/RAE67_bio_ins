import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch,Mock
from sync_position_writer import SyncPositionError
from shared.experiments.central_safety_controller_20261110.runtime import PlayPreempted


class Tests(unittest.TestCase):
    def error(self,message):
        return SyncPositionError(dict(error=message,broadcast_sent=True,requires_hold=True,verified_ids=[]))

    def test_only_explicit_owner_close_can_unwind_to_existing_final_hold(self):
        from .close_sync import close_aware_sync
        for closing in (False,True):
            event=Mock();bus=NS(central_feedback=NS(owner=NS(stopping=NS(is_set=lambda:closing)),recorder=NS(event=event)))
            error=self.error('Cancelled after Sync Write; confirmation incomplete')
            fn=close_aware_sync(Mock(side_effect=error),bus)
            if closing:
                with self.assertRaises(PlayPreempted):fn({2:2837,3:2746},lambda:True)
                event.assert_called_once()
            else:
                with self.assertRaises(SyncPositionError):fn({2:2837,3:2746},lambda:True)
                event.assert_not_called()

    def test_partial_writes_readback_mismatch_and_unknown_owner_are_not_hidden(self):
        from .close_sync import close_aware_sync
        for message in ('Partial Sync Write transmission; goals uncertain','ID2 Sync position readback mismatch'):
            bus=NS(central_feedback=NS(owner=NS(stopping=NS(is_set=lambda:True))))
            with self.assertRaises(SyncPositionError):close_aware_sync(Mock(side_effect=self.error(message)),bus)({},None)
        with self.assertRaises(SyncPositionError):close_aware_sync(Mock(side_effect=self.error('Cancelled after Sync Write; confirmation incomplete')),NS())({},None)

    def test_real_runtime_q_after_broadcast_still_verifies_hold_and_closes_uart(self):
        from . import offline_harness as harness
        from .test_auto_release import ProbePlant
        from .integration import hooks,consent
        def selected(*a,**kw):return hooks(*a,**{**kw,'trial_consent':consent((1,2,4)),'accepted_coordination':True,'auto_contacts':True,'resume_after_normal':True,'isolate_tof':True,'id2_contact_recovery':True})
        def scenario(w):
            if w.clock()-w.start<2 or getattr(w,'injected',False):return
            def after_packet(op):
                if op!=131 or w.plant.frames[-1]['packet'][5:7]!=[42,2]:return
                w.injected=True;w.motor.stopping.set();w.plant.on_packet=None
            w.plant.on_packet=after_packet
        with tempfile.TemporaryDirectory()as d,patch.object(harness,'Plant',ProbePlant),patch.object(harness,'hooks',selected):
            r,w=harness.run(Path(d),scenario,seconds=5,enabled_ids=())
        self.assertTrue(w.injected);self.assertTrue(r['cleanup_confirmed'])
        self.assertNotEqual(r['controller_state'],'FAULT');self.assertIsNone(r['error'])
        self.assertTrue(w.plant.closed)


if __name__=='__main__':unittest.main()
