"""Pure, experimental bounded-release planner; never a force safety certificate.

The raw effort/error boundaries are existing experimental observations, not
physical force limits. The caller owns RAM/profile writes, stop/hold, retries,
and restoration. Reuse the original source anchors across attempts; this plan
never expands its source-goal-relative target or certifies the return path.
"""
import math


class ReleasePlan:
    """One tick per command, fresh encoder progress required for a local pass."""

    def __init__(self, sid, anchor_goal, anchor_q, normal_goal, window, now,
                 calibrated_goal_window=None, id2_command_span=16):
        if id2_command_span not in (16, 32) or (sid != 2 and id2_command_span != 16):
            raise ValueError('Optional command span is ID2 only and must be16 or32')
        if sid not in (1, 2, 4):
            raise ValueError('ReleasePlan supports only ID1, ID2, ID4')
        values = (anchor_goal, anchor_q, normal_goal, now, *window)
        if len(window) != 2 or not all(math.isfinite(v) for v in values):
            raise ValueError('Finite anchors, time, and reviewed window required')
        lo, hi = window
        if lo > hi or not lo <= anchor_goal <= hi or not lo <= anchor_q <= hi:
            raise ValueError('Source anchors must lie inside reviewed window')
        if any(int(v) != v for v in (anchor_goal, anchor_q, normal_goal, lo, hi)):
            raise ValueError('Encoder goals and window must be integer ticks')
        self.sid = sid
        self.anchor_goal = int(anchor_goal)
        self.anchor_q = int(anchor_q)
        self.normal_goal = int(normal_goal)
        self.window = (int(lo), int(hi))
        self.excursion = 32 if sid == 4 else 16
        self.command_excursion = id2_command_span if sid == 2 else self.excursion
        if sid == 4:
            if abs(self.anchor_q-self.anchor_goal) > 12:
                raise ValueError('Head source residual exceeds reviewed support bound')
            self.command_excursion = 32 + abs(self.anchor_q-self.anchor_goal)
        self.command_window = self.window
        self.target_normal = sid == 2 and id2_command_span == 32 and calibrated_goal_window is None
        if calibrated_goal_window is not None:
            # This opt-in is valid only for the existing ID2 Normal diagnostic.
            # Caller must verify its recorded whole-body/head pose context.
            # Encoder bounds remain source-q +/-20 despite the wider command span.
            if (sid != 2 or tuple(calibrated_goal_window) != (2819, 2851)
                    or self.window != (2815, 2861)
                    or not 2819 <= self.anchor_goal <= 2851):
                raise ValueError('Unsupported calibrated release context/window')
            self.command_excursion = 32
            self.command_window = (2819, 2851)
        self.duration = 1.6 if self.command_excursion == 32 else .8
        if sid == 4:
            # Preserve the original 32-tick/1.6s goal-ramp rate even when
            # traversing the pre-existing source goal/encoder residual.
            self.duration = 1.6 * self.command_excursion / 32
        self.started = now
        self.start_goal = self.anchor_goal
        self.goal = self.start_goal
        self.stepped = False
        self.motion_start = None
        self.sign = self._direction(anchor_q)
        self.source_sign = self.sign
        self.target = self._target()
        self.last_stamp = None
        self.last_q = None
        self.flow = []
        self.terminal = None
        self.breakaway_since = None
        self.peak_progress = 0
        self.motion_verified = False

    def start_at(self, goal):
        """Resume from a verified current goal without changing original pins.

        Call only before the first step, after the coordinator has read back the
        retained goal. The time origin remains the attempt construction time.
        """
        if self.stepped:
            raise ValueError('Cannot change ramp start after first step')
        try:
            valid = (math.isfinite(goal) and int(goal) == goal
                     and self.command_window[0] <= goal <= self.command_window[1]
                     and abs(goal-self.anchor_goal) <= self.command_excursion)
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ValueError('Ramp start outside original pinned command bounds')
        self.start_goal = self.goal = int(goal)

    def _direction(self, q):
        distance = self.normal_goal - q
        if distance == 0:
            distance = self.anchor_goal - q
        return (distance > 0) - (distance < 0)

    def _target(self):
        if self.sid == 4:
            return min(self.command_window[1], max(self.command_window[0],
                       self.anchor_q + self.sign * 32))
        if self.target_normal:
            bounded_normal = min(self.anchor_goal+self.command_excursion,
                                 max(self.anchor_goal-self.command_excursion, self.normal_goal))
            if self.source_sign * (bounded_normal-self.anchor_goal) < 4:
                bounded_normal = self.anchor_goal + self.source_sign*self.command_excursion
            return min(self.command_window[1], max(self.command_window[0], bounded_normal))
        return min(self.command_window[1], max(self.command_window[0],
                   self.anchor_goal + self.sign * self.command_excursion))

    def _result(self, action, reason=None, **extra):
        result = dict(action=action, sid=self.sid, anchor_goal=self.anchor_goal,
                      anchor_q=self.anchor_q, motion_start=self.motion_start,
                      target=self.target, whole_path_clearance=False, **extra)
        if reason:
            result['reason'] = reason
        if action in ('passed', 'blocked', 'fault'):
            self.terminal = result
        return result

    def step(self, row, now):
        """Return command(goal), wait, passed, blocked, or fault; perform no I/O.

        Terminal outcomes are sticky. A coordinator may hold and later construct
        a new attempt with the SAME original anchors, never the displaced hold.
        Raw speed is recorded but not used as signed encoder evidence.
        """
        self.stepped = True
        if self.terminal is not None:
            return dict(self.terminal)
        required = ('time_s', 'position_raw', 'goal_raw', 'internal_target_raw',
                    'current_raw', 'load_raw', 'moving_raw', 'speed_raw',
                    'mode', 'torque_raw', 'status_raw', 'voltage_V')
        try:
            if not math.isfinite(now) or not all(math.isfinite(row[k]) for k in required):
                return self._result('fault', 'nonfinite native feedback')
        except (KeyError, TypeError, ValueError):
            return self._result('fault', 'missing or invalid native feedback')
        if row.get('id', self.sid) != self.sid:
            return self._result('fault', 'feedback axis differs')
        t, q = row['time_s'], row['position_raw']
        if now < self.started:
            return self._result('fault', 'clock precedes attempt')
        if now - self.started >= 6.:
            return self._result('blocked', 'bounded probe timeout')
        if not 0 <= now - t <= .18:
            return self._result('blocked', 'stale or future probe feedback')
        if self.last_stamp is not None and t <= self.last_stamp:
            return self._result('blocked', 'nonincreasing probe timestamp')
        if self.last_stamp is not None and t - self.last_stamp > .2 + 1e-9:
            return self._result('blocked', 'probe feedback gap')
        lo, hi = self.window
        if (row['mode'] != 0 or row['torque_raw'] != 1 or row['status_raw'] != 0
                or row['voltage_V'] < 6
                or any(not lo <= row[k] <= hi for k in
                       ('position_raw', 'goal_raw', 'internal_target_raw'))):
            return self._result('fault', 'native support/supply/reviewed window fault')
        if row['goal_raw'] != self.goal:
            return self._result('fault', 'commanded goal readback differs')
        if abs(q - self.anchor_q) > self.excursion + 4:
            return self._result('blocked', 'encoder outside pinned source excursion')
        if self.motion_start is None:
            self.motion_start = q
            self.sign = self._direction(q)
            self.target = self._target()
            if not self.sign or self.sign * (self.target - q) <= 0:
                return self._result('blocked', 'no_probe_space')
        progress = self.sign * (q - self.motion_start)
        # The same native two-tick noise/settling band used for hold proof
        # must not become a terminal reversal on a single encoder tick.
        # Bound cumulative rollback from the peak, not each individual step.
        if progress < self.peak_progress - 2:
            return self._result('blocked', 'encoder reversed intended direction')
        if self.last_q is not None and self.sign * (q - self.last_q) < 0:
            self.flow.clear()
        self.peak_progress = max(self.peak_progress, progress)
        self.last_stamp, self.last_q = t, q
        pwm = int(row['load_raw']) & 1023
        current = row['current_raw']
        error = abs(row['internal_target_raw'] - q)
        if self.sid == 2:
            effort_ok = 0 <= current <= 40 and pwm < 300 and error <= 34
        elif self.sid == 4:
            # Dynamic breakaway only: recorded cap160/Speed600/ACC3 evidence
            # id4_free_probe_1794421237652381012 reached PWM47/error26 with
            # current2 and actual directional movement under cap160.
            # This does not relax the caller's separate static restore proof.
            effort_ok = 0 <= current < 3 and pwm <= 47 and error <= 32
        else:
            # Match the accepted ID1 probe's transient error envelope.
            # PWM32/error8 are release-proof limits, not immediate retry
            # limits: run_1794413428236689224 otherwise retried41 times at
            # PWM32--34/error8--9 with current0--1 before breakaway.
            # At the exact12-tick breakaway boundary, give the native loop
            # time to respond rather than cancelling on its first sample.
            # Do not advance the host goal at that boundary (below).
            effort_ok = 0 <= current < 3 and error <= 12
        if not effort_ok:
            return self._result('blocked', 'renewed experimental effort/error',
                                current_raw=current, pwm_raw=pwm, internal_error_ticks=error)
        if progress < 4:
            self.motion_verified = False
            self.flow.clear()
        elif not self.motion_verified:
            # Confirm only with new readings AFTER this attempt's measured
            # movement. Never reuse quiet samples collected before breakaway.
            self.motion_verified = True
            self.flow.clear()
        good = abs(row['internal_target_raw'] - row['goal_raw']) <= 2
        good = good and self.motion_verified
        if self.sid == 1:
            good = good and error <= 8 and pwm < 32 and current < 3
        if good:
            self.flow.append((t, q))
        else:
            self.flow.clear()
        if (len(self.flow) >= 4 and self.flow[-1][0] - self.flow[0][0] >= .15 - 1e-9
                and progress >= 4
                and self.motion_verified):
            return self._result('passed', 'fresh local directional encoder progress',
                                progress_ticks=progress, readings=len(self.flow),
                                span_s=t-self.flow[0][0], current_raw=current,
                                pwm_raw=pwm, internal_error_ticks=error,
                                speed_raw=row['speed_raw'], moving_raw=row['moving_raw'])
        if self.sid == 1 and error == 12:
            if self.breakaway_since is None:
                self.breakaway_since = now
            if now-self.breakaway_since >= .3:
                return self._result('blocked', 'bounded native breakaway dwell expired')
            return self._result('wait', 'bounded native breakaway dwell')
        self.breakaway_since = None
        u = min(1., max(0., (now-self.started)/self.duration))
        desired = round(self.start_goal + (self.target-self.start_goal)*u*u*(3-2*u))
        delta = max(-1, min(1, desired-self.goal))
        if delta:
            self.goal += delta
            return self._result('command', goal=self.goal)
        return self._result('wait')
