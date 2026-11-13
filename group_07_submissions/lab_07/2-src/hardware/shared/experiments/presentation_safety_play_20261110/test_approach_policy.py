import unittest
from types import SimpleNamespace
from bio_inspire.runtime import automatic_fsm as retained
import test_automatic_fsm as fixtures
from .approach_policy import policy_class,scan_service


class PolicyTests(fixtures.ScanApproachTests):
    """Run the retained arrival tests against the isolated policy as well."""
    def scan_motor(self):
        m, b, s = self.face_gate_motor()
        cls = policy_class(retained)
        m.automatic_fsm = cls(approach_requires_face=True,
                             approach_scan_arrival=True, sleep_after_s=100.)
        m.automatic_fsm.service(m, 20.)
        return m, b, s

    def test_cooldown_drops_scan_and_distance_events_but_button_still_works(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        self.found(m,s,21.);self.normal_again(m)
        self.found(m,s,51.4,serial=2)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        m.physical_button.poll.return_value=True;self.at(m,s,52.,distance_cm=40.)
        self.assertEqual(m.behavior_trial,'button_look')
        m.physical_button.poll.return_value=False;self.normal_again(m)
        self.found(m,s,80.8,serial=3)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.found(m,s,81.2,serial=4)
        self.assertEqual(m.automatic_fsm.fsm.state,'interested')

    def test_face_age_half_second_and_original_gate_untouched(self):
        for age, accepted in ((.49,True),(.5,True),(.51,False),(1.99,False)):
            m,b,s=self.scan_motor()
            m.latest_result=self.face_frame(20.1-age)
            self.at(m,s,20.1,distance_cm=40.)
            self.assertEqual(m.automatic_fsm.fsm.state=='interested',accepted)
        m=SimpleNamespace(latest_result=self.face_frame(19.))
        self.assertFalse(retained.current_selected_face(m,20.))

    def test_recovery_owner_keeps_cooldown_but_new_viewer_does_not(self):
        m,b,s=self.scan_motor();self.at(m,s,20.1,distance_cm=40.)
        self.found(m,s,21.)
        cls=type(m.automatic_fsm);self.normal_again(m)
        m.automatic_fsm=cls(approach_requires_face=True,approach_scan_arrival=True,sleep_after_s=100.)
        self.at(m,s,22.,distance_cm=110.)
        self.found(m,s,23.,serial=2)
        self.assertEqual(m.automatic_fsm.fsm.state,'normal')
        self.assertEqual(m.automatic_fsm.last_auto_approach_s,21.16)
        fresh=policy_class(retained)()
        self.assertIsNone(fresh.last_auto_approach_s)


class MissingFaceTests(unittest.TestCase):
    def test_confirmed_missing_two_seconds_not_one(self):
        from bio_inspire.runtime import yaw_face_scan
        import test_yaw_face_scan as f
        fixture=f.Tests();m,b=fixture.motor();service=scan_service(yaw_face_scan)
        for now in (20.,20.5,21.,21.99):
            self.assertFalse(service(m,fixture.frame(now,'LOST'),now))
        self.assertTrue(service(m,fixture.frame(22.,'LOST'),22.))
        self.assertTrue(m.yaw_scan_status['active'])

    def test_brief_reappearance_restarts_confirmed_missing_time(self):
        from bio_inspire.runtime import yaw_face_scan
        import test_yaw_face_scan as f
        fixture=f.Tests();m,b=fixture.motor();service=scan_service(yaw_face_scan)
        self.assertFalse(service(m,fixture.frame(20.,'LOST'),20.))
        self.assertFalse(service(m,fixture.frame(21.,'TRACKING','FOLLOW'),21.))
        self.assertFalse(service(m,fixture.frame(21.1,'LOST'),21.1))
        self.assertFalse(service(m,fixture.frame(23.09,'LOST'),23.09))
        self.assertTrue(service(m,fixture.frame(23.11,'LOST'),23.11))

    def test_original_scan_is_still_one_second_and_fault_preempts_trial(self):
        from bio_inspire.runtime import yaw_face_scan
        import test_yaw_face_scan as f
        fixture=f.Tests();m,b=fixture.motor()
        yaw_face_scan.service(m,fixture.frame(20.,'LOST'),20.)
        self.assertTrue(yaw_face_scan.service(m,fixture.frame(21.,'LOST'),21.))
        m,b=fixture.motor();m.urgent_stop.set();b.calls.clear()
        self.assertFalse(scan_service(yaw_face_scan)(m,fixture.frame(25.,'LOST'),25.))
        self.assertEqual(b.calls,[])


if __name__=='__main__':unittest.main()
