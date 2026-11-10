import unittest
from command_frame import JointIntent, FrameComposer, GuardedFrameWriter


class FakeBus:
    def __init__(self, fail_id=None):
        self.calls = []
        self.reg = {}
        self.fail_id = fail_id

    def write(self, sid, address, data):
        self.calls.append((sid, address, int.from_bytes(data, 'little')))
        if sid == self.fail_id:
            raise IOError('ACK lost: command may have arrived')
        self.reg[sid] = data

    def read(self, sid, address, size):
        return self.reg[sid]


class FrameTests(unittest.TestCase):
    def compose(self, intents=()):
        return FrameComposer().compose(7, {i: 2000 for i in range(1, 6)}, intents,
                                       {i: (1800, 2200) for i in range(1, 6)})

    def test_conflicting_equal_priority_intents_rejected(self):
        with self.assertRaises(ValueError):
            self.compose([JointIntent(1, 2010., 'gaze', 2, 'face1'),
                          JointIntent(1, 2020., 'dance', 2, 'cpg1')])

    def test_priority_is_explicit_and_unowned_joint_holds_previous_target(self):
        frame = self.compose([JointIntent(1, 2010.25, 'gaze', 3, 'face1'),
                              JointIntent(1, 2020., 'dance', 2, 'cpg1')])
        self.assertEqual(frame.joints[0].target_float_ticks, 2010.25)
        self.assertEqual(frame.joints[0].target_ticks, 2010)
        self.assertEqual(frame.joints[0].producer, 'gaze')
        self.assertTrue(all(j.producer == 'previous_command_hold' and j.target_ticks == 2000 for j in frame.joints[1:]))

    def test_all_bounds_validated_before_first_write(self):
        bus = FakeBus()
        with self.assertRaises(ValueError):
            frame = self.compose([JointIntent(5, 2200.1, 'gaze', 2, 'bad')])
            GuardedFrameWriter().commit(frame, bus, lambda: False)
        self.assertEqual(bus.calls, [])
        for value in (True, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.compose([JointIntent(2, value, 'gaze', 2, 'bad')])

    def test_stop_cancels_staged_frame(self):
        bus = FakeBus()
        writer = GuardedFrameWriter()
        report = writer.commit(self.compose(), bus, lambda: True)
        self.assertEqual(report.status, 'cancelled')
        self.assertTrue(report.requires_recovery)
        self.assertEqual(bus.calls, [])

    def test_stop_during_commit_reports_partial_without_releasing_torque(self):
        bus = FakeBus()
        report = GuardedFrameWriter().commit(self.compose(), bus, lambda: len(bus.calls) == 2)
        self.assertEqual(report.status, 'cancelled')
        self.assertEqual([entry.joint_id for entry in report.committed], [1, 2])
        self.assertTrue(report.requires_hold)
        self.assertTrue(all(address == 42 for _, address, _ in bus.calls))

    def test_ack_failure_requires_explicit_recovery(self):
        bus = FakeBus(fail_id=3)
        writer = GuardedFrameWriter(clock=lambda: 10.)
        report = writer.commit(self.compose(), bus, lambda: False)
        self.assertEqual(report.status, 'failed')
        self.assertEqual(report.uncertain_joint_id, 3)
        self.assertEqual([entry.joint_id for entry in report.committed], [1, 2])
        count = len(bus.calls)
        self.assertEqual(writer.commit(self.compose(), bus, lambda: False).status, 'recovery_required')
        self.assertEqual(len(bus.calls), count)
        self.assertRaises(ValueError, writer.recover, False)
        writer.recover(True)
        fresh = FrameComposer().compose(8, {i: 2000 for i in range(1, 6)}, [], {i: (1800, 2200) for i in range(1, 6)})
        bus.fail_id = None
        self.assertEqual(writer.commit(fresh, bus, lambda: False).status, 'committed')

    def test_readback_mismatch_and_repeated_tick_are_not_accepted(self):
        class BadReadback(FakeBus):
            def read(self, sid, address, size): return b'\0\0'
        report = GuardedFrameWriter().commit(self.compose(), BadReadback(), lambda: False)
        self.assertEqual(report.status, 'failed')
        writer, bus = GuardedFrameWriter(), FakeBus()
        self.assertEqual(writer.commit(self.compose(), bus, lambda: False).status, 'committed')
        self.assertEqual(writer.commit(self.compose(), bus, lambda: False).status, 'stale_frame')
        self.assertEqual(len(bus.calls), 5)


if __name__ == '__main__': unittest.main()
