import unittest
from types import SimpleNamespace as NS
from .initial_settle import StandstillReads,wrap_preflight


def rows(speed=0):
    return [dict(id=i,mode=0,status_raw=0,torque_raw=1,goal_raw=2000,
                 internal_target_raw=2000,position_raw=2000,
                 speed_raw=speed if i==1 else 0,moving_raw=0)for i in range(1,6)]


class Tests(unittest.TestCase):
    def clock(self):
        c=NS(t=0.);return c,lambda:c.t,lambda dt:setattr(c,'t',c.t+dt)

    def test_recorded_single_tick_speed_waits_for_actual_zero_samples(self):
        c,now,wait=self.clock();samples=[rows(32818),rows(),rows(),rows()];calls=[]
        def read():calls.append(1);return samples.pop(0)
        r=StandstillReads(read,now,wait,lambda:False)()
        self.assertEqual(len(calls),4);self.assertTrue(all(x['speed_raw']==0 for x in r))

    def test_fault_travel_changed_goal_and_persistent_motion_cannot_pass(self):
        for fault in('status','travel','goal','motion'):
            c,now,wait=self.clock();n=[0]
            def read():
                n[0]+=1;r=rows(50 if fault=='motion'else 0)
                if n[0]>1:
                    if fault=='status':r[0]['status_raw']=1
                    if fault=='travel':r[0]['position_raw']+=3
                    if fault=='goal':r[0]['goal_raw']+=1
                return r
            with self.assertRaises(RuntimeError):StandstillReads(read,now,wait,lambda:False)()
            self.assertLessEqual(c.t,.251)

    def test_original_preflight_still_runs_and_snapshot_hook_restores(self):
        c,now,wait=self.clock();bus=NS(snapshot=lambda:rows());read=bus.snapshot;seen=[]
        def original(b,*a,**kw):
            seen.extend(b.snapshot());return {r['id']:r['position_raw']for r in seen}
        out=wrap_preflight(original,now,wait,lambda:False)(bus,{})
        self.assertEqual(out,{i:2000 for i in range(1,6)})
        self.assertIs(bus.snapshot,read);self.assertEqual(bus.initial_standstill_goals,out)

    def test_cold_torque_off_passes_original_checks_without_active_hold_marker(self):
        c,now,wait=self.clock();calls=[]
        def read():
            r=rows()
            for v in r:v['torque_raw']=0;v['internal_target_raw']=1900
            return r
        bus=NS(snapshot=read)
        def original(b):
            calls.append('original');actual=b.snapshot()
            self.assertTrue(all(v['torque_raw']==0 for v in actual))
            return 'cold path'
        self.assertEqual(wrap_preflight(original,now,wait,lambda:False)(bus),'cold path')
        self.assertEqual(calls,['original']);self.assertIs(bus.snapshot,read)
        self.assertFalse(hasattr(bus,'initial_standstill_goals'))

    def test_cancel_during_read_restores_hook_and_never_grants_start_marker(self):
        c,now,wait=self.clock();cancelled=[False]
        def read():cancelled[0]=True;return rows()
        bus=NS(snapshot=read)
        with self.assertRaisesRegex(RuntimeError,'cancelled after read'):
            wrap_preflight(lambda b:b.snapshot(),now,wait,lambda:cancelled[0])(bus)
        self.assertIs(bus.snapshot,read)
        self.assertFalse(hasattr(bus,'initial_standstill_goals'))

    def test_torque_change_or_mixed_torque_never_qualifies(self):
        for mixed in(False,True):
            c,now,wait=self.clock();n=[0]
            def read():
                n[0]+=1;r=rows()
                if mixed:r[0]['torque_raw']=0
                elif n[0]>1:
                    for v in r:v['torque_raw']=0
                return r
            with self.subTest(mixed=mixed),self.assertRaises(RuntimeError):
                StandstillReads(read,now,wait,lambda:False)()
