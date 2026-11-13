"""Simulation-only contract tests; no UART device is opened."""
import unittest
from unittest.mock import patch

try:
    from .release_io import ReleaseIO
except ImportError:
    ReleaseIO = None


class Port:
    def __init__(self, bus):
        self.bus = bus

    def reset_input_buffer(self):
        pass

    def write(self, packet):
        b = self.bus
        assert packet[2] == b.sid and packet[4] == 3
        assert sum(packet[2:]) & 255 == 255
        address, data = packet[5], packet[6:-1]
        b.writes.append((address, bytes(data)))
        b.ram[address:address + len(data)] = data
        if address == 42:
            b.put(67, int.from_bytes(data, 'little'))
            b.put(56, int.from_bytes(data, 'little') + b.residual)
        if b.after_write:
            b.after_write(address)
        return len(packet)


class Bus:
    def __init__(self, sid=2, residual=20):
        self.sid, self.residual = sid, residual
        self.ram = bytearray(100)
        self.ram[40], self.ram[41], self.ram[62] = 1, 12, 70
        for a, v in ((42, 2000), (46, 321), (48, 1000),
                     (56, 2000 + residual), (67, 2000)):
            self.put(a, v)
        self.writes, self.after_write = [], None
        self.port = Port(self)

    def put(self, address, value):
        self.ram[address:address + 2] = value.to_bytes(2, 'little')

    def read(self, sid, address, count):
        assert sid == self.sid
        return bytes(self.ram[address:address + count])


