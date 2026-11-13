import unittest


class Tests(unittest.TestCase):
    def config(self):
        return dict(maximum_gap_s=.2,stall_window_s=.3,minimum_samples=4,
                    ids={'4':dict(current_limit_raw=4,pwm_limit_raw=231,internal_error_limit_ticks=173)})

    def row(self,t,q=2000,**changes):
        r=dict(id=4,time_s=t,position_raw=q,current_raw=16,
               pwm_magnitude_raw=240,internal_error_ticks=180,decision='MONITOR')
        r.update(changes);return r

    def test_moving_head_contact_does_not_require_a_full_stall(self):
        from .effort_detection import ID4EffortEvidence
        m=ID4EffortEvidence(self.config())
        result=[m.update(self.row(k*.05,2000+k*20))for k in range(8)][-1]
        self.assertTrue(result['candidate_stop'])
        self.assertGreater(result['encoder_span_ticks'],2)

    def test_recorded_gentle_contact_is_not_hidden_by_global_motion_peaks(self):
        from copy import deepcopy
        from .effort_detection import ID4EffortEvidence
        config=self.config();before=deepcopy(config);m=ID4EffortEvidence(config)
        rows=[self.row(k*.05,2000+k*15,current_raw=8,
                       pwm_magnitude_raw=171,internal_error_ticks=125)for k in range(4)]
        self.assertTrue([m.update(r)for r in rows][-1]['candidate_stop'])
        self.assertEqual(config,before)

    def test_threshold_edges_short_pulse_gap_fault_and_other_ids_cannot_trigger(self):
        from .effort_detection import ID4EffortEvidence
        for changes in(dict(current_raw=4),dict(pwm_magnitude_raw=32),dict(internal_error_ticks=8),dict(decision='WOULD_HOLD_DATA'),dict(id=2)):
            m=ID4EffortEvidence(self.config())
            self.assertFalse(any(m.update(self.row(k*.05,**changes))['candidate_stop']for k in range(10)))
        m=ID4EffortEvidence(self.config())
        for k in range(3):self.assertFalse(m.update(self.row(k*.05))['candidate_stop'])
        self.assertFalse(m.update(self.row(.5))['candidate_stop'])
        m=ID4EffortEvidence(self.config())
        for k in range(10):
            self.assertFalse(m.update(self.row(k*.05,internal_error_ticks=125*(-1 if k%2 else 1)))['candidate_stop'])

    def test_trial_routes_axis4_only_when_explicit_monitor_enabled(self):
        from collections import deque
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        from .integration import adapter_class,consent,BaseAdapter
        from .effort_detection import ID4EffortEvidence
        for enabled in (False,True):
            cls=adapter_class(consent((1,2,4)),id4_effort_stop=enabled)
            a=object.__new__(cls);seen=[];events=[]
            a.auto_id1=NS(observe=lambda row:None,active=False)
            a.id2_context_monitor=None;a.effort_monitor=None;a.id2_effort_monitor=None
            a.id4_effort_monitor=ID4EffortEvidence(self.config())if enabled else None
            a.m=NS();a.enabled_ids={1,2,4};a.stop_writer=None;a.return_dispatch=False
            a.core=NS(phase='PLAY',pending=None,record=lambda *args,**kw:events.append(args[0]))
            with patch.object(BaseAdapter,'observe',lambda self,row,decision:seen.append(decision)):
                for k in range(8):
                    r=self.row(k*.05,2000+k*20);a.observe(r,r)
            self.assertEqual(seen[-1]['decision'],'WOULD_STOP_RESISTANCE'if enabled else'MONITOR')
            self.assertEqual(bool(events),enabled)

    def test_moving_id4_contact_through_uart_stops_resets_and_cleans_up(self):
        import tempfile
        from pathlib import Path
        from functools import partial
        from unittest.mock import patch
        from .test_integration import TrialPlant,harness
        from .integration import hooks,consent
        from shared.experiments.central_safety_controller_20261110.scenarios import contact_in_state
        class SlidingHead(TrialPlant):
            def refresh(self,i):
                super().refresh(i)
                if i==4 and i in self.contact and i not in self.held_ids and self.ram[i][40]==1:
                    a=self.ram[i];q=int.from_bytes(a[56:58],'little')+1
                    a[56:58]=q.to_bytes(2,'little')
                    a[67:69]=(q+180).to_bytes(2,'little')
                    a[60:62]=(240).to_bytes(2,'little')
                    a[69:71]=(16).to_bytes(2,'little')
        def after(w):
            a=w.motor.bus.central_feedback.brake_capture
            if a.core.phase=='WAIT_CLEARANCE'and a.id1_contact_released():w.motor.key(ord('r'))
        with tempfile.TemporaryDirectory()as out,patch.object(harness,'Plant',SlidingHead),patch.object(harness,'hooks',partial(hooks,trial_consent=consent((4,)),isolate_tof=True,id4_effort_stop=True)):
            r,w=harness.run(Path(out),contact_in_state('happy',4,after),seconds=30,enabled_ids=(4,),dark=True)
        self.assertEqual(r['phase'],'NORMAL_PARKED',r['error'])
        self.assertIsNone(r['error']);self.assertEqual(r['reset']['h'],0.)
        evidence=[e for e in r['events']if e['event']=='ID4_EXCESS_EFFORT_STOP_REQUEST']
        self.assertTrue(evidence);self.assertGreater(evidence[0]['evidence']['encoder_span_ticks'],2)
        a=w.motor.bus.central_feedback.brake_capture
        self.assertEqual(a.core.event['axis'],4)
        self.assertEqual(a.writers[0].contact_axis,4)
        self.assertTrue(r['stops']);self.assertTrue(r['cleanup_confirmed'])
