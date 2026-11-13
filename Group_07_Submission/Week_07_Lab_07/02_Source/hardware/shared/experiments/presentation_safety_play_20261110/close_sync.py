"""Unwind an explicit close to the existing verified native final hold.

Never retry a Sync, claim an incomplete readback succeeded, reset the blocked
writer, swallow hardware errors, or turn a stop request into play permission.
"""
from sync_position_writer import SyncPositionError
from shared.experiments.central_safety_controller_20261110.runtime import PlayPreempted

CLOSE_CANCELLATIONS=frozenset(('Cancelled before Sync Write',
    'Cancelled during Sync Write preparation',
    'Cancelled after Sync Write; confirmation incomplete'))


def close_aware_sync(original,bus):
    def sync(*args,**kwargs):
        try:return original(*args,**kwargs)
        except SyncPositionError as error:
            session=getattr(bus,'central_feedback',None)
            owner=getattr(session,'owner',None)
            if (owner is None or not owner.stopping.is_set()
                    or error.report.get('error')not in CLOSE_CANCELLATIONS):raise
            session.recorder.event('OPERATOR_CLOSE_DURING_SYNC',
                sync_report=error.report,final_native_hold_required=True,
                incomplete_command_not_accepted=True)
            # The existing worker catches this only inside its control loop.
            # Since stopping is set, it exits straight into its original
            # independent native hold/confirmation/UART-close finally block.
            raise PlayPreempted() from error
    return sync
