import unittest
from startup_preflight import prepare_operator_start
from test_normal_gaze_motor import Bus,NORMAL

PIDS={'1':dict(p=8,i=0,d=16),'2':dict(p=32,i=0,d=16),'3':dict(p=20,i=0,d=22),
      '4':dict(p=5,i=0,d=0),'5':dict(p=7,i=0,d=3)}


class Tests(unittest.TestCase):
    def test_warm_start400_preserves_loaded_goals(self):
        b=self.bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=b.pos[i];b.reg[i][46]=200;b.reg[i][41]=1
        goals={i:b.reg[i][42] for i in NORMAL}
        prepare_operator_start(b,PIDS,motion_speed=400)
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},goals)
        self.assertTrue(all(b.reg[i][46]==400 for i in NORMAL))
        self.assertFalse(any(a in (40,42) for i,a,v in b.calls))

    def test_warm_start200_changes_speed_without_rebasing_loaded_goals(self):
        b=self.bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=b.pos[i];b.reg[i][46]=100;b.reg[i][41]=1
        goals={i:b.reg[i][42] for i in NORMAL}
        prepare_operator_start(b,PIDS,motion_speed=200)
        self.assertEqual({i:b.reg[i][42] for i in NORMAL},goals)
        self.assertTrue(all(b.reg[i][46]==200 for i in NORMAL))
        self.assertFalse(any(a in (40,42) for i,a,v in b.calls))

    def test_approved_loaded_joint_tolerances_allow_2_3_5_but_keep_1_4_at22(self):
        b=self.bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=b.pos[i];b.reg[i][46]=100;b.reg[i][41]=1
            p=PIDS[str(i)];b.reg[i][21]=int.from_bytes(bytes([p['p'],p['d'],p['i']]),'little')
        limits={1:22,2:34,3:34,4:22,5:34}
        for i in (2,3,5):b.reg[i][42]-=26
        self.assertEqual(prepare_operator_start(b,PIDS,limits),b.pos)
        b.reg[4][42]-=23
        with self.assertRaisesRegex(RuntimeError,'ID4'):prepare_operator_start(b,PIDS,limits)

    def test_approved_id3_hold_tolerance_is_shared_with_normal_readiness(self):
        b=self.bus()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=b.pos[i];b.reg[i][46]=100;b.reg[i][41]=1
            p=PIDS[str(i)];b.reg[i][21]=int.from_bytes(bytes([p['p'],p['d'],p['i']]),'little')
        b.reg[3][42]-=26
        limits={i:22 for i in NORMAL};limits[3]=34
        self.assertEqual(prepare_operator_start(b,PIDS,limits),b.pos)
        self.assertEqual(b.calls,[])
        b.reg[3][42]=b.pos[3]-35
        with self.assertRaisesRegex(RuntimeError,'ID3'):prepare_operator_start(b,PIDS,limits)
        self.assertEqual(b.calls,[])

    def bus(self):
        b=Bus();b.manual_tuning=False;b.tuning_id=1
        for i in NORMAL:b.reg[i][21]=int.from_bytes(bytes([32,32,0]),'little');b.reg[i][55]=1
        return b

    def test_cold_cycle_restores_only_approved_pid_and_returns_live_pose(self):
        b=self.bus();origin=prepare_operator_start(b,PIDS)
        self.assertEqual(origin,b.pos)
        self.assertTrue(all(a==21 for i,a,v in b.calls))
        for sid,p in PIDS.items():self.assertEqual(b.read(int(sid),21,3),bytes([p['p'],p['d'],p['i']]))
        self.assertFalse(b.manual_tuning);self.assertEqual(b.tuning_id,1)

    def test_warm_start_preserves_gains_and_never_releases_or_rebases_loaded_joints(self):
        b=self.bus();prepare_operator_start(b,PIDS);b.calls.clear()
        for i in NORMAL:
            b.torque[i]=1;b.reg[i][42]=b.pos[i];b.reg[i][46]=100;b.reg[i][41]=1
        self.assertEqual(prepare_operator_start(b,PIDS),b.pos);self.assertEqual(b.calls,[])
        b.reg[3][21]=int.from_bytes(bytes([32,32,0]),'little')
        self.assertEqual(prepare_operator_start(b,PIDS),b.pos)
        self.assertEqual(b.read(3,21,3),bytes([20,22,0]))
        self.assertTrue(all(a in (21,41,46) for i,a,v in b.calls))

    def test_supported_warm_pid_restore_blocks_distant_active_goal_before_writes(self):
        b=self.bus()
        for i in NORMAL:b.torque[i]=1;b.reg[i][42]=b.pos[i]
        b.reg[2][42]+=30
        with self.assertRaisesRegex(RuntimeError,'ID2 hold error'):prepare_operator_start(b,PIDS)
        self.assertEqual(b.calls,[])

    def test_mixed_torque_invalid_config_or_eeprom_lock_block_before_any_write(self):
        b=self.bus();b.torque[3]=1
        with self.assertRaises(RuntimeError):prepare_operator_start(b,PIDS)
        self.assertEqual(b.calls,[])
        b=self.bus();b.reg[4][55]=0
        with self.assertRaises(RuntimeError):prepare_operator_start(b,PIDS)
        self.assertEqual(b.calls,[])
        b=self.bus()
        with self.assertRaises(ValueError):prepare_operator_start(b,{k:v for k,v in PIDS.items() if k!='1'})
        self.assertEqual(b.calls,[])
