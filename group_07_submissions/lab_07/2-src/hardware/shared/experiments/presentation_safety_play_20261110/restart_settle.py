"""Read-only, bounded standstill confirmation for verified button handoff.

No relaxed speed/travel criterion, fault clearing, or motor writes. The original
start validator still sees real snapshots and runs all its existing checks.
"""
from contextvars import ContextVar
from contextlib import contextmanager

_goals = ContextVar('experimental_verified_parked_restart', default=None)


@contextmanager
def restart_scope(goals):
    if set(goals) != set(range(1, 6)) or any(type(q) is not int for q in goals.values()):
        raise ValueError('Verified five-axis parked goals required')
    token = _goals.set(dict(goals))
    try:
        yield
    finally:
        _goals.reset(token)


def settle_snapshot(read, origin, goals, now, wait, cancelled):
    started = now()
    stable = 0
    while True:
        if cancelled():
            raise RuntimeError('Parked restart cancelled')
        rows = read()
        if [r['id'] for r in rows] != list(range(1, 6)):
            raise RuntimeError('Parked restart feedback incomplete')
        for r in rows:
            i = r['id']
            if (r['mode'] != 0 or r['status_raw'] != 0 or r['torque_raw'] != 1 or
                r['goal_raw'] != goals[i] or abs(r['position_raw']-origin[i]) > 2 or
                abs(r.get('internal_target_raw', r['goal_raw'])-r['goal_raw']) > 2):
                raise RuntimeError('Parked restart native hold/travel changed ID'+str(i))
        if cancelled():
            raise RuntimeError('Parked restart cancelled after read')
        if now()-started > .25:
            raise RuntimeError('Parked restart standstill not confirmed within0.25s')
        stable = stable+1 if all(not r['speed_raw'] and not r['moving_raw'] for r in rows) else 0
        if stable >= 2:
            return rows
        left = .25-(now()-started)
        if left <= 1e-9:
            raise RuntimeError('Parked restart standstill not confirmed within0.25s')
        wait(min(.01, left))


def wrap_start(original, now, wait, cancelled):
    def start(controller, *args, **kwargs):
        goals = _goals.get()
        initial=goals is None and hasattr(controller.bus,'initial_standstill_goals')
        if initial:goals=controller.bus.initial_standstill_goals
        if goals is None:
            return original(controller, *args, **kwargs)
        bus = controller.bus
        read = bus.snapshot
        def snapshot():
            return settle_snapshot(read, controller.origin, goals, now, wait, cancelled)
        bus.snapshot = snapshot
        try:
            return original(controller, *args, **kwargs)
        finally:
            bus.snapshot = read
            if hasattr(bus,'initial_standstill_goals'):delattr(bus,'initial_standstill_goals')
    return start
