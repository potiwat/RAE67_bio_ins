"""Opt-in experiment checks; no hardware imports or real actuator access."""
import unittest
from types import SimpleNamespace as NS
from threading import Event

from bio_inspire.runtime.automatic_trial import AutomaticTrial, ScriptAHM, stimulus_at, schedule_sha256, validate,BUTTON,TOUCH,NEAR


class Tests(unittest.TestCase):
    def test_paired_grid_same_S_old_H_and_decay(self):
        c0,c1=ScriptAHM('C0'),ScriptAHM('C1')
        for a in (c0,c1):a.start(100.)
        previous_h=0.;previous_s=0.
        for i in range(12001):
            t=100+i*.05
            a,b=c0.step(t),c1.step(t)
            self.assertEqual(a['stimulus'],b['stimulus'])
            self.assertEqual(a['h'],b['h'])
            if i:self.assertAlmostEqual(a['h'],previous_h+.05*(.8*previous_s-.8*previous_h))
            self.assertEqual(a['r_used'],a['stimulus'])
            self.assertEqual(b['r_used'],b['h'])
            self.assertTrue(.1<=b['phi']<=.13)
            previous_h=a['h'];previous_s=a['stimulus']
        end=BUTTON[0][1]
        self.assertEqual(stimulus_at(end+.1),0.)
        self.assertGreater(c1.h_values[round((end+.1)/.05)],0.)
        self.assertEqual(c0.last_view['schedule_sha256'],schedule_sha256())

    def test_scripted_edges_full_near_cycle_and_no_replay(self):
        t=AutomaticTrial('C1');t.start(10.)
        a,b=BUTTON[0]
        for elapsed in (0.,a-.1,a+.05,a+.2,b+.1):t.advance(10+elapsed)
        self.assertEqual(t.sources['button'].drain_events(41.1),[10+a])
        self.assertEqual(t.sources['button'].drain_events(41.2),[])
        self.assertFalse(t.sources['button'].edge.stable)
        a,b=NEAR[0]
        t.advance(10+a+.1);self.assertTrue(t.near)
        self.assertEqual(t.distance_event,'near')
        t.advance(10+a+.2);self.assertIsNone(t.distance_event)
        t.advance(10+b+.1);self.assertFalse(t.near)
        self.assertEqual(t.distance_event,'clear')

    def test_live_near_aborts_and_never_rearms(self):
        t=AutomaticTrial('C0');t.start(0.)
        m=NS(controller=NS(state='READY'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=True),lab07_recorder=None,physical_button=None,physical_touch=None)
        m.keys=[];m._key=lambda k:m.keys.append(k)
        self.assertFalse(t.service(m,.1));self.assertEqual(t.state,'aborted')
        self.assertEqual(m.keys,[ord('h')])
        m.distance_gate.near=False
        self.assertFalse(t.service(m,.2));self.assertEqual(m.keys,[ord('h')])

    def test_missing_clock_or_safety_not_silently_resumed(self):
        for reason in ('gap','operator','controller','recorder'):
            t=AutomaticTrial('C1');t.start(10.)
            m=NS(controller=NS(state='READY'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
                distance_gate=NS(near=False),lab07_recorder=None,physical_button=None,physical_touch=None,
                _key=lambda k:None)
            self.assertTrue(t.service(m,10.1))
            now=11.2 if reason=='gap' else 10.2
            if reason=='operator':m.operator_stopped=True
            if reason=='controller':m.controller.state='FAULT'
            if reason=='recorder':m.lab07_recorder=NS(error='disk full',dropped=0)
            self.assertFalse(t.service(m,now));self.assertEqual(t.state,'aborted')

    def test_schedule_covers_all_inputs_early_and_repeats_without_long_idle_gaps(self):
        self.assertLessEqual(BUTTON[0][0],10.)
        self.assertLessEqual(NEAR[0][0],90.)
        self.assertTrue(any(40<=a<=60 for a,b in TOUCH))
        self.assertEqual(len(NEAR),5)

    def test_short_ToF_wait_holds_then_recovers_without_resetting_script(self):
        t=AutomaticTrial('C1');t.start(0.)
        m=NS(controller=NS(state='READY'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=False),distance_view={'error':None},lab07_recorder=None,
             physical_button=None,physical_touch=None,_key=lambda k:self.fail('Transient wait must not issue STOP'))
        self.assertTrue(t.service(m,.1))
        m.controller.state='WAIT_TOF'
        self.assertFalse(t.service(m,.2));self.assertEqual(t.state,'running')
        self.assertFalse(t.service(m,.4))
        m.controller.state='READY'
        self.assertTrue(t.service(m,.5));self.assertTrue(t.recovered_from_pause)
        self.assertEqual(t.started,0.)
        self.assertEqual(t.status(.5)['distance_pauses'][0]['end_s'],.5)

    def test_persistent_ToF_wait_aborts_after_half_second(self):
        t=AutomaticTrial('C0');t.start(0.)
        m=NS(controller=NS(state='WAIT_TOF'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=False),distance_view={'error':None},lab07_recorder=None,
             physical_button=None,physical_touch=None,_key=lambda k:None)
        t.service(m,.1);self.assertEqual(t.state,'running')
        t.service(m,.61);self.assertEqual(t.state,'aborted')
        self.assertEqual(t.reason,'ToF_wait_over_0.5s')

    def test_delayed_healthy_recovery_cannot_bypass_wait_deadline(self):
        t=AutomaticTrial('C0');t.start(0.)
        m=NS(controller=NS(state='WAIT_TOF'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=False),distance_view={'error':None},lab07_recorder=None,
             physical_button=None,physical_touch=None,_key=lambda k:None)
        t.last_callback=7.8;t.service(m,7.9);t.service(m,8.1)
        m.controller.state='READY';self.assertFalse(t.service(m,8.6))
        self.assertEqual(t.state,'aborted')

    def test_script_input_history_advances_while_outputs_are_paused(self):
        t=AutomaticTrial('C1');t.start(0.)
        m=NS(controller=NS(state='WAIT_TOF'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=False),distance_view={'error':None},lab07_recorder=None,
             physical_button=None,physical_touch=None,_key=lambda k:None)
        t.last_callback=7.8;t.service(m,7.9);t.service(m,8.1)
        self.assertTrue(t.status(8.1)['button'])
        self.assertEqual(t.replay.step(8.1)['stimulus'],1.)
        m.controller.state='READY';t.service(m,8.2)
        self.assertEqual(t.sources['button'].drain_events(8.2),[8.])

    def test_requires_opt_in_recorded_gate_and_600_seconds(self):
        self.assertFalse(validate({}))
        for c in ({'lab07_automatic_script':True}, {'lab07_automatic_script':'yes'}):
            with self.assertRaises(ValueError):validate(c)
        self.assertTrue(validate(dict(lab07_automatic_script=True,lab07_recording_seconds=600,
            lab07_start_button_presses=5,automatic_fsm_enabled=True,ahm_scope='all_states',normal_ahm_condition='C1')))

    def test_actual_owner_uses_script_and_records_all_topics_without_physical_relabelling(self):
        c0=self.owner_trial('C0');c1=self.owner_trial('C1')
        self.assertEqual(c0['initial'],c1['initial'])
        self.assertEqual(c0['S'],c1['S'])

    def owner_trial(self,condition):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from .runtime_integration import ROOT,run_runtime
        from .ahm_input_bridge import InputFrame
        from .ros13 import Encoder,TOPICS
        class Recorder:
            def __init__(self):
                self.first=None;self.end_seen=False;self.error=None;self.dropped=0
                self.rows=[];self.topics=set();self.encoder=None;self.closed=False
            def record(self,row):
                if self.first is None:self.first=row['time_s']
                messages=self.encoder.encode(row,len(self.rows))
                self.topics.update(m['topic'] for m in messages)
                self.rows.append(dict(time_s=row['time_s'],experiment=row.get('experimental_inputs'),
                    ahm=(row.get('breathing_rhythm') or {}).get('state_ahm'),
                    emotion=row['fsm']['state'],digital=row['digital_inputs'],
                    marker=row.get('measurement_start')))
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as folder:
            root=Path(folder);profile=json.loads((ROOT/'bio_inspire/hardware/boot_ready_c1.json').read_text())
            profile.update(lab07_recording_seconds=600,lab07_start_button_presses=5,lab07_automatic_script=True)
            p=root/'profile.json';p.write_text(json.dumps(profile))
            frames=[InputFrame(i*.05,i*.05,any(a<=i*.05<a+.25 for a in (2.,3.,4.,5.,6.)),
                    20<=i*.05<21.,'range',1.2,f'physical_{i}') for i in range(12300)]
            recorder=Recorder()
            def prepare(m):
                recorder.encoder=Encoder(dict(profile=profile,run_id='mock',pair_id='P1',condition=condition,
                    origin='virtual_test_only',clock='virtual_clock'))
                return recorder
            with patch('bio_inspire.runtime.session_recording.prepare_recorder',side_effect=prepare):
                result=run_runtime(root/'run',profile_path=p,condition=condition,duration_s=615,frames_override=frames)
            self.assertEqual(recorder.topics,set(TOPICS))
            self.assertTrue(recorder.closed);self.assertNotIn('FAULT',result['controller_states'])
            self.assertFalse(result['forbidden_writes']);self.assertEqual(result['bounds_violations'],0)
            states={r['emotion'] for r in recorder.rows}
            self.assertEqual(states,{'normal','sleepy','interested','happy','angry','afraid'})
            self.assertEqual(recorder.rows[0]['marker']['initial_h'],0.)
            early=[r for r in recorder.rows if 20<r['time_s']<21]
            self.assertTrue(any(r['digital']['touch']['stable_pressed'] for r in early))
            self.assertTrue(all(r['experiment']['touch'] is False for r in early))
            self.assertTrue(all(r['emotion']!='happy' for r in early))
            self.assertTrue(all(r['experiment']['source']=='scripted_experimental_inputs' for r in recorder.rows))
            self.assertEqual(recorder.rows[-1]['experiment']['state'],'complete')
            self.assertEqual(recorder.rows[-1]['emotion'],'normal')
            active=[r for r in recorder.rows if r['ahm'] is not None]
            for r in active:
                a=r['ahm']
                self.assertEqual(a['r_used'],a['stimulus'] if condition=='C0' else a['h'])
            return dict(initial=recorder.rows[0]['marker']['initial_oscillator_bank'],
                        S=[(r['experiment']['elapsed_s'],r['ahm']['stimulus']) for r in active])

    def test_complete_returns_once_and_cannot_restart_from_M(self):
        t=AutomaticTrial('C0');t.start(0.)
        m=NS(controller=NS(state='READY'),operator_stopped=False,stopping=Event(),urgent_stop=Event(),
             distance_gate=NS(near=False),lab07_recorder=None,physical_button=None,physical_touch=None,
             _key=lambda k:None)
        for i in range(1,12001):t.service(m,i*.05)
        self.assertEqual(t.state,'complete')
        self.assertFalse(t.service(m,600.1))

    def test_aborted_trial_cannot_be_marked_complete_by_recorder(self):
        import tempfile,json
        from pathlib import Path
        from bio_inspire.runtime.session_recording import SessionRecorder
        with tempfile.TemporaryDirectory() as folder:
            recorder=SessionRecorder(folder,'C1',600.)
            recorder.record(dict(time_s=0.,experimental_inputs={'state':'running'}))
            recorder.record(dict(time_s=600.,experimental_inputs={'state':'aborted'}))
            recorder.close()
            self.assertFalse(json.loads((Path(folder)/'summary.json').read_text())['complete'])

    def test_actual_owner_safety_abort_and_early_Q_invalidate_trial(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from .runtime_integration import ROOT,run_runtime
        from .ahm_input_bridge import InputFrame
        class Recorder:
            first=None;end_seen=False;error=None;dropped=0;invalid=False
            def __init__(self):self.rows=[]
            def record(self,row):
                if self.first is None:self.first=row['time_s']
                self.rows.append(row.get('experimental_inputs'))
            def close(self):pass
        for case in ('near','STOP','UART','ToF','Q'):
            with self.subTest(case=case),tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as folder:
                root=Path(folder);profile=json.loads((ROOT/'bio_inspire/hardware/boot_ready_c1.json').read_text())
                profile.update(lab07_recording_seconds=600,lab07_start_button_presses=5,lab07_automatic_script=True)
                p=root/'profile.json';p.write_text(json.dumps(profile))
                frames=[InputFrame(i*.05,i*.05,any(a<=i*.05<a+.25 for a in (2.,3.,4.,5.,6.)),False,
                        'range',.16 if case=='near' and i*.05>=10 else 1.2,f'physical_{i}') for i in range(300)]
                kwargs={'STOP':dict(stop_s=10.),'UART':dict(bus_fault_s=10.),'ToF':dict(tof_stall=(10.,12.))}.get(case,{})
                rec=Recorder()
                with patch('bio_inspire.runtime.session_recording.prepare_recorder',return_value=rec):
                    r=run_runtime(root/'run',profile_path=p,duration_s=15.,frames_override=frames,**kwargs)
                self.assertTrue(rec.invalid)
                self.assertFalse(r['forbidden_writes']);self.assertEqual(r['bounds_violations'],0)
                if case!='Q':self.assertEqual(rec.rows[-1]['state'],'aborted')

    def test_actual_owner_recovers_short_ToF_pause_and_restores_same_emotion_route(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from .runtime_integration import ROOT,run_runtime
        from .ahm_input_bridge import InputFrame
        class Recorder:
            first=None;end_seen=False;error=None;dropped=0;invalid=False
            def __init__(self):self.rows=[]
            def record(self,row):
                if self.first is None:self.first=row['time_s']
                self.rows.append((row['time_s'],row['state'],row['behavior'],row.get('experimental_inputs')))
            def close(self):pass
        with tempfile.TemporaryDirectory(dir=ROOT/'bio_inspire/results') as folder:
            root=Path(folder);profile=json.loads((ROOT/'bio_inspire/hardware/boot_ready_c1.json').read_text())
            profile.update(lab07_recording_seconds=600,lab07_start_button_presses=5,lab07_automatic_script=True)
            p=root/'profile.json';p.write_text(json.dumps(profile))
            frames=[InputFrame(i*.05,i*.05,any(a<=i*.05<a+.25 for a in (2.,3.,4.,5.,6.)),False,
                    'range',1.2,f'physical_{i}') for i in range(500)]
            rec=Recorder()
            with patch('bio_inspire.runtime.session_recording.prepare_recorder',return_value=rec):
                r=run_runtime(root/'run',profile_path=p,duration_s=25.,frames_override=frames,tof_stall=(17.,17.25))
            self.assertNotIn('FAULT',r['controller_states'])
            self.assertTrue(any(x[1]=='WAIT_TOF' for x in rec.rows))
            after=[x for x in rec.rows if 17.5<x[0]<24.]
            self.assertTrue(after)
            self.assertTrue(all(x[3]['state']=='running' and x[2]!='distance_wait' for x in after))
            self.assertTrue(any(x[3]['distance_pauses'] and x[3]['distance_pauses'][-1]['end_s'] is not None for x in after))

if __name__=='__main__':unittest.main()
