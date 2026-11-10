"""Bounded gameplay liveness scenarios. Uses real owner loop and fake I/O."""
import unittest,random
from dataclasses import replace
from types import SimpleNamespace
from . import runtime_integration as runtime
from . import test_demo_acceptance as accepted
from physical_distance import distance_input_kind


class Tests(unittest.TestCase):
    def test_happy_button_return_uses_coordinated_awake_head_and_body(self):
        from unittest.mock import patch
        from pose_route import PoseRoute
        original=PoseRoute.__init__;returns=[]
        def capture(route,*args,**kwargs):
            original(route,*args,**kwargs)
            if route.post_steps:returns.append(dict(route.return_pose))
        frames=[replace(f,touch=3<=f.time_s<4,button=7<=f.time_s<7.3) for f in self.frames(25.)]
        with patch.object(PoseRoute,'__init__',capture):r=self.run_case(frames,duration=25.,face_lost=(0.,25.))
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue(returns)
        for pose in returns:
            self.assertEqual((pose[2],pose[3],pose[4]),(2837,2746,1997))
            self.assertTrue(2355<=pose[5]<=2764)
    def test_quiescent_tail_recovers_after_random_preemptions(self):
        for seed in range(81,93):
            rng=random.Random(seed)
            actions=[(2.+2*n,rng.choice(('button','touch','burst','near'))) for n in range(15)]
            frames=[]
            for f in self.frames(60.):
                t=f.time_s
                button=any(kind=='button' and start<=t<start+.25 for start,kind in actions)
                touch=any(kind=='touch' and start<=t<start+.6 or kind=='burst' and any(start+d<=t<start+d+.15 for d in (0.,.35,.7)) for start,kind in actions)
                near=any(kind=='near' and start<=t<start+1.1 for start,kind in actions)
                unknown=24<=t<26
                frames.append(replace(f,button=button,touch=touch,distance_kind='unreliable' if unknown else 'range',
                                      distance_m=None if unknown else .16 if near else 1.2))
            with self.subTest(seed=seed):
                r=self.run_case(frames,duration=60.,condition='C0' if seed%2 else 'C1',
                                face_lost=(0.,60.) if seed%2 else None,tof_stall=(19.8,20.1))
                self.assertNotIn('FAULT',r['controller_states'])
                tail=[v for v in r['trace'] if v['time_s']>=58.]
                self.assertTrue(tail)
                self.assertTrue(all(v['fsm']['state'] in ('normal','sleepy') for v in tail))
                self.assertTrue(all(v['behavior'] in ('normal','sleepy','sleepy_transition') for v in tail))

    def frames(self,duration=45.):return accepted.Tests().frames(duration)
    def run_case(self,frames,**kw):
        return accepted.Tests().run_case(frames,**kw)

    def test_fake_quality_frames_use_real_raw_status_contract(self):
        frame=replace(self.frames(1.)[0],distance_kind='unreliable',distance_m=None)
        clock=SimpleNamespace(t=0.,tof_stall=None,inside=lambda x:False,frame=lambda:frame,index=lambda:0)
        port=runtime.DistancePort(clock)
        self.assertEqual(distance_input_kind(port.latest(),0.),'unreliable')

    def test_sleepy_button_then_happy_burst_and_clear_do_not_stall(self):
        frames=[replace(f,button=14<=f.time_s<14.25,
                  touch=27<=f.time_s<28 or any(t<=f.time_s<t+.15 for t in (31.,31.4,31.8)),
                  distance_m=.16 if 37<=f.time_s<40 else 1.2) for f in self.frames(55.)]
        r=self.run_case(frames,duration=55.)
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue({'normal','sleepy','interested','happy','angry','afraid'}<=set(v['fsm']['state'] for v in r['trace']))
        self.assertTrue(any(v['time_s']>41 and v['fsm']['state']=='normal' for v in r['trace']))

    def test_no_face_interested_leaves_and_happy_keeps_dancing(self):
        frames=[replace(f,button=3<=f.time_s<3.3,touch=22<=f.time_s<23) for f in self.frames(45.)]
        r=self.run_case(frames,face_lost=(0.,45.))
        self.assertNotIn('FAULT',r['controller_states'])
        posed=[v for v in r['trace'] if v['behavior']=='interested' and v['route_phase']=='complete' and v['time_s']<17]
        self.assertTrue(posed,'No face must still complete the lean and neck gesture, not merely time out')
        neck_positions=[row['position_raw'] for v in posed for row in v['rows'] if row['id']==4]
        self.assertLess(min(neck_positions),1900,'Recorded Interested neck tilt must actually be reached')
        self.assertTrue(any(17<v['time_s']<22 and v['fsm']['state']=='normal' for v in r['trace']))
        dancing=[v for v in r['trace'] if v['behavior']=='happy' and 25<v['time_s']<29]
        self.assertTrue(dancing)
        self.assertTrue(all(v['rhythm'].get('small_happy')=='running' for v in dancing))

    def test_tof_pause_unknown_stream_recovers_and_later_touch_works(self):
        frames=[replace(f,touch=10<=f.time_s<11,distance_kind='unreliable' if 4<=f.time_s<9 else 'range',
                        distance_m=None if 4<=f.time_s<9 else 1.2) for f in self.frames(25.)]
        r=self.run_case(frames,duration=25.,tof_stall=(3.6,4.))
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertIn('WAIT_TOF',r['controller_states'])
        self.assertFalse(any(v['state']=='WAIT_TOF' and 6<v['time_s']<9 for v in r['trace']))
        self.assertTrue(any(12<v['time_s']<18 and v['behavior']=='happy' for v in r['trace']))

    def test_stop_then_operator_start_discards_old_presses(self):
        # The real viewer handles M by closing/recreating CameraMotor; M is
        # not an owner-loop command. Model two owners sequentially, never hot
        # inject M into the old stopped worker (which intentionally ignores it).
        frames=[replace(f,touch=3<=f.time_s<4,button=6<=f.time_s<6.3) for f in self.frames(8.)]
        r=self.run_case(frames,duration=8.,stop_s=5.)
        self.assertNotIn('FAULT',r['controller_states'])
        self.assertTrue(all(v['operator_stopped'] for v in r['trace'] if 5.2<v['time_s']<8))
        self.assertFalse(any(5.2<w['time_s']<8 for w in r['position_writes_after_stop']))
        pose={row['id']:row['position_raw'] for row in r['trace'][-1]['rows']}
        fresh=[replace(f,button=3<=f.time_s<3.3) for f in self.frames(20.)]
        restarted=self.run_case(fresh,duration=20.,initial_pose=pose,initial_torque=1)
        self.assertNotIn('FAULT',restarted['controller_states'])
        self.assertTrue(all(v['fsm']['state']=='normal' for v in restarted['trace'] if .2<v['time_s']<3))
        self.assertTrue(any(v['fsm']['state']=='interested' for v in restarted['trace'] if 3<v['time_s']<8))


if __name__=='__main__':unittest.main()
