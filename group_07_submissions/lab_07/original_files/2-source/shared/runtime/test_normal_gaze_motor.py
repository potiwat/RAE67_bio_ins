import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normal_gaze_motor import NormalGaze

NORMAL={1:2019,2:2837,3:2746,4:1997,5:2696}
ORIGIN={1:2022,2:3208,3:3236,4:1997,5:2412}


class Bus:
    def __init__(self):
        self.pos=dict(ORIGIN);self.torque={i:0 for i in NORMAL};self.calls=[]
        self.reg={i:{18:12,33:0,40:0,41:0,42:0,46:0,64:0,65:0} for i in NORMAL}
    def snapshot(self):
        return [dict(id=i,position_raw=self.pos[i],torque_raw=self.torque[i],
                     status_raw=self.reg[i][65],mode=0,speed_raw=0,moving_raw=0) for i in NORMAL]
    def read(self,i,a,n):return self.reg[i][a].to_bytes(n,'little')
    def write(self,i,a,data):
        v=int.from_bytes(data,'little');self.calls.append((i,a,v));self.reg[i][a]=v
        if a==40:self.torque[i]=v


class StartupTests(unittest.TestCase):
    def test_sleepy_yaw_tracking_leaves_head_droop_speed_untouched(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=400,tracking_acceleration=3,yaw_range_deg=30,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,pitch_up_deg=30,motion_speed=400)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.reg[5][46]=25;b.calls.clear();s.configure_tracking(pitch=False)
        self.assertEqual(b.reg[5][46],25)
        self.assertFalse(any(i==5 for i,a,v in b.calls))

    def test_all_joint_speed400_and_asymmetric_pitch30_share_one_window(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=400,tracking_acceleration=3,yaw_range_deg=30,command_margin_ticks=13,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,pitch_up_deg=30,motion_speed=400)
        self.assertEqual(s.pitch_window,(2355,2764))
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        self.assertTrue(all(b.reg[i][46]==400 for i in NORMAL))
        s.probe_pitch('negative');self.assertEqual(b.reg[5][42],2355)
        s.probe_pitch(True);self.assertEqual(b.reg[5][42],2764)
        s.configure_tracking();self.assertTrue(all(b.reg[i][46]==400 for i in NORMAL))

    def test_reviewed_yaw30_speed400_is_scoped_to_tracking_id1(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=400,tracking_acceleration=3,yaw_range_deg=30,command_margin_ticks=13,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=200)
        self.assertEqual(s.yaw_window,(1678,2360));self.assertEqual(s.pitch_window,(2628,2764))
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.probe(True);self.assertEqual(b.reg[1][42],2347)
        s.probe('negative');self.assertEqual(b.reg[1][42],1691)
        s.configure_tracking()
        self.assertEqual(b.reg[1][46],400)
        self.assertTrue(all(b.reg[i][46]==200 for i in (2,3,4,5)))

    def test_reviewed_yaw20_profile_keeps_command_margin_and_other_joint_ranges(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=200,tracking_acceleration=3,yaw_range_deg=20,command_margin_ticks=13,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=200)
        self.assertEqual(s.yaw_window,(1791,2247));self.assertEqual(s.pitch_window,(2628,2764))
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.probe(True);self.assertEqual(b.reg[1][42],2234)
        s.probe('negative');self.assertEqual(b.reg[1][42],1804)

    def test_stationary_loaded_emotion_hold_uses_current_feedback_window(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,normal_tolerances={2:34,3:34,5:34})
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.behavior_joint_windows={2:(2689,2781)};s.behavior_joint_allowances={2:0}
        b.reg[2][42]=2735;b.pos[2]=2755;b.calls.clear()
        s.hold('supported stop',all_axes=True)
        self.assertEqual(b.reg[2][42],2735)
        self.assertFalse(any(i==2 and a==42 for i,a,v in b.calls))

    def test_approved_base_speed200_reaches_all_joint_startup_and_tracking(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=200,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=200)
        s.start(0)
        self.assertTrue(all(b.reg[i][46]==200 for i in NORMAL))
        b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.configure_tracking()
        self.assertEqual(b.reg[1][46],200);self.assertEqual(b.reg[5][46],200)

    def test_interested_pitch_range_is_scoped_and_does_not_change_normal_window(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.interest_pitch_window=(NORMAL[5]-205,NORMAL[5]+68)
        self.assertTrue(s.goal_pitch(NORMAL[5]-180))
        self.assertEqual(s.pitch_window,(NORMAL[5]-68,NORMAL[5]+68))
        self.assertEqual(s.feedback_window(5),(NORMAL[5]-211,NORMAL[5]+74))
        s.interest_pitch_window=None
        with self.assertRaises(ValueError):s.goal_pitch(NORMAL[5]-180)

    def test_reviewed_id3_normal_tolerance_changes_readiness_not_motion_bounds(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,normal_tolerances={3:34})
        s.start(0);bounds=dict(s.windows);b.pos=dict(NORMAL);b.pos[3]+=24
        for t in (1,2,3):s.tick(t)
        self.assertEqual(s.state,'READY');self.assertEqual(s.windows,bounds)
        b.calls.clear();s.hold('operator stop',all_axes=True)
        self.assertFalse(any(i==3 and a==42 for i,a,v in b.calls))
        self.assertEqual(b.reg[3][42],NORMAL[3])
        default=NormalGaze(Bus(),ORIGIN,NORMAL);default.start(0)
        default.bus.pos=dict(NORMAL);default.bus.pos[3]+=24
        for t in (1,2,3):default.tick(t)
        self.assertEqual(default.state,'NORMAL_STARTUP')
        with self.assertRaises(ValueError):NormalGaze(Bus(),ORIGIN,NORMAL,normal_tolerances={2:34})
        with self.assertRaises(ValueError):NormalGaze(Bus(),ORIGIN,NORMAL,normal_tolerances={3:100})

    def test_all_joint_speed_trial_preserves_acceleration_goals_and_bounds(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_tuning=True,tracking_speed=100,tracking_acceleration=3,
                            yaw_range_deg=10,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6,motion_speed=100)
        s.start(0)
        for i in NORMAL:
            self.assertEqual(b.reg[i][46],100);self.assertEqual(b.reg[i][41],1)
            self.assertEqual(b.reg[i][42],NORMAL[i])
        b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.configure_tracking()
        self.assertEqual(b.calls,[(1,46,100),(1,41,3),(5,46,100),(5,41,1)])
        b.calls.clear();s.probe_pitch(True)
        self.assertEqual(b.calls,[(5,46,100),(5,41,1),(5,42,2764)])
        self.assertFalse(any(a==21 for i,a,v in b.calls))
        b.pos[5]=2771;s.tick(4);self.assertEqual(s.state,'FAULT')

    def test_nonbase_raw100_requires_explicit_speed_trial_and_acceleration_stays_one(self):
        from normal_gaze_motor import speed_write_allowed
        self.assertFalse(speed_write_allowed(2,46,100))
        self.assertTrue(speed_write_allowed(2,46,100,motion_speed=100))
        self.assertFalse(speed_write_allowed(2,46,101,motion_speed=100))
        self.assertFalse(speed_write_allowed(2,41,3,motion_speed=100))
        self.assertTrue(speed_write_allowed(2,41,1,motion_speed=100))

    def test_loaded_joint_inner_probe_does_not_expand_feedback_guard(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True,limb_range_deg=6,loaded_probe_deg=3)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        for sid in (2,3):
            for direction in (-1,1):
                b.calls.clear();s.probe_joint(sid,direction)
                self.assertEqual(b.calls,[(sid,46,1),(sid,41,1),(sid,42,NORMAL[sid]+direction*34)])
            self.assertEqual(s.joint_windows[sid],(NORMAL[sid]-68,NORMAL[sid]+68))
        b.calls.clear();s.probe_joint(4,1)
        self.assertEqual(b.reg[4][42],NORMAL[4]+68)
        b.pos[2]=NORMAL[2]+75;s.tick(4);self.assertEqual(s.state,'FAULT')

    def test_manual_limb_six_degrees_keeps_pid_and_other_joint_goals_unchanged(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True,limb_range_deg=6)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        for sid in (2,3,4):
            for direction in (-1,1):
                b.calls.clear();s.probe_joint(sid,direction)
                self.assertEqual(b.calls,[(sid,46,1),(sid,41,1),(sid,42,NORMAL[sid]+direction*68)])
        self.assertEqual(s.joint_windows[1],(NORMAL[1]-34,NORMAL[1]+34))
        b.pos[3]=NORMAL[3]+75;s.tick(4);self.assertEqual(s.state,'FAULT')

    def test_manual_connect_hold_does_not_send_normal_or_rebase_warm_loaded_goals(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);s.start(0,hold_only=True)
        self.assertEqual(s.state,'STOPPED')
        self.assertTrue(all(b.reg[i][42]==ORIGIN[i] for i in NORMAL))
        warm=Bus();warm.pos=dict(NORMAL);warm.pos[2]+=15
        for i in NORMAL:warm.torque[i]=1;warm.reg[i][42]=NORMAL[i];warm.reg[i][46]=1;warm.reg[i][41]=1
        w=NormalGaze(warm,warm.pos,NORMAL,manual_joints=True);w.start(0,hold_only=True)
        self.assertFalse(any(a==42 for i,a,v in warm.calls));self.assertEqual(w.state,'STOPPED')
    def test_manual_base_probe_uses_previously_tested_three_degrees(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.probe_joint(1,1)
        self.assertEqual(b.calls,[(1,46,1),(1,41,1),(1,42,2053)])

    def test_paused_manual_startup_keeps_feedback_live_and_resumes_only_explicitly(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);s.start(0)
        s.state='STOPPED';self.assertTrue(s.hold('pause',all_axes=True))
        self.assertEqual(s.state,'STOPPED')
        s.tick(1);self.assertEqual(len(s.last_rows),5);self.assertEqual(s.state,'STOPPED')
        self.assertFalse(s.probe_joint(5,1))
        b.calls.clear();s.resume_normal(2)
        self.assertEqual(s.state,'NORMAL_STARTUP');self.assertEqual(b.reg[5][42],NORMAL[5])

    def test_manual_hold_stops_the_selected_moving_joint(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.active_joint_id=3;b.pos[3]+=12;b.reg[3][42]=NORMAL[3]+34
        original_snapshot=b.snapshot
        def moving_snapshot():
            rows=original_snapshot();rows[2]['speed_raw']=1;return rows
        b.snapshot=moving_snapshot;b.calls.clear();s.hold('pause selected')
        self.assertEqual(b.reg[3][42],b.pos[3])
        self.assertFalse(any(i in (2,4) for i,a,v in b.calls))

    def test_manual_joint_goals_are_single_axis_and_bounded_after_normal(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,manual_joints=True)
        self.assertFalse(s.probe_joint(2,1));s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        for sid,ticks in [(2,34),(3,34),(4,34),(5,68)]:
            b.calls.clear();self.assertTrue(s.probe_joint(sid,1))
            self.assertEqual(b.calls,[(sid,46,1),(sid,41,1),(sid,42,NORMAL[sid]+ticks)])
            b.pos[sid]=NORMAL[sid]+ticks;s.tick(4+sid)
            self.assertNotEqual(s.state,'FAULT')
        with self.assertRaises(ValueError):s.probe_joint(6,1)
        with self.assertRaises(ValueError):s.probe_joint(2,2)

    def test_six_degree_pitch_probe_and_head_only_configuration_keep_base_unchanged(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,pitch_probe=True,pitch_tracking=True,pitch_range_deg=6)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.configure_tracking(yaw=False)
        self.assertEqual(b.calls,[(5,46,1),(5,41,1)])
        s.probe_pitch(True);self.assertEqual(b.reg[5][42],2764)
        s.probe_pitch('negative');self.assertEqual(b.reg[5][42],2628)
        with self.assertRaises(ValueError):s.goal_pitch(2765)

    def test_pitch_follow_requires_ready_obeys_bounds_and_does_not_move_arm(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,pitch_probe=True,pitch_tracking=True)
        self.assertFalse(s.goal_pitch(2700));s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.configure_tracking()
        self.assertEqual(b.calls,[(1,46,1),(1,41,1),(5,46,1),(5,41,1)])
        b.calls.clear();self.assertTrue(s.goal_pitch(2700));self.assertEqual(b.calls,[(5,42,2700)])
        with self.assertRaises(ValueError):s.goal_pitch(2731)
        with self.assertRaises(ValueError):s.goal_pitch(2661)
        self.assertFalse(any(i in (2,3,4) for i,a,v in b.calls))
    def test_pitch_follow_cannot_enable_without_reviewed_probe(self):
        with self.assertRaises(ValueError):NormalGaze(Bus(),ORIGIN,NORMAL,pitch_tracking=True)

    def test_pitch_probe_waits_for_ready_and_changes_only_id5(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,pitch_probe=True)
        self.assertFalse(s.probe_pitch(True));self.assertEqual(b.calls,[])
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();self.assertTrue(s.probe_pitch(True))
        self.assertEqual(b.calls,[(5,46,1),(5,41,1),(5,42,2730)])
        b.pos[5]=2730;s.tick(4);self.assertEqual(s.state,'READY')
        self.assertTrue(s.probe_pitch(False));self.assertEqual(b.reg[5][42],2696)
        self.assertTrue(s.probe_pitch('negative'));self.assertEqual(b.reg[5][42],2662)
        self.assertTrue(s.probe_pitch(False));self.assertEqual(b.reg[5][42],2696)
        b.pos[5]=2737;s.tick(5);self.assertEqual(s.state,'FAULT')

    def test_pitch_probe_requires_explicit_opt_in(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();self.assertFalse(s.probe_pitch(True));self.assertEqual(b.calls,[])

    def test_repeated_stop_preserves_stationary_loaded_joint_goals(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0)
        b.pos=dict(NORMAL);b.pos[2]+=15;b.pos[3]+=15
        for t in (1,2,3):s.tick(t)
        self.assertEqual(s.state,'READY');b.calls.clear()
        for _ in range(3):self.assertTrue(s.hold('operator stop',all_axes=True))
        self.assertEqual(b.reg[2][42],NORMAL[2]);self.assertEqual(b.reg[3][42],NORMAL[3])
        self.assertFalse(any(i in (2,3) for i,a,v in b.calls))

    def test_manual_eight_keeps_outer_fault_limits_and_insets_probe_targets(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,tracking_speed=8,tracking_acceleration=3,
                            yaw_range_deg=10,manual_tuning=True,command_margin_ticks=13)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        self.assertEqual(s.yaw_window,(1905,2133))
        s.probe(True);self.assertEqual(b.reg[1][42],2120)
        s.probe('negative');self.assertEqual(b.reg[1][42],1918)

    def test_faster_base_keeps_ten_degree_window_and_same_acceleration(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,tracking_speed=4,tracking_acceleration=3,yaw_range_deg=10)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.configure_tracking()
        self.assertEqual(b.calls,[(1,46,4),(1,41,3)])
        self.assertEqual(s.yaw_window,(1905,2133))
        with self.assertRaises(ValueError):s.goal_yaw(2134)

    def test_fresh_hold_precedes_settings_and_enable(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0)
        for i in NORMAL:
            calls=[(a,v) for sid,a,v in b.calls if sid==i]
            self.assertEqual(calls[:4],[(42,ORIGIN[i]),(46,1),(41,1),(40,1)])
            self.assertEqual(calls[4],(42,NORMAL[i]))

    def test_bad_state_prevents_any_write(self):
        b=Bus();b.reg[3][65]=1
        with self.assertRaises(RuntimeError):NormalGaze(b,ORIGIN,NORMAL).start(0)
        self.assertEqual(b.calls,[])

    def test_changed_origin_refused_without_writes(self):
        b=Bus();b.pos[5]+=50
        with self.assertRaises(RuntimeError):NormalGaze(b,ORIGIN,NORMAL).start(0)
        self.assertEqual(b.calls,[])

    def test_follow_waits_for_normal_and_explicit_direction(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0)
        self.assertFalse(s.follow(.9,1))
        b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        self.assertEqual(s.state,'READY')
        with self.assertRaises(ValueError):s.set_direction(0)
        s.set_direction(-1)
        s.follow(1,4)
        self.assertEqual(b.reg[1][42],1985)
        self.assertTrue(all(b.reg[i][42]==NORMAL[i] for i in (2,3,4,5)))

    def test_stale_or_missing_face_holds_actual_without_releasing(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.set_direction(1);s.follow(1,4);b.pos[1]=2025
        s.hold('face lost')
        self.assertEqual(b.reg[1][42],2025)
        self.assertTrue(all(b.torque.values()))

    def test_fault_during_startup_holds_all_enabled_axes(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0);b.reg[2][65]=1
        s.tick(1)
        self.assertEqual(s.state,'FAULT')
        self.assertTrue(all(b.reg[i][42]==b.pos[i] for i in NORMAL))
        self.assertTrue(all(b.torque.values()))

    def test_failed_hold_latches_fault_and_refuses_future_motion(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.set_direction(1)
        def fail_hold(sid):raise TimeoutError('UART timeout')
        b.hold_actual=fail_hold
        s.hold('lost face')
        self.assertEqual(s.state,'FAULT')
        self.assertFalse(s.follow(1,4))

    def test_yaw_write_failure_holds_and_latches_fault(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL);s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.set_direction(1);write=b.write
        def fail_goal(i,a,data):
            if i==1 and a==42 and int.from_bytes(data,'little')!=NORMAL[1]:raise TimeoutError('readback')
            return write(i,a,data)
        b.write=fail_goal
        self.assertFalse(s.follow(1,4))
        self.assertEqual(s.state,'FAULT')

    def test_invalid_start_clock_never_arms(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL)
        with self.assertRaises(ValueError):s.start(float('nan'))
        self.assertEqual(b.calls,[])

    def test_verified_active_hold_resumes_without_rebasing_or_reenabling(self):
        b=Bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=ORIGIN[i];b.reg[i][46]=1;b.reg[i][41]=1
        s=NormalGaze(b,ORIGIN,NORMAL);s.start(0)
        self.assertEqual(b.calls,[(i,42,NORMAL[i]) for i in NORMAL])
        self.assertEqual(s.state,'NORMAL_STARTUP')

    def test_wrong_speed_in_active_hold_is_refused_without_writes(self):
        b=Bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=ORIGIN[i];b.reg[i][46]=1;b.reg[i][41]=1
        b.reg[2][46]=0
        with self.assertRaises(RuntimeError):NormalGaze(b,ORIGIN,NORMAL).start(0)
        self.assertEqual(b.calls,[])

    def test_ten_degree_tracking_limits_apply_only_to_base_after_normal_ready(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,tracking_speed=3,tracking_acceleration=3,yaw_range_deg=10)
        self.assertEqual(s.yaw_window,(1905,2133))
        with self.assertRaises(RuntimeError):s.configure_tracking()
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        b.calls.clear();s.configure_tracking()
        self.assertEqual(b.calls,[(1,46,3),(1,41,3)])

    def test_resume_from_previous_tracking_uses_slow_normal_limits_first(self):
        b=Bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=ORIGIN[i];b.reg[i][46]=1;b.reg[i][41]=1
        b.reg[1][46]=3;b.reg[1][41]=3
        s=NormalGaze(b,ORIGIN,NORMAL,tracking_speed=3,tracking_acceleration=3,yaw_range_deg=10)
        s.start(0)
        self.assertEqual(b.calls[:2],[(1,46,1),(1,41,1)])
        self.assertFalse(any(a==40 for i,a,v in b.calls))

    def test_probe_after_tracking_restores_slow_limits_before_moving(self):
        b=Bus();s=NormalGaze(b,ORIGIN,NORMAL,tracking_speed=3,tracking_acceleration=3,yaw_range_deg=10)
        s.start(0);b.pos=dict(NORMAL)
        for t in (1,2,3):s.tick(t)
        s.configure_tracking();b.calls.clear();s.probe(True)
        self.assertEqual(b.calls,[(1,46,1),(1,41,1),(1,42,2133)])


if __name__=='__main__':unittest.main()
