"""Device-free quintic command transitions with explicit q/v/a boundaries.

All quantities are host command ticks and seconds, NOT native servo speed/ACC
register units. No default hardware limits and no UART, PID or EEPROM access.
Float-polynomial validation is separate from quantized/measured motion.
"""
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class CommandState:
    q: float
    v: float = 0.
    a: float = 0.


@dataclass(frozen=True)
class JointLimits:
    low: float
    high: float
    max_velocity: float
    max_acceleration: float
    max_jerk: float


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    violations: tuple[str, ...]
    maxima: dict
    evidence: str = 'analytic_float_command_only_not_quantized_or_measured'


class TrajectoryLimitError(ValueError):
    pass


def _derivative(coefficients):
    return tuple(i*c for i, c in enumerate(coefficients) if i)


def _evaluate(coefficients, x):
    result = 0.
    for coefficient in reversed(coefficients):
        result = result*x + coefficient
    return result


def _roots_unit_interval(coefficients):
    """Bounded-degree polynomial roots via derivative-isolated monotone spans.

    Includes even-multiplicity roots at derivative critical points. This is a
    numerical analytic-extrema check, not a certified interval arithmetic proof.
    """
    values = list(coefficients)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Nonfinite polynomial derivative')
    while values and values[-1] == 0:
        values.pop()
    if len(values) <= 1:
        return []
    scale = max(abs(v) for v in values)
    values = [v/scale for v in values]
    critical = _roots_unit_interval(_derivative(values))
    partitions = sorted({0., *critical, 1.})
    roots = [u for u in partitions if abs(_evaluate(values, u)) < 1e-12]
    for low, high in zip(partitions, partitions[1:]):
        f_low, f_high = _evaluate(values, low), _evaluate(values, high)
        if f_low*f_high >= 0:
            continue
        for _ in range(64):
            middle = (low+high)/2
            f_middle = _evaluate(values, middle)
            if f_low*f_middle <= 0:
                high = middle
            else:
                low, f_low = middle, f_middle
        roots.append((low+high)/2)
    return sorted(set(roots))


def _states(states):
    if not isinstance(states, dict) or set(states) != set(range(1, 6)) or any(type(i) is not int for i in states):
        raise ValueError('Command state required for exactly IDs1..5')
    result = {}
    for sid, state in states.items():
        if not isinstance(state, CommandState) or not all(finite(v) for v in (state.q, state.v, state.a)):
            raise ValueError('Finite q/v/a command states required')
        result[sid] = CommandState(float(state.q), float(state.v), float(state.a))
    return result


