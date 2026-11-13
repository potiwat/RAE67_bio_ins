"""Pure five-joint arbitration and an opt-in guarded unicast writer.

Not connected to live producers yet. Caller supplies command bounds, not
feedback tolerances. Writer needs the existing exclusive, ACK-checking bus.
Arming, tuning, health reads and emergency hold remain separate transactions.
"""
import math
import time
from dataclasses import dataclass

IDS = set(range(1, 6))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class JointIntent:
    joint_id: int
    target_ticks: float
    producer: str
    priority: int
    source_id: str


@dataclass(frozen=True)
class JointCommand:
    joint_id: int
    target_float_ticks: float
    target_ticks: int
    producer: str
    source_id: str
    low: float
    high: float


@dataclass(frozen=True)
class CommandFrame:
    tick_id: int
    joints: tuple[JointCommand, ...]


def validate_frame(frame):
    if not isinstance(frame, CommandFrame) or type(frame.tick_id) is not int or frame.tick_id < 0:
        raise ValueError('Invalid frame/tick')
    if type(frame.joints) is not tuple or len(frame.joints) != 5:
        raise ValueError('Five immutable joint commands required')
    for sid, joint in enumerate(frame.joints, 1):
        if not isinstance(joint, JointCommand) or type(joint.joint_id) is not int or joint.joint_id != sid:
            raise ValueError('Exactly IDs1..5 in order required')
        if not all(finite(v) for v in (joint.low, joint.high, joint.target_float_ticks)):
            raise ValueError('Non-finite frame value')
        if not 0 <= joint.low <= joint.target_float_ticks <= joint.high <= 4095:
            raise ValueError('Float target outside command bounds')
        if type(joint.target_ticks) is not int or joint.target_ticks != round(joint.target_float_ticks) or not joint.low <= joint.target_ticks <= joint.high:
            raise ValueError('Rounded target outside bounds or inconsistent')
        if not all(isinstance(v, str) and v for v in (joint.producer, joint.source_id)):
            raise ValueError('Command provenance required')


class FrameComposer:
    def compose(self, tick_id, previous_targets, intents, bounds):
        if set(previous_targets) != IDS or set(bounds) != IDS or any(type(k) is not int for k in (*previous_targets, *bounds)):
            raise ValueError('Explicit previous targets/bounds for IDs1..5 required')
        candidates = {i: [] for i in IDS}
        for intent in intents:
            if not isinstance(intent, JointIntent) or type(intent.joint_id) is not int or intent.joint_id not in IDS:
                raise ValueError('Invalid joint intent')
            if not finite(intent.target_ticks) or type(intent.priority) is not int:
                raise ValueError('Finite target and integer priority required')
            if not all(isinstance(v, str) and v for v in (intent.producer, intent.source_id)):
                raise ValueError('Intent provenance required')
            candidates[intent.joint_id].append(intent)
        commands = []
        for sid in range(1, 6):
            values = candidates[sid]
            if values:
                highest = max(v.priority for v in values)
                winners = [v for v in values if v.priority == highest]
                if len(winners) != 1:
                    raise ValueError(f'ID{sid}: equal-priority conflict')
                winner = winners[0]
                target, producer, source = winner.target_ticks, winner.producer, winner.source_id
            else:
                target, producer, source = previous_targets[sid], 'previous_command_hold', f'held_ID{sid}'
            if not finite(target):
                raise ValueError('Finite previous command required')
            low, high = bounds[sid]
            commands.append(JointCommand(sid, target, round(target), producer, source, low, high))
        frame = CommandFrame(tick_id, tuple(commands))
        validate_frame(frame)
        return frame


@dataclass(frozen=True)
class CommitEntry:
    joint_id: int
    target_ticks: int
    sent_s: float
    readback_s: float


@dataclass(frozen=True)
class CommitReport:
    status: str
    committed: tuple[CommitEntry, ...] = ()
    uncertain_joint_id: int | None = None
    requires_recovery: bool = False
    requires_hold: bool = False
    error: str = ''


class GuardedFrameWriter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.blocked = False
        self.last_tick = -1

    def recover(self, operator_confirmed):
        """Caller must reconcile power/health/pose and hold before confirmation.

        This does not restore torque, clear bus faults, or issue any command.
        """
        if operator_confirmed is not True:
            raise ValueError('Explicit recovery confirmation required')
        self.blocked = False

    def commit(self, frame, bus, cancelled):
        # Validate the WHOLE immutable frame before touching the bus.
        validate_frame(frame)
        if self.blocked:
            return CommitReport('recovery_required', requires_recovery=True, requires_hold=True)
        if frame.tick_id <= self.last_tick:
            return CommitReport('stale_frame')
        self.last_tick = frame.tick_id
        committed = []
        for joint in frame.joints:
            if cancelled():
                self.blocked = True
                return CommitReport('cancelled', tuple(committed), requires_recovery=True, requires_hold=bool(committed))
            try:
                data = joint.target_ticks.to_bytes(2, 'little')
                sent = self.clock()
                # Existing guarded bus.write checks the unicast ACK and readback.
                bus.write(joint.joint_id, 42, data)
                if bus.read(joint.joint_id, 42, 2) != data:
                    raise RuntimeError('Goal readback mismatch')
                committed.append(CommitEntry(joint.joint_id, joint.target_ticks, sent, self.clock()))
            except Exception as error:
                self.blocked = True
                return CommitReport('failed', tuple(committed), joint.joint_id, True, True, str(error))
        return CommitReport('committed', tuple(committed))
