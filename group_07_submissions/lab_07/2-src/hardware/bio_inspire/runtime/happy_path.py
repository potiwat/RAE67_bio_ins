"""Offline Happy reference in player-view coordinates, NOT servo commands.

The smooth two-lobe curve is a reference drawing (dimensionless), not a fitted
Cartesian trajectory from the taught raw poses. Raw-to-model/head calibration
must be established before a physical task solver can consume this shape.
"""
import math
from dataclasses import dataclass


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class CalibrationRequired(ValueError):
    pass


@dataclass(frozen=True)
class ReferenceTarget:
    position: tuple[float, float]
    tangent: tuple[float, float]
    curvature_vector: tuple[float, float]
    frame: str = 'player_view_reference'
    units: str = 'dimensionless'
    derivative_units: str = 'per_CPG_cycle_progress'
    motor_goals: None = None
    hardware_validated: bool = False


class HappyReferencePath:
    """One cycle: center -> left upper/outer lower -> center -> right -> center.

    x=-sin(theta), y=sin(2*theta)+sin(theta)^2. Both lobes share heights
    and mirrored horizontal extents. This is a smooth oval-like reference,
    not two exact conic ellipses, nor a measured path of the lamp head.
    x increases toward the viewer's right; y increases upward in the drawing.
    Derivatives are with respect to cycle progress, not seconds or motor angle.
    """
    def sample(self, progress):
        if not finite(progress) or progress < 0:
            raise ValueError('Finite nonnegative CPG progress required')
        theta = 2 * math.pi * (progress % 1.)
        k = 2 * math.pi
        return ReferenceTarget(
            position=(-math.sin(theta), math.sin(2*theta) + math.sin(theta)**2),
            tangent=(-k*math.cos(theta), k*(2*math.cos(2*theta)+math.sin(2*theta))),
            curvature_vector=(k*k*math.sin(theta), k*k*(-4*math.sin(2*theta)+2*math.cos(2*theta))))


class CpgPhaseProgress:
    """Unwrap the existing clockwise SO(2) pair; never resets its oscillator.

    Call continuously, including while expressive output is masked. This only
    identifies phase from a nonzero oscillator pair; it does not estimate a
    person's breathing or verify actuator phase. Missing model updates require
    an explicit new tracker, rather than guessing how many turns were skipped.
    """
    def __init__(self):
        self.last_time = self.last_updates = self.last_angle = None
        self.progress = None

    def advance(self, o1, o2, updates, now):
        if not all(finite(v) for v in (o1, o2, now)) or now < 0 or math.hypot(o1, o2) < 1e-12:
            raise ValueError('Finite nonzero CPG pair and valid clock required')
        if type(updates) is not int or updates < 0:
            raise ValueError('Nonnegative CPG update counter required')
        if self.last_time is not None:
            if now <= self.last_time:
                raise ValueError('Phase clock must increase')
            if not 0 <= updates-self.last_updates <= 1:
                raise ValueError('CPG reset/missing updates: phase cannot be inferred safely')
        angle = math.atan2(-o2, o1)
        if self.last_angle is None:
            progress = (angle % (2*math.pi)) / (2*math.pi)
        else:
            delta = (angle-self.last_angle+math.pi) % (2*math.pi)-math.pi
            if delta < -1e-10:
                raise ValueError('Reversed or aliased SO(2) phase')
            progress = self.progress + max(0., delta)/(2*math.pi)
        self.last_time, self.last_updates, self.last_angle = now, updates, angle
        self.progress = progress
        return progress


def build_symmetric_path(teaching_poses, model, calibration):
    """Physical path factory is deliberately unavailable pending Task 3.

    A dictionary saying verified=True alone is not raw-to-URDF/camera evidence.
    Use HappyReferencePath for offline design; never convert it to raw by guess.
    """
    raise CalibrationRequired('Physical Happy path needs verified raw/model/camera calibration and task solving; only the dimensionless reference exists')


@dataclass(frozen=True, slots=True)
class JointLoopPreview:
    """Empirical JOINT-SPACE preview from taught, symmetric body anchors.

    These floating raw references are NOT motor commands or a verified head
    path. Both body joints use the taught upper/lower direction, unlike the
    rejected opposite-sign decoder. ID4/5 remain the gaze problem; no taught
    constant head angle is silently reused as a pointing solution.
    """
    center_yaw: float
    yaw_span: float
    upper: tuple[float, float]
    lower: tuple[float, float]
    hardware_validated: bool = False

    def __post_init__(self):
        if (type(self.upper) is not tuple or type(self.lower) is not tuple
                or len(self.upper)!=2 or len(self.lower)!=2
                or not all(finite(v) for v in (self.center_yaw,self.yaw_span,*self.upper,*self.lower))
                or self.yaw_span<=0 or not 0<=self.center_yaw-self.yaw_span<self.center_yaw+self.yaw_span<=4095
                or not all(0<=u<l<=4095 for u,l in zip(self.upper,self.lower))
                or self.hardware_validated is not False):
            raise ValueError('Invalid/unverified teaching preview')

    @classmethod
    def from_template(cls, template):
        try:
            return cls(template['center_yaw_raw'],template['yaw_half_span_ticks'],
                       tuple(template['upper_body_raw'][str(i)] for i in (2,3)),
                       tuple(template['lower_body_raw'][str(i)] for i in (2,3)))
        except (KeyError,TypeError) as error:
            raise ValueError('Complete teaching template required') from error

    def sample(self, progress):
        target=HappyReferencePath().sample(progress)
        x,y=target.position
        # y=.5+sin(2theta)-.5cos(2theta), hence exact analytic extrema.
        radius=math.sqrt(1.25)
        elevation=(y-(.5-radius))/(2*radius)
        body=tuple(l+(u-l)*elevation for u,l in zip(self.upper,self.lower))
        return (self.center_yaw+self.yaw_span*x,*body)
