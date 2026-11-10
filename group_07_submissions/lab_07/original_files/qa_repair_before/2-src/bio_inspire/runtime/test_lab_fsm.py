import unittest
from lab_fsm import LabFSM,transition,STATES,PRIORITY

class Tests(unittest.TestCase):
    def event(self,kind,t):return dict(kind=kind,source_s=t,source_id='test_'+kind)
    def test_exact_group_transition_table(self):
        import importlib.util
        from importlib.machinery import SourceFileLoader
        from pathlib import Path
        p=Path(__file__).resolve().parents[2]/'references'/'bio_inspire'/'group07_student_policy.py.txt'
        loader=SourceFileLoader('group_policy_reference',str(p));spec=importlib.util.spec_from_loader(loader.name,loader);module=importlib.util.module_from_spec(spec);loader.exec_module(module)
        for state in STATES:
            for event in PRIORITY:self.assertEqual(transition(state,event),module.transition(state,event))
    def test_timeout_and_idle_use_lab_clocks(self):
        f=LabFSM(10.);f.step(11.,[self.event('button',11.)])
        self.assertEqual(f.state,'interested');f.step(12.99,[]);self.assertEqual(f.state,'interested')
        f.step(13.,[]);self.assertEqual(f.state,'normal')
        f.step(16.99,[]);self.assertEqual(f.state,'normal');f.step(17.,[]);self.assertEqual(f.state,'sleepy')
    def test_priority_and_afraid_guard(self):
        f=LabFSM(0.);f.step(1.,[self.event('touch',1.),self.event('near',1.),self.event('button',1.)])
        self.assertEqual(f.state,'afraid');self.assertEqual(list(f.events)[0]['kind'],'near')
        f.step(2.,[self.event('touch',2.)]);self.assertEqual(f.state,'afraid')
        f.step(3.,[self.event('clear',3.),self.event('touch',3.)]);self.assertEqual(f.state,'normal')
    def test_repeated_same_state_does_not_restart_timeout(self):
        f=LabFSM(0.);f.step(1.,[self.event('touch',1.)]);f.step(2.,[self.event('touch',2.)])
        self.assertEqual(f.entry,1.);f.step(3.,[]);self.assertEqual(f.state,'normal')
    def test_visible_face_is_not_activity(self):
        f=LabFSM(0.)
        for n in range(61):f.step(n*.1,[])
        self.assertEqual(f.state,'sleepy')

class EngagementClockTests(unittest.TestCase):
    def test_five_seconds_begin_only_after_entry_finishes_and_renew_on_input(self):
        f=LabFSM(0.,active_timeout_s=5.,motion_aware=True)
        f.step(1.,[dict(kind='button')],ready=False)
        f.step(10.,[],ready=False);self.assertEqual(f.state,'interested')
        f.step(11.,[],ready=True)
        f.step(15.9,[],ready=True);self.assertEqual(f.state,'interested')
        f.step(16.,[dict(kind='button')],ready=True)
        f.step(20.9,[],ready=True);self.assertEqual(f.state,'interested')
        f.step(21.,[],ready=True);self.assertEqual(f.state,'normal')
    def test_sleep_waits_for_normal_return_and_released_inputs(self):
        f=LabFSM(0.,active_timeout_s=5.,motion_aware=True)
        f.step(20.,[],ready=False);self.assertEqual(f.state,'normal')
        f.step(21.,[],ready=True,held=True)
        f.step(30.,[],ready=True,held=True);self.assertEqual(f.state,'normal')
        f.step(31.,[],ready=True)
        f.step(36.9,[],ready=True);self.assertEqual(f.state,'normal')
        f.step(37.,[],ready=True);self.assertEqual(f.state,'sleepy')

class ExtendedIdleTests(unittest.TestCase):
    def test_approved_ten_second_idle(self):
        f=LabFSM(0.,active_timeout_s=5.,motion_aware=True,sleep_after_s=10.)
        f.step(0.,[]);f.step(9.99,[]);self.assertEqual(f.state,'normal')
        f.step(10.,[]);self.assertEqual(f.state,'sleepy')
