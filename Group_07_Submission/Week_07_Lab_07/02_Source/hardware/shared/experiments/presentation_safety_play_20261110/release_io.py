"""Experimental bounded low-cap release I/O. No clearance or return authority.

No hardware access on import. Only RAM41/42/46/48 are written. A loaded
source goal is retained, and independent GroupStop owns emergency capture.
"""
import math

from normal_gaze_motor import decode_state
from write_ack import receive_write_ack


class ReleaseIO:
    def __init__(self, bus, sid, window, cancelled, clock, pinned_source=None,
                 calibrated_goal_window=None, id2_command_span=16):
        lo, hi = window
        if type(sid) is not int or sid not in (1, 2, 4):
            raise ValueError('Reviewed release axis required')
        if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= 4095:
            raise ValueError('Reviewed absolute window required')
        if pinned_source is not None and (
                type(pinned_source) not in (tuple, list) or len(pinned_source) != 2
                or any(type(value) is not int or not 0 <= value <= 4095 for value in pinned_source)):
            raise ValueError('Pinned source requires original integer goal and encoder')
        if calibrated_goal_window is not None and (
                sid != 2 or type(calibrated_goal_window) is not tuple
                or calibrated_goal_window != (2819, 2851) or (lo, hi) != (2815, 2861)):
            raise ValueError('Only measured ID2 goal/feedback windows allow calibration')
        if (type(id2_command_span) is not int or id2_command_span not in (16, 32)
                or (sid != 2 and id2_command_span != 16)):
            raise ValueError('Explicit extended command span is only reviewed for ID2')
        self.bus, self.sid, self.window = bus, sid, (lo, hi)
        self.cancelled, self.clock = cancelled, clock
        self.calibrated_goal_window = calibrated_goal_window
        self.id2_command_span = id2_command_span
        self.excursion = (32 if sid == 4 or calibrated_goal_window is not None
                          else id2_command_span if sid == 2 else 16)
        self.encoder_travel_limit = 20 if sid == 2 else self.excursion + 4
        self.cap = 400 if sid == 2 else 160
        self.acceleration = 8 if sid == 2 else 3
        self.anchor_goal = self.anchor_q = self.goal = None
        if pinned_source is not None:
            self.anchor_goal, self.anchor_q = pinned_source
            if sid == 4:
                if abs(self.anchor_q - self.anchor_goal) > 12:
                    raise ValueError('Head source residual exceeds reviewed support bound')
                self.excursion = 32 + abs(self.anchor_q - self.anchor_goal)
        self.original = self.expected = self.pending = None
        self.prepared = self.restored = self.uncertain_write = False
        self.audit, self.still, self.preprobe_still = [], [], []
        self.phase = 'NEW'

    def _decode(self):
        raw = bytes(self.bus.read(self.sid, 33, 38))
        if len(raw) != 38:
            raise RuntimeError('Incomplete native release feedback')
        row = decode_state(self.sid, raw)
        row.update(time_s=self.clock(), torque_limit_raw=int.from_bytes(raw[15:17], 'little'), raw=raw)
        if row['mode'] or row['torque_raw'] != 1 or row['status_raw'] or row['voltage_V'] < 6:
            raise RuntimeError('Native support/supply fault')
        if any(not self.window[0] <= row[k] <= self.window[1]
               for k in ('position_raw', 'internal_target_raw', 'goal_raw')):
            raise RuntimeError('Reviewed absolute release window violated')
        if self.anchor_goal is not None and abs(row['goal_raw'] - self.anchor_goal) > self.excursion:
            raise RuntimeError('Pinned source goal excursion exceeded')
        if self.calibrated_goal_window is not None and not self.calibrated_goal_window[0] <= row['goal_raw'] <= self.calibrated_goal_window[1]:
            raise RuntimeError('Goal outside measured ID2 calibration span')
        if self.anchor_q is not None and abs(row['position_raw'] - self.anchor_q) > self.encoder_travel_limit:
            raise RuntimeError('Pinned source encoder travel exceeded')
        if abs(row['internal_target_raw'] - row['goal_raw']) > 16:
            raise RuntimeError('Native trajectory reference unconfirmed')
        return row, raw

    def read(self):
        if self.uncertain_write:
            raise RuntimeError('Uncertain write requires independent stop reconciliation')
        row, raw = self._decode()
        if self.expected is not None and raw[7:17] != bytes(self.expected[7:17]):
            raise RuntimeError('Native support/profile/goal changed')
        return row, raw

    def _write(self, address, data, recovery=False):
        sizes = {41: 1, 42: 2, 46: 2, 48: 2}
        if not self.prepared or address not in sizes or len(data) != sizes[address]:
            raise ValueError('Only scoped release RAM writes allowed')
        if self.uncertain_write:
            raise RuntimeError('Uncertain write forbids further writes')
        if self.cancelled() and not recovery:
            raise RuntimeError('Release probe cancelled')
        value, offset = int.from_bytes(data, 'little'), address - 33
        if address == 42:
            if recovery or not self.window[0] <= value <= self.window[1] or abs(value - self.anchor_goal) > self.excursion:
                raise RuntimeError('Pinned command excursion exceeded')
            if self.calibrated_goal_window is not None and not self.calibrated_goal_window[0] <= value <= self.calibrated_goal_window[1]:
                raise RuntimeError('Command outside measured ID2 calibration span')
        else:
            target = int.from_bytes(self.original[offset:offset + len(data)], 'little') if recovery else {41:self.acceleration, 46:600, 48:self.cap}[address]
            if value != target:
                raise ValueError('Unreviewed release profile/cap')
        expected = bytearray(self.expected)
        expected[offset:offset + len(data)] = data
        self.pending = dict(address=address, value=value, previous_goal=self.goal,
                            goal=value if address == 42 else self.goal,
                            prior_block=bytes(self.expected[7:17]), next_block=bytes(expected[7:17]))
        self.uncertain_write = True
        body = bytes((self.sid, len(data) + 3, 3, address)) + data
        packet = b'\xff\xff' + body + bytes((~sum(body) & 255,))
        port = self.bus.port
        port.reset_input_buffer()
        if port.write(packet) != len(packet):
            raise RuntimeError('Partial release write')
        ack_error = None
        try:
            receive_write_ack(port, self.sid, packet)
        except Exception as error:
            ack_error = str(error)
        row, raw = self._decode()
        if raw[7:17] != bytes(expected[7:17]):
            raise RuntimeError('Release write/readback differs')
        self.expected, self.goal = expected, row['goal_raw']
        self.pending, self.uncertain_write = None, False
        if not recovery:
            self.still = []
            self.preprobe_still = []
        self.audit.append(dict(time_s=self.clock(), id=self.sid, address=address,
                               data_hex=data.hex(), ack_error=ack_error))

    def _effort_ok(self, row, source=False, retry=False):
        error = 34 if self.sid == 2 else (12 if source else 4)
        head_retry=source and retry and self.sid==4
        if head_retry:error=22  # existing supported head hold tolerance
        return (abs(row['position_raw'] - row['goal_raw']) <= error
                and (row['load_raw'] & 1023) < (300 if self.sid == 2 else 48 if head_retry else 32)
                and (row['current_raw'] <= 40 if self.sid == 2 else row['current_raw'] < 3))

    def prepare(self):
        if self.prepared:
            raise RuntimeError('Release preparation cannot repeat')
        row, raw = self.read()
        if (row['speed_raw'] or row['moving_raw'] or row['internal_target_raw'] != row['goal_raw']
                or row['torque_limit_raw'] != 1000 or not self._effort_ok(row, source=True)):
            raise RuntimeError('Fresh static source support required')
        self.original, self.expected = raw, bytearray(raw)
        # A Near pause may capture a new held goal. Keep that native goal, but
        # never let reopening an attempt move the stop epoch's original pins.
        self.goal = row['goal_raw']
        if self.anchor_goal is None:
            self.anchor_goal, self.anchor_q = self.goal, row['position_raw']
            # Match the verified head diagnostic's encoder-relative 32 ticks.
            # Preserve both original pins and the 36-tick actual travel guard.
            if self.sid == 4:
                self.excursion = 32 + abs(self.anchor_q - self.anchor_goal)
        self.prepared, self.phase = True, 'PREPARING'
        self._write(48, self.cap.to_bytes(2, 'little'))
        self._write(46, (600).to_bytes(2, 'little'))
        self._write(41, bytes((self.acceleration,)))
        self.phase = 'PROBE'
        return self.read()[0]

    def command(self, goal):
        if (not self.prepared or self.restored or self.phase != 'PROBE'
                or type(goal) is not int or abs(goal - self.goal) > 1
                or not self.window[0] <= goal <= self.window[1]):
            raise RuntimeError('One-tick relative probe command required')
        self.read()
        self._write(42, goal.to_bytes(2, 'little'))

    def _identity(self):
        return self.goal, bytes(self.expected[7:17]), self.phase

    def _static_ok(self, row, source=False, retry=False):
        try:
            raw = row['raw']
            decoded = decode_state(self.sid, raw)
            return (self.prepared and not self.uncertain_write and row['id'] == self.sid
                    and all(row[k] == v for k, v in decoded.items() if k != 'sampled_monotonic_s')
                    and row['torque_limit_raw'] == int.from_bytes(raw[15:17], 'little')
                    and raw[7:17] == bytes(self.expected[7:17])
                    and row['mode'] == 0 and row['torque_raw'] == 1 and row['status_raw'] == 0
                    and row['voltage_V'] >= 6 and row['goal_raw'] == self.goal
                    and row['internal_target_raw'] == self.goal
                    and not row['speed_raw'] and not row['moving_raw']
                    and all(self.window[0] <= row[k] <= self.window[1] for k in ('position_raw', 'internal_target_raw', 'goal_raw'))
                    and abs(self.goal - self.anchor_goal) <= self.excursion
                    and (self.calibrated_goal_window is None or self.calibrated_goal_window[0] <= self.goal <= self.calibrated_goal_window[1])
                    and abs(row['position_raw'] - self.anchor_q) <= self.encoder_travel_limit
                    and self._effort_ok(row, source=source,retry=retry))
        except (KeyError, TypeError, ValueError):
            return False

    def observe_preprobe_still(self, row, retry=False):
        """Source support eligibility only; never authorizes cap restoration.

        Preserve the held goal. Head source residual may be 5--12 ticks even
        while stationary; requiring restore precision here deadlocks probing.
        Movement proof and strict post-probe restoration remain separate.
        """
        stamp = row.get('time_s')
        if (self.phase != 'PROBE' or type(stamp) not in (int, float)
                or not math.isfinite(stamp) or not 0 <= self.clock() - stamp <= .18
                or not self._static_ok(row, source=True,retry=retry)):
            self.preprobe_still = []
            return False
        identity = self._identity()
        history = self.preprobe_still
        if history and (history[-1][2] != identity or stamp - history[-1][0] > .2):
            history.clear()
        if history and stamp <= history[-1][0]:
            return False
        history.append((stamp, row['position_raw'], identity))
        while len(history) > 4 and stamp - history[1][0] >= .15:
            history.pop(0)
        return (len(history) >= 4 and stamp - history[0][0] >= .15 - 1e-9
                and max(v[1] for v in history) - min(v[1] for v in history) <= 2)

    def observe_still(self, row):
        stamp = row.get('time_s')
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not 0 <= self.clock() - stamp <= .18 or not self._static_ok(row)):
            self.still = []
            return False
        identity = self._identity()
        if self.still and self.still[-1][2] != identity:
            self.still = []
        if self.still and stamp <= self.still[-1][0]:
            return False
        if self.still and stamp - self.still[-1][0] > .2:
            self.still = []
        self.still.append((stamp, row['position_raw'], identity))
        while len(self.still) > 4 and stamp - self.still[1][0] >= .15:
            self.still.pop(0)
        return self._proof_ok()

    def _proof_ok(self):
        return (len(self.still) >= 4 and self.still[-1][0] - self.still[0][0] >= .15 - 1e-9
                and 0 <= self.clock() - self.still[-1][0] <= .18
                and all(v[2] == self._identity() for v in self.still)
                and max(v[1] for v in self.still) - min(v[1] for v in self.still) <= 2)

    def _fresh_static(self, proof_position):
        row, _ = self.read()
        if not self._static_ok(row) or abs(row['position_raw'] - proof_position) > 2:
            raise RuntimeError('Fresh static support differs during restoration')
        if not 0 <= self.clock() - self.still[-1][0] <= .18:
            raise RuntimeError('Temporal support proof expired during restoration')

    def restore(self):
        if self.restored:
            return
        if not self.prepared or self.uncertain_write or not self._proof_ok():
            raise RuntimeError('Known fresh temporal static support proof required')
        proof_position = self.still[-1][1]
        self._fresh_static(proof_position)
        # The temporal proof establishes the held goal. Every changed profile
        # stage gets fresh static evidence; do not demand the old profile again
        # after restoring it, and do not relabel old samples as new evidence.
        for address, data in ((46, self.original[13:15]), (41, self.original[8:9]), (48, self.original[15:17])):
            self._fresh_static(proof_position)
            offset = address - 33
            if bytes(self.expected[offset:offset + len(data)]) != data:
                self._write(address, data, recovery=True)
            self._fresh_static(proof_position)
        self.restored, self.phase = True, 'RESTORED'
        self.still = []

    def adopt_stop(self, writer):
        from .native_stop import GroupStop
        if (not self.prepared or not isinstance(writer, GroupStop) or writer.bus is not self.bus
                or writer.contact_axis != self.sid or not writer.verified or not writer.restored
                or getattr(self.bus, 'unsafe_damping_axes', ())):
            raise RuntimeError('Verified restored matching native stop required')
        old = writer.original.get(self.sid)
        known = {bytes(self.expected[7:17])}
        if self.pending:
            known.update((self.pending['prior_block'], self.pending['next_block']))
        if old is None or old[0] != 0 or old[7:17] not in known:
            raise RuntimeError('Stop source does not match known pending goal/cap/profile')
        expected = bytearray(old)
        expected[7:15] = writer.expected.get(self.sid, old[7:15])
        # GroupStop may change the held goal, but must restore its own source ACC
        # and preserve source Speed/aux/cap before reconciliation is accepted.
        if expected[7] != 1 or expected[8] != old[8] or expected[11:17] != old[11:17]:
            raise RuntimeError('Native stop profile differs from known source')
        row, raw = self._decode()
        if (raw[7:17] != bytes(expected[7:17]) or row['internal_target_raw'] != row['goal_raw']
                or row['speed_raw'] or row['moving_raw']):
            raise RuntimeError('Captured native hold not confirmed')
        self.expected, self.goal = expected, row['goal_raw']
        self.pending, self.uncertain_write, self.still = None, False, []
        self.phase = 'ABORT_HELD'
        self.audit.append(dict(time_s=self.clock(), id=self.sid, kind='SUPPORTED_STOP_ADOPTED',
                               goal=self.goal, anchor_goal=self.anchor_goal, anchor_q=self.anchor_q))
