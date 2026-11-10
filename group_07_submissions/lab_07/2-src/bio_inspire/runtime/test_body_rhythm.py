"""Course oscillator timing, envelope, arbitration, and bounded motor mapping."""
import math
import unittest
from body_rhythm import BodyRhythm

class Tests(unittest.TestCase):
    def test_sleepy_keeps_rhythm_and_current_body_center_without_face(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller();c.face_ready_for_interest=True
        m=SimpleNamespace(controller=c,behavior_trial='interested',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(interested_amplitude_deg=1.9,sleepy_amplitude_deg=2.,time_scale=.5)
        d.step(m,0.);d.step(m,2.)
        c.sleepy_body_reference=dict(d.centers);m.behavior_trial='sleepy';c.face_ready_for_interest=False
        d.step(m,2.1);d.step(m,4.1)
        self.assertEqual(d.centers,{2:2735,3:2848})
        self.assertEqual(d.rhythm.envelope,1.)
        self.assertAlmostEqual(d.rhythm.status()['amplitude_deg_limit'],2.)
        self.assertEqual(d.rhythm.status()['time_scale'],.5)
        self.assertTrue(all(abs(b.reg[i][42]-d.centers[i])<=23 for i in (2,3)))

    def test_time_stretch_preserves_model_samples_and_interpolates_between_them(self):
        slow=BodyRhythm(amplitude_deg=2.,phi=.1,time_scale=.5)
        normal=BodyRhythm(amplitude_deg=2.,phi=.1)
        slow.advance(0.,True);normal.advance(0.,True)
        for n in range(1,121):
            normal.advance(n*.05,True);slow.advance(n*.1,True)
            self.assertAlmostEqual(normal.o1,slow.o1)
        a,b=slow.o1,slow.o2
        following=math.tanh(1.1*(math.cos(.1)*a+math.sin(.1)*b))
        slow.advance(12.05,True)
        self.assertAlmostEqual(slow.offsets()[3],2*4096/360*(a+following)/2)
        self.assertEqual(slow.updates,120)
        self.assertEqual(slow.status()['time_scale'],.5)
        self.assertEqual(slow.status()['wall_model_step_s'],.1)
        self.assertEqual(slow.dt_s,.05)
        with self.assertRaises(ValueError):BodyRhythm(time_scale=.01)

    def test_isolated_rhythm_writes_only_selected_joint(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        for sid in (2,3):
            b,c=PoseTests().controller();b.calls.clear()
            m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
            d=BodyRhythmDriver(normal_amplitude_deg=2.,phi=.1,active_joint_ids=(sid,))
            d.step(m,0.);d.step(m,2.)
            self.assertTrue(b.calls)
            self.assertTrue(all(i==sid and a==42 for i,a,v in b.calls))
            other=3 if sid==2 else 2
            self.assertEqual(b.reg[other][42],c.normal[other])
            self.assertEqual(d.rhythm.status()['active_joint_ids'],[sid])
        with self.assertRaises(ValueError):BodyRhythmDriver(active_joint_ids=(1,))

    def test_slow_breathing_phi_keeps_model_dt_and_reduces_cycle_rate(self):
        r=BodyRhythm(amplitude_deg=1.9,phi=.1);crossings=[];previous=r.o1
        for n in range(1201):
            r.advance(n*.05,True)
            if n>200 and previous<0<=r.o1:crossings.append(n*.05)
            previous=r.o1
        period=sum(b-a for a,b in zip(crossings,crossings[1:]))/(len(crossings)-1)
        self.assertTrue(3.3<period<3.5)
        self.assertEqual(r.dt_s,.05);self.assertEqual(r.alpha,1.1)
        self.assertEqual(r.status()['phi'],.1)
        with self.assertRaises(ValueError):BodyRhythm(phi=.01)

    def test_interested19_waits_for_neck_return_then_fades_in_without_phase_reset(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller();c.face_ready_for_interest=True
        m=SimpleNamespace(controller=c,behavior_trial='interested',operator_stopped=False,joint_mode=False,interested_roll_due=2.)
        d=BodyRhythmDriver(normal_amplitude_deg=1.9,interested_amplitude_deg=1.9)
        b.calls.clear();d.step(m,0.);d.step(m,1.)
        self.assertEqual(b.calls,[])
        m.interested_roll_due=None;c.current_roll_goal=c.normal[4]
        c.last_rows[3]['position_raw']=c.normal[4]-80
        d.step(m,2.);self.assertEqual(b.calls,[])
        c.last_rows[3]['position_raw']=c.normal[4]
        d.step(m,3.);self.assertEqual(d.rhythm.envelope,0.)
        d.step(m,4.);self.assertAlmostEqual(d.rhythm.envelope,.5)
        d.step(m,5.);self.assertAlmostEqual(d.rhythm.envelope,1.)
        self.assertAlmostEqual(d.rhythm.status()['amplitude_deg_limit'],1.9)
        self.assertEqual(d.centers,{2:2735,3:2848})
        self.assertEqual(d.rhythm.updates,100)
        self.assertTrue(all(i in (2,3) and a==42 for i,a,v in b.calls))
        m.operator_stopped=True;b.calls.clear();d.step(m,5.1);self.assertEqual(b.calls,[])

    def test_manual_driver_updates_normal_only_and_does_not_override_stop(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(normal_amplitude_deg=2.,normal_amplitude_mode='manual_1_3')
        b.calls.clear()
        d.step(m,0.);d.request_amplitude(2.5,0.);d.step(m,2.)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],2.5)
        self.assertTrue(all(i in (2,3) and a==42 for i,a,v in b.calls if a==42 and v!=c.normal[i]))
        m.behavior_trial='interested';c.face_ready_for_interest=True;d.step(m,2.05)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],1.)
        b.calls.clear();m.operator_stopped=True;d.request_amplitude(3.,2.05);d.step(m,4.05)
        self.assertEqual(b.calls,[])

    def test_manual_gain_has_fractional_steps_and_smooth_two_second_transition(self):
        from body_rhythm import ManualAmplitude
        a=ManualAmplitude(2.)
        self.assertEqual(a.value(0.),2.)
        a.request(2.5,0.)
        self.assertEqual(a.value(0.),2.)
        self.assertAlmostEqual(a.value(1.),2.25)
        self.assertEqual(a.value(2.),2.5)
        a.request(1.5,2.);self.assertEqual(a.value(4.),1.5)
        for bad in (0.,3.1,2.55,float('nan'),True):
            with self.assertRaises(ValueError):a.request(bad,4.)

    def test_smooth_amplitude_is_bounded_replayable_and_independent_of_call_rate(self):
        from body_rhythm import SmoothAmplitude
        a=SmoothAmplitude(seed=0);b=SmoothAmplitude(seed=0)
        self.assertEqual(a.value(0.),1.)
        values=[a.value(n*.05) for n in range(1,161)]
        self.assertTrue(all(1<=v<=2 for v in values))
        self.assertGreater(max(values)-min(values),.1)
        b.value(0.);self.assertAlmostEqual(b.value(8.),values[-1])
        self.assertLess(abs(a.value(8.00001)-values[-1]),1e-6)
        with self.assertRaises(ValueError):a.value(7.)

    def test_variable_normal_keeps_interest_fixed_and_stop_silent(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(normal_amplitude_mode='smooth_1_2',variation_seed=0)
        d.step(m,0.);d.step(m,2.)
        self.assertGreater(d.rhythm.status()['amplitude_deg_limit'],1.)
        self.assertLessEqual(d.rhythm.status()['amplitude_deg_limit'],2.)
        self.assertEqual(d.rhythm.status()['variation_seed'],0)
        m.behavior_trial='interested';c.face_ready_for_interest=True;d.step(m,2.05)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],1.)
        b.calls.clear();m.operator_stopped=True;d.step(m,4.)
        self.assertEqual(b.calls,[])

    def test_normal3_mapping_keeps_course_phase_and_interest_at1(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(normal_amplitude_deg=3.)
        d.step(m,0.);d.step(m,2.)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],3.)
        self.assertAlmostEqual(d.rhythm.offsets()[3],3*4096/360*d.rhythm.o1)
        self.assertLessEqual(abs(b.reg[3][42]-c.normal[3]),35)
        r=BodyRhythm();r.advance(0.,True);r.advance(2.,True)
        self.assertAlmostEqual(r.o1,d.rhythm.o1)
        m.behavior_trial='interested';c.face_ready_for_interest=True
        d.step(m,2.05);d.step(m,4.05)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],1.)
        self.assertEqual(d.centers,{2:c.normal[2]-102,3:c.normal[3]+102})
        self.assertLessEqual(abs(b.reg[3][42]-d.centers[3]),12)
        self.assertEqual(d.rhythm.updates,81)

    def test_course_simultaneous_update_and_same_phase_across_state_changes(self):
        r=BodyRhythm();a,b=r.o1,r.o2;r.advance(10.,False)
        r.advance(10.05,True)
        self.assertAlmostEqual(r.o1,math.tanh(1.1*(math.cos(.2)*a+math.sin(.2)*b)))
        self.assertAlmostEqual(r.o2,math.tanh(1.1*(-math.sin(.2)*a+math.cos(.2)*b)))
        before=r.updates;r.advance(10.10,False);r.advance(10.15,True)
        self.assertEqual(r.updates,before+2)

    def test_jitter_runs_model_steps_but_emits_only_latest_bounded_offset(self):
        a=BodyRhythm();b=BodyRhythm();a.advance(0.,True);b.advance(0.,True)
        for n in range(1,41):a.advance(n*.05,True)
        b.advance(2.,True)
        self.assertEqual(a.updates,b.updates)
        self.assertAlmostEqual(a.o1,b.o1);self.assertAlmostEqual(a.envelope,1.)
        offsets=a.offsets();self.assertEqual(offsets[2],-offsets[3])
        self.assertLessEqual(abs(offsets[2]),4096/360)
        a.advance(3.,False);self.assertAlmostEqual(a.envelope,.5)
        a.advance(4.,False);self.assertEqual(a.offsets(),{2:0.,3:0.})

    def test_invalid_clock_and_unapproved_parameters_rejected(self):
        r=BodyRhythm();r.advance(2.,False)
        for bad in (1.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):r.advance(bad,True)
        with self.assertRaises(ValueError):BodyRhythm(amplitude_deg=8)

    def test_driver_only_writes_body_and_never_writes_during_action_or_stop(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver();b.calls.clear();d.step(m,0.);d.step(m,1.)
        self.assertTrue(b.calls)
        self.assertTrue(all(i in (2,3) and a==42 for i,a,v in b.calls))
        for i in (2,3):self.assertLessEqual(abs(b.reg[i][42]-c.normal[i]),12)
        self.assertEqual(c.rhythm_base_reference,{2:c.normal[2],3:c.normal[3]})
        c.pose_route=SimpleNamespace(phase='look');b.calls.clear();d.step(m,2.)
        self.assertEqual(b.calls,[]);self.assertEqual(d.rhythm.updates,40)
        c.pose_route=None;m.operator_stopped=True;d.step(m,3.)
        self.assertEqual(b.calls,[])

    def test_happy_rate_change_preserves_phase_and_moves_both_body_joints(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(normal_amplitude_deg=2.,time_scale=.5,phi=.1,happy_amplitude_deg=2.,happy_time_scale=.75)
        d.step(m,0.);d.step(m,2.)
        phase=(d.rhythm.o1,d.rhythm.o2,d.rhythm.updates)
        centers=dict(d.centers);m.behavior_trial='happy'
        d.step(m,2.)
        self.assertEqual(phase,(d.rhythm.o1,d.rhythm.o2,d.rhythm.updates))
        self.assertEqual(d.centers,centers);self.assertEqual(d.rhythm.time_scale,.75)
        d.step(m,3.)
        self.assertAlmostEqual(d.rhythm.logical_elapsed_s,1.75)
        self.assertEqual(d.rhythm.offsets()[2],-d.rhythm.offsets()[3])
        self.assertGreater(abs(d.rhythm.offsets()[2]),0)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],2.)
        m.behavior_trial='sleepy';d.sleepy_amplitude_deg=2.;c.sleepy_body_reference=centers
        d.step(m,3.);d.step(m,4.)
        self.assertAlmostEqual(d.rhythm.logical_elapsed_s,2.25)

    def test_happy4_doubles_dance_gain_without_expanding_normal_slider(self):
        from body_rhythm import BodyRhythmDriver,validate_manual_amplitude
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller()
        m=SimpleNamespace(controller=c,behavior_trial='normal',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(normal_amplitude_deg=2.,phi=.1,time_scale=.5,happy_amplitude_deg=4.)
        d.step(m,0.);d.step(m,2.)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],2.)
        c.happy_body_reference=dict(d.centers);m.behavior_trial='happy'
        d.step(m,2.);d.step(m,3.)
        self.assertEqual(d.rhythm.status()['amplitude_deg_limit'],4.)
        self.assertEqual(d.rhythm.time_scale,.75)
        self.assertAlmostEqual(d.rhythm.offsets()[3],4*4096/360*d.rhythm.envelope*d.rhythm.interpolated_o1)
        for row in b.snapshot():
            if row['id'] in (2,3):self.assertTrue(c.bus.windows[row['id']][0]<=row['position_raw']<=c.bus.windows[row['id']][1])
        with self.assertRaises(ValueError):validate_manual_amplitude(4.)
        with self.assertRaises(ValueError):BodyRhythm(amplitude_deg=4.)

    def test_happy_body_targets_reach_six_degrees_without_changing_yaw_gain(self):
        from body_rhythm import BodyRhythmDriver
        from test_button_look import Tests as PoseTests
        from types import SimpleNamespace
        b,c=PoseTests().controller();c.happy_body_reference={2:c.normal[2],3:c.normal[3]}
        m=SimpleNamespace(controller=c,behavior_trial='happy',operator_stopped=False,joint_mode=False)
        d=BodyRhythmDriver(phi=.1,time_scale=.5,happy_amplitude_deg=4.,happy_body_excursion_deg=6.)
        d.step(m,0.);values=[]
        for n in range(1,301):
            d.step(m,n*.05)
            if n>40:values.append(b.reg[3][42]-c.normal[3])
        self.assertGreater(max(values)*360/4096,5.9)
        self.assertLess(min(values)*360/4096,-5.9)
        self.assertLessEqual(max(abs(v) for v in values),69)
        self.assertEqual(d.rhythm.amplitude_ticks,4*4096/360)