@dataclass(frozen=True, init=False, slots=True)
class QuinticTransition:
    duration_s: float
    start: Mapping[int, CommandState]
    end: Mapping[int, CommandState]
    coefficients: Mapping[int, tuple[float, ...]]

    def __init__(self, current_command_state, target_state, duration_s):
        if not finite(duration_s) or duration_s <= 0:
            raise ValueError('Explicit positive finite duration required')
        start_states = _states(current_command_state)
        end_states = _states(target_state)
        all_coefficients = {}
        t = duration_s
        for sid in range(1, 6):
            start, end = start_states[sid], end_states[sid]
            c0, c1, c2 = start.q, start.v*t, .5*start.a*t*t
            q = end.q-(c0+c1+c2)
            v = end.v*t-(c1+2*c2)
            a = end.a*t*t-2*c2
            coefficients = (c0, c1, c2, 10*q-4*v+.5*a, -15*q+7*v-a, 6*q-3*v+.5*a)
            if not all(math.isfinite(c) for c in coefficients):
                raise ValueError('Transition coefficient overflow')
            # Endpoint sampling must not hide catastrophic cancellation inside
            # the polynomial. These are numerical consistency tolerances, not
            # physical servo settling allowances or approved motion bounds.
            for u, endpoint in ((0., start), (1., end)):
                polynomial = coefficients
                for order, expected in enumerate((endpoint.q, endpoint.v, endpoint.a)):
                    computed = _evaluate(polynomial, u)
                    for _ in range(order):
                        computed /= t
                    if not math.isfinite(computed) or not math.isclose(computed, expected, rel_tol=1e-10, abs_tol=1e-7):
                        raise ValueError('Numerically unstable transition endpoint polynomial')
                    polynomial = _derivative(polynomial)
            all_coefficients[sid] = coefficients
        object.__setattr__(self, 'duration_s', float(duration_s))
        object.__setattr__(self, 'start', MappingProxyType(start_states))
        object.__setattr__(self, 'end', MappingProxyType(end_states))
        object.__setattr__(self, 'coefficients', MappingProxyType(all_coefficients))

    def sample(self, elapsed_s):
        if not finite(elapsed_s) or not 0 <= elapsed_s <= self.duration_s:
            raise ValueError('Sample outside transition duration')
        if elapsed_s == 0:
            return dict(self.start)
        if elapsed_s == self.duration_s:
            return dict(self.end)
        u, t = elapsed_s/self.duration_s, self.duration_s
        return {sid: CommandState(_evaluate(c, u), _evaluate(_derivative(c), u)/t,
                                  _evaluate(_derivative(_derivative(c)), u)/t/t)
                for sid, c in self.coefficients.items()}

    def validate(self, limits):
        if not isinstance(limits, dict) or set(limits) != set(range(1, 6)) or any(type(i) is not int for i in limits):
            raise ValueError('Explicit limits for exactly IDs1..5 required; no hardware defaults')
        violations, maxima = [], {}
        for sid in range(1, 6):
            limit = limits[sid]
            if not isinstance(limit, JointLimits) or not all(finite(v) for v in (limit.low, limit.high, limit.max_velocity, limit.max_acceleration, limit.max_jerk)):
                raise ValueError('Finite command limits required')
            if not limit.low < limit.high or min(limit.max_velocity, limit.max_acceleration, limit.max_jerk) <= 0:
                raise ValueError('Invalid command bounds or nonpositive rate limits')
            c = self.coefficients[sid]
            maxima[sid] = {}
            for order, name, maximum in ((0, 'position', None), (1, 'velocity', limit.max_velocity),
                                         (2, 'acceleration', limit.max_acceleration), (3, 'jerk', limit.max_jerk)):
                derivative = c
                for _ in range(order):
                    derivative = _derivative(derivative)
                points = (0., *_roots_unit_interval(_derivative(derivative)), 1.)
                values = [_evaluate(derivative, u) for u in points]
                for _ in range(order):
                    values = [v/self.duration_s for v in values]
                if order < 3:
                    field = ('q', 'v', 'a')[order]
                    values.extend((getattr(self.start[sid], field), getattr(self.end[sid], field)))
                if not all(math.isfinite(v) for v in values):
                    raise ValueError('Nonfinite transition extrema')
                if order == 0:
                    maxima[sid]['position_min'] = min(values)
                    maxima[sid]['position_max'] = max(values)
                    if min(values) < limit.low or max(values) > limit.high:
                        violations.append(f'ID{sid}: position outside supplied limits')
                else:
                    maxima[sid][name] = max(abs(v) for v in values)
                    if not math.isfinite(maxima[sid][name]) or maxima[sid][name] > maximum:
                        violations.append(f'ID{sid}: {name} exceeds supplied limit')
        return ValidationReport(not violations, tuple(violations), maxima)


def plan_transition(current_command_state, target_state, limits, *, duration_s):
    """Return only a float-command trajectory passing caller-supplied limits.

    Does not auto-stretch time, silently change a course condition, quantize,
    approve hardware, or produce motor writes. Failed plans emit no goals.
    """
    transition = QuinticTransition(current_command_state, target_state, duration_s)
    report = transition.validate(limits)
    if not report.valid:
        raise TrajectoryLimitError('; '.join(report.violations))
    return transition