class Tests(unittest.TestCase):
    def test_head_retry_eligibility_is_not_initial_source_or_restore_clearance(self):
        b,io=self.fixture(4);io.prepare();pins=(io.anchor_goal,io.anchor_q)
        b.put(56,1983);b.put(60,36);b.put(69,1)
        for k in range(4):
            self.t+=.05;r=io.read()[0]
            self.assertFalse(io.observe_still(r))
            result=io.observe_preprobe_still(r,retry=True)
        self.assertTrue(result);self.assertEqual((io.anchor_goal,io.anchor_q),pins)
        self.assertFalse(io.observe_preprobe_still(io.read()[0]))
        for q,current in ((1977,1),(1983,3)):
            b.put(56,q);b.put(69,current);self.t+=.05
            self.assertFalse(io.observe_preprobe_still(io.read()[0],retry=True))
    def setUp(self):
        self.t = 1.

    def fixture(self, sid=2, residual=None, window=(1950, 2050)):
        self.assertIsNotNone(ReleaseIO, 'generic bounded release I/O is missing')
        p = patch('shared.experiments.presentation_safety_play_20261110.release_io.receive_write_ack', return_value=None)
        p.start(); self.addCleanup(p.stop)
        b = Bus(sid, (20 if sid == 2 else 0) if residual is None else residual)
        return b, ReleaseIO(b, sid, window, lambda: False, lambda: self.t)

    def still(self, io):
        result = False
        for _ in range(4):
            self.t += .05
            result = io.observe_still(io.read()[0])
        self.assertTrue(result)

    def test_generic_io_is_available(self):
        self.assertIsNotNone(ReleaseIO, 'generic bounded release I/O is missing')

    def test_head_residual_does_not_shrink_reviewed_encoder_relative_probe(self):
        b, io = self.fixture(4, residual=11); io.prepare()
        self.assertEqual(io.encoder_travel_limit, 36)
        self.assertEqual(io.excursion, 43)
        b.residual = 0
        for goal in range(2001, 2044): io.command(goal)
        self.assertEqual(io.anchor_q, 2011)
        b.put(56, 2048)
        with self.assertRaises(RuntimeError): io.read()

    def test_preprobe_head_residual_does_not_grant_restore_authority(self):
        b, io = self.fixture(4, residual=6); io.prepare()
        for _ in range(4):
            self.t += .05
            ready = io.observe_preprobe_still(io.read()[0])
        self.assertTrue(ready)
        self.assertFalse(io._proof_ok())
        with self.assertRaises(RuntimeError): io.restore()
        self.assertEqual(io.goal, 2000)
        self.assertFalse(any(a == 42 for a, _ in b.writes))
        b.put(60, 32)
        self.t += .05
        self.assertFalse(io.observe_preprobe_still(io.read()[0]))

    def test_preprobe_requires_temporal_static_fresh_support(self):
        for fault in ('motion', 'reference', 'current', 'error', 'stale'):
            b, io = self.fixture(4, residual=6); io.prepare()
            if fault == 'motion': b.put(58, 1)
            if fault == 'reference': b.put(67, 2001)
            if fault == 'current': b.put(69, 3)
            if fault == 'error': b.put(56, 2013)
            for _ in range(4):
                self.t += .05
                row = io.read()[0]
                if fault == 'stale': self.t += .181
                self.assertFalse(io.observe_preprobe_still(row), fault)

    def test_prepare_preserves_loaded_source_and_profiles_restore_cap_last(self):
        for sid, cap, acc in ((1, 160, 3), (2, 400, 8), (4, 160, 3)):
            with self.subTest(sid=sid):
                b, io = self.fixture(sid)
                source = bytes(b.ram[33:71]); io.prepare()
                self.assertEqual(io.original, source)
                self.assertEqual(io.anchor_goal, 2000)
                self.assertEqual(io.anchor_q, 2020 if sid == 2 else 2000)
                self.assertEqual(b.writes, [(48, cap.to_bytes(2, 'little')), (46, b'X\x02'), (41, bytes((acc,)))])
                self.assertFalse(hasattr(io, 'hold'))
                self.still(io); io.restore()
                self.assertTrue(io.restored)
                self.assertEqual(b.writes[-3:], [(46, b'A\x01'), (41, b'\x0c'), (48, b'\xe8\x03')])
                self.assertEqual(bytes(b.ram[33:50]), source[:17])

    def test_one_sided_window_and_goal_anchor_never_ratchet(self):
        b, io = self.fixture(1, window=(2000, 2016)); io.prepare()
        with self.assertRaises(RuntimeError): io.command(2002)
        for goal in range(2001, 2017): io.command(goal)
        with self.assertRaises(RuntimeError): io.command(2017)
        self.assertEqual((io.anchor_goal, io.anchor_q), (2000, 2000))
        self.still(io); io.restore()
        self.assertEqual(io.goal, 2016)
        self.assertEqual(int.from_bytes(b.ram[42:44], 'little'), 2016)

    def test_id4_32_tick_bound_and_encoder_extra_margin(self):
        b, io = self.fixture(4); io.prepare()
        for goal in range(2001, 2033): io.command(goal)
        with self.assertRaises(RuntimeError): io.command(2033)
        b.put(56, 2036); io.read()
        b.put(56, 2037)
        with self.assertRaises(RuntimeError): io.read()

    def test_source_faults_refuse_without_writes(self):
        for address, value, width in ((33, 1, 1), (40, 0, 1), (65, 1, 1), (62, 59, 1), (48, 400, 2), (58, 1, 2), (66, 1, 1), (56, 2035, 2), (60, 300, 2), (69, 41, 2)):
            b, io = self.fixture()
            b.ram[address:address+width] = value.to_bytes(width, 'little')
            with self.subTest(address=address), self.assertRaises(RuntimeError): io.prepare()
            self.assertEqual(b.writes, [])

    def test_read_detects_native_block_window_reference_and_pinned_travel_changes(self):
        for address, value in ((41, 9), (44, 1), (48, 401), (42, 2017), (56, 2041), (67, 2017)):
            b, io = self.fixture(); io.prepare()
            if address in (41, 44): b.ram[address] = value
            else: b.put(address, value)
            with self.subTest(address=address), self.assertRaises(RuntimeError): io.read()

    def test_restore_requires_temporal_fresh_static_low_effort_proof(self):
        for fault in ('missing', 'stale', 'motion', 'reference', 'pwm', 'current', 'position', 'spoof'):
            b, io = self.fixture(1); io.prepare()
            if fault != 'missing': self.still(io)
            if fault == 'stale': self.t += .181
            if fault == 'motion': b.put(58, 1)
            if fault == 'reference': b.put(67, 2001)
            if fault == 'pwm': b.put(60, 32)
            if fault == 'current': b.put(69, 3)
            if fault == 'position': b.put(56, 2005)
            if fault == 'spoof':
                row = dict(io.read()[0]); row['target_speed_raw'] = 599
                self.assertFalse(io.observe_still(row))
            n = len(b.writes)
            with self.subTest(fault=fault), self.assertRaises(RuntimeError): io.restore()
            self.assertEqual(len(b.writes), n)

    def test_profile_restore_does_not_invalidate_proof_but_fresh_motion_blocks_cap_raise(self):
        b, io = self.fixture(4); io.prepare(); self.still(io)
        b.after_write = lambda a: b.put(58, 1) if a == 41 else None
        with self.assertRaises(RuntimeError): io.restore()
        self.assertEqual(int.from_bytes(b.ram[48:50], 'little'), 160)
        self.assertFalse(io.restored)

    def test_uncertain_write_blocks_reads_and_restore_without_speculation(self):
        b, io = self.fixture(); io.prepare()
        b.after_write = lambda a: b.ram.__setitem__(62, 59) if a == 42 else None
        with self.assertRaises(RuntimeError): io.command(2001)
        self.assertTrue(io.uncertain_write)
        self.assertEqual(io.pending['goal'], 2001)
        b.ram[62] = 70
        count = len(b.writes)
        with self.assertRaises(RuntimeError): io.read()
        with self.assertRaises(RuntimeError): io.restore()
        self.assertEqual(len(b.writes), count)

    def test_verified_stop_reconciles_only_known_pending_source(self):
        from .native_stop import GroupStop
        b, io = self.fixture(); io.prepare()
        b.after_write = lambda a: b.ram.__setitem__(62, 59) if a == 42 else None
        with self.assertRaises(RuntimeError): io.command(2001)
        b.ram[62] = 70
        w = GroupStop({i:(1950, 2050) for i in range(1, 6)}, contact_axis=2)
        w.bus = b; w.verified = w.restored = True
        w.original[2] = bytes(b.ram[33:71])
        b.put(42, 2003); b.put(67, 2003); b.put(56, 2021)
        w.expected[2] = bytes(b.ram[40:48])
        io.adopt_stop(w)
        self.assertFalse(io.uncertain_write)
        self.assertEqual((io.goal, io.anchor_goal, io.anchor_q), (2003, 2000, 2020))
        self.still(io); io.restore(); self.assertTrue(io.restored)

    def test_unknown_stop_source_cannot_clear_uncertainty(self):
        from .native_stop import GroupStop
        b, io = self.fixture(); io.prepare()
        w = GroupStop({i:(1950, 2050) for i in range(1, 6)}, contact_axis=2)
        w.bus = b; w.verified = w.restored = True
        b.put(46, 601); w.original[2] = bytes(b.ram[33:71]); w.expected[2] = bytes(b.ram[40:48])
        with self.assertRaises(RuntimeError): io.adopt_stop(w)

    def test_cancel_refuses_commands_but_allows_proven_restore(self):
        b, io = self.fixture(1); io.prepare(); io.cancelled = lambda: True
        with self.assertRaises(RuntimeError): io.command(2001)
        self.still(io); io.restore(); self.assertTrue(io.restored)

    def test_lost_ack_requires_matching_full_native_readback(self):
        b, io = self.fixture()
        with patch('shared.experiments.presentation_safety_play_20261110.release_io.receive_write_ack', side_effect=TimeoutError('lost ACK')):
            io.prepare()
        self.assertFalse(io.uncertain_write)
        self.assertTrue(all(v['ack_error'] for v in io.audit))

    def test_partial_write_leaves_pending_and_forbids_speculative_cap_restore(self):
        b, io = self.fixture(); io.prepare()
        b.port.write = lambda packet: len(packet) - 1
        with self.assertRaises(RuntimeError): io.command(2001)
        self.assertTrue(io.uncertain_write)
        self.assertEqual(io.pending['previous_goal'], 2000)
        with self.assertRaises(RuntimeError): io.restore()
        self.assertEqual(int.from_bytes(b.ram[48:50], 'little'), 400)

    def test_temporal_proof_rejects_duplicate_gap_and_q_span(self):
        b, io = self.fixture(1); io.prepare()
        row = io.read()[0]
        for _ in range(8): self.assertFalse(io.observe_still(row))
        with self.assertRaises(RuntimeError): io.restore()
        self.t += .21
        self.assertFalse(io.observe_still(io.read()[0]))
        for index in range(3):
            self.t += .05; b.put(56, 2003 if index == 2 else 2000)
            self.assertFalse(io.observe_still(io.read()[0]))
        with self.assertRaises(RuntimeError): io.restore()

    def test_cap_raise_rechecks_original_profiles_and_time_after_write(self):
        for fault in ('drift', 'expired'):
            b, io = self.fixture(1); io.prepare(); self.still(io)
            def fail(address):
                if address == 41:
                    if fault == 'drift': b.put(46, 322)
                    else: self.t += .19
            b.after_write = fail
            with self.subTest(fault=fault), self.assertRaises(RuntimeError): io.restore()
            self.assertEqual(int.from_bytes(b.ram[48:50], 'little'), 160)

    def test_no_goal_command_can_escape_zero_or_native_word_bounds(self):
        b, io = self.fixture(1, window=(0, 16))
        b.put(42, 0); b.put(56, 0); b.put(67, 0); io.prepare()
        with self.assertRaises(RuntimeError): io.command(-1)
        self.assertFalse(io.uncertain_write)

    def test_reopen_captured_hold_retains_first_source_pins_without_goal_rebase(self):
        b, first = self.fixture(2); first.prepare()
        pins = (first.anchor_goal, first.anchor_q)
        b.put(42, 2005); b.put(67, 2005); b.put(56, 2022)
        b.put(48, 1000); b.put(46, 333); b.ram[41] = 11
        current = bytes(b.ram[33:71]); b.writes.clear()
        resumed = ReleaseIO(b, 2, (1950, 2050), lambda: False, lambda: self.t, pinned_source=pins)
        resumed.prepare()
        self.assertEqual((resumed.anchor_goal, resumed.anchor_q, resumed.goal), (2000, 2020, 2005))
        self.assertEqual(resumed.original, current)
        self.assertEqual(int.from_bytes(b.ram[42:44], 'little'), 2005)
        self.assertFalse(any(a == 42 for a, _ in b.writes))
        for goal in range(2006, 2017): resumed.command(goal)
        with self.assertRaises(RuntimeError): resumed.command(2017)
        self.still(resumed); resumed.restore()
        self.assertEqual((b.ram[41], int.from_bytes(b.ram[46:48], 'little')), (11, 333))

    def test_reopen_outside_original_goal_or_encoder_pin_refuses_before_any_write(self):
        for goal, q in ((2017, 2020), (2000, 2041)):
            b, _ = self.fixture(2)
            b.put(42, goal); b.put(67, goal); b.put(56, q)
            resumed = ReleaseIO(b, 2, (1950, 2050), lambda: False, lambda: self.t,
                                pinned_source=(2000, 2020))
            with self.subTest(goal=goal, q=q), self.assertRaises(RuntimeError): resumed.prepare()
            self.assertEqual(b.writes, [])

    def test_pinned_source_requires_reviewed_integer_goal_and_encoder(self):
        b, _ = self.fixture(1)
        for pins in ((True, 2000), (2000, 2.5), (-1, 2000), (2000, 4096), (2000,), '2000'):
            with self.subTest(pins=pins), self.assertRaises(ValueError):
                ReleaseIO(b, 1, (1950, 2050), lambda: False, lambda: self.t, pinned_source=pins)
        self.assertEqual(b.writes, [])

    def test_calibrated_id2_window_allows_old_measured_goal_span_without_rebasing(self):
        b, _ = self.fixture(2, residual=7)
        b.put(42, 2844); b.put(67, 2844); b.put(56, 2851)
        io = ReleaseIO(b, 2, (2815, 2861), lambda: False, lambda: self.t,
                       calibrated_goal_window=(2819, 2851))
        io.prepare()
        self.assertEqual((io.anchor_goal, io.anchor_q, io.excursion, io.encoder_travel_limit), (2844, 2851, 32, 20))
        for goal in range(2843, 2818, -1):
            # A loaded, still-obstructed encoder need not follow the command.
            b.residual = 2851 - goal
            io.command(goal)
        self.assertEqual(io.goal, 2819)
        n = len(b.writes)
        with self.assertRaises(RuntimeError): io.command(2818)
        self.assertEqual(len(b.writes), n)
        self.assertEqual(io.anchor_q, 2851)

    def test_calibrated_id2_encoder_limit_is_still_twenty_from_original_pin(self):
        b, _ = self.fixture(2)
        b.put(42, 2844); b.put(67, 2844); b.put(56, 2851)
        io = ReleaseIO(b, 2, (2815, 2861), lambda: False, lambda: self.t,
                       calibrated_goal_window=(2819, 2851))
        io.prepare(); b.put(56, 2831); io.read()
        b.put(56, 2830)
        with self.assertRaises(RuntimeError): io.read()

    def test_calibration_refuses_wrong_axis_window_or_unmeasured_goal_span(self):
        b, _ = self.fixture(2)
        for sid, feedback, goals in ((1, (2815,2861), (2819,2851)),
                                     (4, (2815,2861), (2819,2851)),
                                     (2, (2814,2861), (2819,2851)),
                                     (2, (2815,2862), (2819,2851)),
                                     (2, (2815,2861), (2818,2851)),
                                     (2, (2815,2861), [2819,2851])):
            with self.subTest(sid=sid, feedback=feedback, goals=goals), self.assertRaises(ValueError):
                ReleaseIO(b, sid, feedback, lambda: False, lambda: self.t, calibrated_goal_window=goals)
        self.assertEqual(b.writes, [])

    def test_calibrated_source_goal_must_be_in_measured_span_before_writes(self):
        b, _ = self.fixture(2)
        b.put(42, 2818); b.put(67, 2818); b.put(56, 2825)
        io = ReleaseIO(b, 2, (2815, 2861), lambda: False, lambda: self.t,
                       calibrated_goal_window=(2819, 2851))
        with self.assertRaises(RuntimeError): io.prepare()
        self.assertEqual(b.writes, [])

    def test_calibrated_raw_goal_outside_span_rejected_and_original_pins_survive_reopen(self):
        b, _ = self.fixture(2)
        b.put(42, 2839); b.put(67, 2839); b.put(56, 2844)
        io = ReleaseIO(b, 2, (2815,2861), lambda: False, lambda: self.t,
                       pinned_source=(2844,2851), calibrated_goal_window=(2819,2851))
        io.prepare()
        self.assertEqual((io.anchor_goal,io.anchor_q,io.goal), (2844,2851,2839))
        b.put(42, 2852); b.put(67, 2852)
        with self.assertRaises(RuntimeError): io.read()

    def test_explicit_id2_span32_retains_cap_and_twenty_tick_encoder_limit(self):
        b, _ = self.fixture(2, residual=8)
        b.put(42, 2859); b.put(67, 2859); b.put(56, 2867)
        io = ReleaseIO(b, 2, (2800, 2900), lambda: False, lambda: self.t,
                       id2_command_span=32)
        io.prepare()
        for goal in range(2858, 2836, -1):
            b.residual = max(2847, goal + 8) - goal
            io.command(goal)
        self.assertEqual((io.goal, io.anchor_goal, io.anchor_q), (2837, 2859, 2867))
        self.assertEqual((io.excursion, io.encoder_travel_limit), (32, 20))
        self.assertEqual((int.from_bytes(b.ram[48:50], 'little'), b.ram[41]), (400, 8))
        for goal in range(2836, 2826, -1):
            b.residual = 2847 - goal
            io.command(goal)
        count = len(b.writes)
        with self.assertRaises(RuntimeError): io.command(2826)
        self.assertEqual(len(b.writes), count)
        b.put(56, 2846)
        with self.assertRaises(RuntimeError): io.read()

    def test_id2_span_option_rejects_other_axes_and_unknown_values_without_writes(self):
        b, _ = self.fixture(2)
        for sid, span in ((1,32), (4,32), (2,0), (2,17), (2,33), (2,True), (2,32.), (2,'32')):
            with self.subTest(sid=sid, span=span), self.assertRaises(ValueError):
                ReleaseIO(b, sid, (2800,2900), lambda: False, lambda: self.t, id2_command_span=span)
        self.assertEqual(b.writes, [])

    def test_explicit_id2_span_does_not_override_calibrated_absolute_goals(self):
        b, _ = self.fixture(2)
        b.put(42, 2851); b.put(67, 2851); b.put(56, 2851)
        io = ReleaseIO(b, 2, (2815,2861), lambda: False, lambda: self.t,
                       id2_command_span=32, calibrated_goal_window=(2819,2851))
        io.prepare(); count = len(b.writes)
        with self.assertRaises(RuntimeError): io.command(2852)
        self.assertEqual(len(b.writes), count)
