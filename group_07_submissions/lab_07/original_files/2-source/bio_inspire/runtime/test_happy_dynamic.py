import unittest
from unittest.mock import patch
from small_happy_trial import SmallHappyTrial
from three_state_behavior import _small_happy_speed
import test_happy_taught_center as fixture
import test_manual_transport as transport

class Tests(unittest.TestCase):
    def test_quick_three_point_eight_cycle_and_two_second_entry_keep_existing_limits(self):
        from taught_happy import validate
        config=dict(happy_taught_center_trial=True,happy_taught_fast_trial=True,happy_taught_fast_period_s=3.8,
                    happy_dynamic_trial=True,small_happy_expanded_trial=True,automatic_fsm_enabled=True,native_posture_compensation=True)
        validate(config)
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=3.8,dynamic_trial=True)
        self.assertEqual(d.entry_seconds,2.);self.assertAlmostEqual(d.phase_divisor,1.)
        m,b=fixture.Tests().motor();m.happy_dynamic_trial=True;m.happy_dance_only=True
        d.rhythm.set_ahm_phi(.13)
        for n in range(601):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            for f in d.limiters.values():
                self.assertTrue(f.limits.low<=f.position<=f.limits.high)
                self.assertLessEqual(abs(f.velocity),800.+1e-7)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertAlmostEqual(d.limiters[4].limits.acceleration,12*8.7*4096/360)
        config['happy_dynamic_trial']=False
        with self.assertRaises(ValueError):validate(config)
    def test_scoped_ram_writes_and_deferred_lowering_in_real_bus_guard(self):
        from acceleration_restore import AccelerationRestore
        b,p=transport.Tests().make_bus();p.reg[41]=b'\1'
        for sid,value in ((2,8),(3,8),(4,12),(5,6)):
            with self.assertRaises(ValueError):b.write(sid,41,bytes((value,)))
        b.happy_dynamic_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid,value in ((2,8),(3,8),(4,12),(5,6)):b.write(sid,41,bytes((value,)))
            for sid,value in ((1,8),(2,12),(4,254),(5,12)):
                with self.assertRaises(ValueError):b.write(sid,41,bytes((value,)))
            b.acceleration_restore=AccelerationRestore();b.acceleration_restore.protect(4,12)
            before=len(p.writes);b.write(4,41,b'\1');self.assertEqual(len(p.writes),before)
            rows=[dict(id=4,position_raw=2000,goal_raw=1997,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1)]
            for _ in range(3):b.acceleration_restore.service(rows,b.write)
            self.assertEqual(p.reg[41],b'\1')
    def test_recipe_keeps_angles_and_reduces_command_lag_against_old5s(self):
        errors=[]
        for dynamic in (False,True):
            m,b=fixture.Tests().motor();m.happy_taught_fast_trial=True;m.happy_dynamic_trial=dynamic
            _small_happy_speed(m,True)
            self.assertEqual([b.reg[i][41] for i in (2,3,4,5)],[8,8,12,6] if dynamic else [3,3,6,3])
            d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=5.,dynamic_trial=dynamic)
            d.rhythm.set_ahm_phi(.13);err=[]
            for n in range(1001):
                now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
                status=d.rhythm.status()
                if now>10.:err.append(abs(status['requested_targets_float'][4]-status['command_targets_float'][4]))
                for i,(lo,hi) in {2:(2603,2705),3:(3044,3146),4:(1636,2383)}.items():
                    if now>10.:self.assertTrue(lo<=status['command_targets_raw'][i]<=hi)
                b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
            errors.append(sum(err)/len(err))
            self.assertEqual(d.entry_seconds,3. if dynamic else 4.)
        self.assertLess(errors[1],errors[0]*.6)
    def test_dynamic_guard_rejects_other_recipes(self):
        from taught_happy import validate
        for kwargs in ({},{'fast_trial':True,'taught_center':True,'expanded':True}):
            with self.assertRaises(ValueError):SmallHappyTrial(dynamic_trial=True,**kwargs)
        with self.assertRaises(ValueError):validate(dict(happy_dynamic_trial=True))

    def test_four_point_five_seconds_changes_only_happy_phase_with_existing_caps(self):
        from taught_happy import validate
        config=dict(happy_taught_center_trial=True,happy_taught_fast_trial=True,happy_taught_fast_period_s=4.5,
                    happy_dynamic_trial=True,small_happy_expanded_trial=True,automatic_fsm_enabled=True,native_posture_compensation=True)
        validate(config)
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=4.5,dynamic_trial=True)
        self.assertAlmostEqual(3.8*d.phase_divisor,4.5);self.assertEqual(d.entry_seconds,3.)
        m,b=fixture.Tests().motor();m.happy_dynamic_trial=True;m.happy_dance_only=True;d.rhythm.set_ahm_phi(.13)
        for n in range(601):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            for f in d.limiters.values():
                self.assertTrue(f.limits.low<=f.position<=f.limits.high)
                self.assertLessEqual(abs(f.velocity),f.limits.speed+1e-7)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        self.assertAlmostEqual(d.limiters[4].limits.acceleration,12*8.7*4096/360)
        config['happy_dynamic_trial']=False
        with self.assertRaises(ValueError):validate(config)

    def test_wide_caps_explicit_profile_and_bounded_full_motion(self):
        from taught_happy import validate
        cfg=dict(happy_taught_center_trial=True,happy_taught_fast_trial=True,happy_taught_fast_period_s=3.8,
                 happy_dynamic_trial=True,happy_wide_caps_trial=True,fast_awake_trial=True,happy_dance_only=True,
                 small_happy_speed_raw=1000,small_happy_expanded_trial=True,automatic_fsm_enabled=True,native_posture_compensation=True)
        validate(cfg)
        for key in ('happy_dynamic_trial','fast_awake_trial','happy_dance_only'):
            with self.assertRaises(ValueError):validate({**cfg,key:False})
        with self.assertRaises(ValueError):validate({**cfg,'happy_taught_fast_period_s':2.})
        m,b=fixture.Tests().motor();m.happy_dynamic_trial=True;m.happy_wide_caps_trial=True;m.happy_dance_only=True
        d=SmallHappyTrial(expanded=True,taught_center=True,fast_trial=True,fast_period_s=3.8,dynamic_trial=True,wide_caps_trial=True)
        d.rhythm.set_ahm_phi(.13)
        for n in range(401):
            now=n*.05;m.latest_result['observation']['captured_s']=now;d.step(m,now)
            for i,acc in ((1,8),(2,16),(3,16),(4,24)):
                self.assertEqual(d.limiters[i].limits.speed,1200.)
                self.assertAlmostEqual(d.limiters[i].limits.acceleration,acc*8.7*4096/360)
                self.assertLessEqual(abs(d.limiters[i].velocity),1200.+1e-7)
                self.assertTrue(d.limiters[i].limits.low<=d.limiters[i].position<=d.limiters[i].limits.high)
            b.pos={i:b.reg[i][42] for i in b.pos};m.controller.last_rows=b.snapshot()
        m.happy_taught_fast_trial=True;m.happy_speed_raw=1000;_small_happy_speed(m,True)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[8,16,16,24,6])
        self.assertEqual([b.reg[i][46] for i in range(1,6)],[1000]*5)

    def test_wide_caps_ram_guard_is_exact_and_scoped(self):
        b,p=transport.Tests().make_bus();p.reg[41]=b'\1'
        for sid,acc in ((1,8),(2,16),(3,16),(4,24)):
            with self.assertRaises(ValueError):b.write(sid,41,bytes((acc,)))
        b.happy_wide_caps_trial=True
        with patch('normal_gaze_motor.receive_write_ack'):
            for sid,acc in ((1,8),(2,16),(3,16),(4,24),(5,6)):b.write(sid,41,bytes((acc,)))
            for sid,acc in ((1,16),(2,24),(4,60),(5,24)):
                with self.assertRaises(ValueError):b.write(sid,41,bytes((acc,)))
        b.happy_wide_caps_trial=False
        with self.assertRaises(ValueError):b.write(4,41,bytes((24,)))

    def test_wide_caps_real_bus_restores_awake_only_after_arrival(self):
        from acceleration_restore import AccelerationRestore
        b,p=transport.Tests().make_bus();p.reg[41]=b'\1'
        g=b.acceleration_restore=AccelerationRestore()
        for sid,high,target in ((1,8,3),(2,16,8),(3,16,8),(4,24,12)):
            g.pin(sid,high);g.unpin(sid,target)
        rows=[dict(id=i,position_raw=2000,goal_raw=2000,speed_raw=0,moving_raw=0,status_raw=0,mode=0,torque_raw=1) for i in range(1,5)]
        with patch('normal_gaze_motor.receive_write_ack'):
            g.service(rows,b.write);g.service(rows,b.write)
            self.assertTrue(g.pending)
            g.service(rows,b.write)
        self.assertFalse(g.pending)
        with self.assertRaises(ValueError):b.write(4,41,bytes((12,)))

    def test_button_route_cannot_lower_wide_braking_floor(self):
        from test_button_look import Tests as ButtonFixture
        from button_look import begin_button_look
        from acceleration_restore import AccelerationRestore
        b,c=ButtonFixture().controller();c.motion_speed=600;c.button_look_dynamic_trial=True
        g=b.acceleration_restore=AccelerationRestore();write=b.write
        def guarded(i,a,v):
            if a==41 and g.defer(i,int.from_bytes(v,'little')):return
            write(i,a,v)
        b.write=guarded
        for i,high,target in ((1,8,3),(2,16,8),(3,16,8),(4,24,12),(5,6,6)):
            b.reg[i][41]=high;g.pin(i,high);g.unpin(i,target)
        begin_button_look(c)
        self.assertEqual([b.reg[i][41] for i in range(1,6)],[8,16,16,24,6])
        self.assertEqual(g.floor[4],24)

    def test_coordinated_normal_return_has_one_progress_for_body_and_head(self):
        from test_button_look import Tests as ButtonFixture
        from pose_route import PoseRoute
        b,c=ButtonFixture().controller();c.motion_speed=600;c.control_now_s=20.
        c.control_clock=lambda:c.control_now_s
        start={1:c.normal[1]+60,2:2654,3:3095,4:2300,5:2164}
        b.pos=dict(start)
        for i,q in start.items():b.reg[i][42]=q
        c.behavior_joint_windows={i:(min(start[i],c.normal[i])-34,max(start[i],c.normal[i])+34) for i in start}
        c.behavior_pitch_window=(2070,2764)
        route=PoseRoute(c,c.normal,c.normal,normal_only=True,coordinated_return=True)
        self.assertEqual({i:b.reg[i][42] for i in start},start)
        last=0.
        for n in range(1,101):
            c.control_now_s=20+n*.05
            route.step(b.snapshot())
            progress=[]
            for i in (2,3,5):
                q=b.reg[i][42];d=c.normal[i]-start[i]
                progress.append((q-start[i])/d)
                expected=start[i]+d*route.return_progress
                self.assertAlmostEqual(q,expected,delta=.51)
            self.assertLess(max(progress)-min(progress),.01)
            self.assertGreaterEqual(route.return_progress,last);last=route.return_progress
            b.pos={i:b.reg[i][42] for i in start}
        self.assertEqual(route.phase,'complete')
        self.assertEqual({i:b.reg[i][42] for i in start},c.normal)
        # Route cancellation cannot emit a late head command.
        route.cancel();b.calls.clear();route.step(b.snapshot());self.assertEqual(b.calls,[])

    def test_coordinated_return_cannot_be_enabled_for_other_routes(self):
        from test_button_look import Tests as ButtonFixture
        from pose_route import PoseRoute
        b,c=ButtonFixture().controller()
        with self.assertRaises(ValueError):PoseRoute(c,c.normal,coordinated_return=True)

    def test_normal_handler_selects_coordinated_return_for_all_reviewed_states(self):
        from three_state_behavior import handle_state_key
        m,b=fixture.Tests().motor();c=m.controller
        m.happy_wide_caps_trial=True;c.motion_speed=600;c.control_now_s=20.
        handle_state_key(m,ord('n'))
        self.assertTrue(c.pose_route.coordinated_return)
        route=c.pose_route;b.calls.clear();c.state='STOPPED';route.step(b.snapshot())
        self.assertEqual(b.calls,[])
        c.state='READY';c.pose_route.phase='complete';m.behavior_trial='normal'
        handle_state_key(m,ord('n'))
        self.assertTrue(c.pose_route.coordinated_return)

    def test_direct_dynamic_button_out_and_back_share_head_body_progress(self):
        from test_button_look import Tests as ButtonFixture
        from button_look import begin_button_look
        b,c=ButtonFixture().controller();c.motion_speed=600;c.button_look_dynamic_trial=True
        c.coordinated_pose_transitions=True;c.control_now_s=20.;c.control_clock=lambda:c.control_now_s
        begin_button_look(c);r=c.pose_route
        self.assertTrue(r.coordinated_return)
        seen=set()
        for n in range(1,151):
            c.control_now_s=20+n*.05
            if r.phase not in ('look','return'):break
            phase=r.phase;r.step(b.snapshot())
            if r.phase==phase:
                for i in (2,3,5):
                    expected=r.return_start[i]+(r.motion_target[i]-r.return_start[i])*r.return_progress
                    self.assertAlmostEqual(b.reg[i][42],expected,delta=.51)
                seen.add(phase)
            b.pos={i:b.reg[i][42] for i in b.pos}
        self.assertEqual(seen,{'look','return'})

    def test_each_state_returns_to_normal_through_the_same_coordinator(self):
        from three_state_behavior import handle_state_key
        for source in ('normal','interested','happy','angry','afraid','sleepy'):
            with self.subTest(source=source):
                m,b=fixture.Tests().motor();c=m.controller
                c.coordinated_pose_transitions=True;c.motion_speed=600;c.control_now_s=20.
                m.behavior_trial=source
                handle_state_key(m,ord('n'))
                self.assertTrue(c.pose_route.coordinated_return)
                self.assertEqual(m.behavior_trial,'normal_transition')
