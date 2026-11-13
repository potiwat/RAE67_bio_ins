"""Bio-Inspire gaze intentions only; no servo or FSM side effects."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GazeIntent:
    mode: str
    error_xy: tuple | None = None
    counts_as_activity: bool = False
    motor_output_enabled: bool = False


def gaze_intent(observation, state, fault=False):
    if (fault or state not in ('normal', 'interested', 'happy', 'afraid', 'sleepy')
            or observation.status not in ('ACQUIRED', 'TRACKING', 'WAITING', 'LOST')):
        return GazeIntent('HOLD')
    if observation.status in ('ACQUIRED', 'TRACKING'):
        return GazeIntent('FOLLOW_DROOP' if state == 'sleepy' else 'FOLLOW',
                          observation.error_xy)
    return GazeIntent('DOZE' if state == 'sleepy' else 'SEARCH')
