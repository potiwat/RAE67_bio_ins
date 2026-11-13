"""Bounded post-settle observations from the existing owner; no device access."""
import copy
import math
from collections import deque


class ProbeObservation:
    """Record after an acknowledged ID2/3/4/5 request, never issue motor commands.

    Uses existing 22-tick ID4 goal allowance and 0.5-second face age policy.
    The 2-second minimum and 10-second diagnostic timeout only govern logging.
    A valid observation is NOT a calibrated image Jacobian or verified identity.
    """
    def __init__(self):
        self._samples = deque(maxlen=8)
        self.pending = None
        self.stationary_count = 0
        self.last_position = None
        self.pending_reason = None
        self.settled_since = None

    @property
    def samples(self):
        return copy.deepcopy(list(self._samples))

    def request(self, event):
        joint=event.get('joint_id',4)
        if type(joint) is not int or joint not in (2,3,4,5):raise ValueError('Only reviewed probe joints2/3/4/5')
        if self.pending is not None:
            self._finish(False, 'superseded_before_settled_observation')
        self.pending = copy.deepcopy(event)
        self.stationary_count = 0
        self.last_position = None
        self.settled_since = None
        self.pending_reason = 'waiting_for_settled_post_command_observation'

    def _finish(self, valid, reason, **data):
        sample = dict(request=self.pending, joint_id=self.pending.get('joint_id',4), valid_observation=valid, calibration_valid=False,
                      reason=reason, source_id_kind='frame_sequence_not_player_identity',
                      clock_domains=dict(request='CLOCK_BOOTTIME', observation='CLOCK_BOOTTIME',
                                         servo_sample='CLOCK_MONOTONIC'), **data)
        self._samples.append(copy.deepcopy(sample))
        self.pending = None
        self.pending_reason = None
        return sample

    def cancel(self, reason):
        if self.pending is not None:
            return self._finish(False, reason)
        return None

    def observe(self, now, rows, face, state):
        if self.pending is None:
            return None
        if state not in ('READY', 'FOLLOWING'):
            return self._finish(False, 'controller_not_ready')
        age = now-self.pending['time_s']
        if age < 0:
            return self._finish(False, 'invalid_observation_clock')
        if age > 10.:
            return self._finish(False, 'diagnostic_timeout_'+str(self.pending_reason))
        if age < 2.:
            return None
        healthy = (len(rows) == 5 and [r.get('id') for r in rows] == list(range(1, 6))
                   and all(r.get('torque_raw') == 1 and r.get('mode') == 0 and r.get('status_raw') == 0
                           and r.get('speed_raw') == 0 and r.get('moving_raw') == 0 for r in rows))
        if not healthy:
            self.stationary_count = 0
            self.last_position = None
            self.settled_since = None
            self.pending_reason = 'motors_not_stationary_and_healthy'
            return None
        positions = tuple(r['position_raw'] for r in rows)
        target = self.pending['target_raw']
        joint=self.pending.get('joint_id',4);index=joint-1;tolerance=22 if joint==4 else 34
        if abs(positions[index]-target) > tolerance:
            self.stationary_count = 0
            self.last_position = None
            self.settled_since = None
            self.pending_reason = f'ID{joint}_outside_existing_goal_tolerance'
            return None
        stable = self.last_position is None or all(abs(a-b) <= 2 for a,b in zip(positions,self.last_position))
        self.stationary_count = self.stationary_count+1 if stable else 1
        self.last_position = positions
        if not stable:self.settled_since = None
        if self.stationary_count >= 3 and self.settled_since is None:
            self.settled_since = now
        face = face or {}
        captured = face.get('captured_s')
        xy = face.get('error_xy')
        fresh = (face.get('status') in ('TRACKING', 'ACQUIRED')
                 and type(captured) in (int,float) and math.isfinite(captured)
                 and self.pending['time_s'] <= captured <= now and now-captured <= .5
                 and self.settled_since is not None and captured >= self.settled_since
                 and isinstance(xy,(list,tuple)) and len(xy) == 2
                 and all(type(v) in (int,float) and math.isfinite(v) for v in xy))
        if not fresh:
            self.pending_reason = 'waiting_for_fresh_post_command_face'
            return None
        if self.stationary_count < 3:
            self.pending_reason = 'waiting_for_three_stationary_samples'
            return None
        return self._finish(True, 'settled_fresh_observation', observed_s=now,
                            settled_since_boottime_s=self.settled_since,
                            actual_raw=positions[index], rows=rows, observation=face)
