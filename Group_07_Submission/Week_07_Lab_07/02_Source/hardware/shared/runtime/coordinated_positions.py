"""Immediate, opt-in position grouping; never buffer holds or parameters."""

def write_positions(bus,goals,cancelled=None,source='position_group'):
    goals=dict(goals)
    def stopped():
        owner=getattr(bus,'position_group_cancelled',None)
        return bool((cancelled is not None and cancelled()) or (callable(owner) and owner()))
    if not goals or stopped():return None
    enabled=getattr(bus,'presentation_all_state_sync_positions',False) is True
    if enabled and len(goals)>1:
        bus.sync_all_state_position_trial=True
        try:report=bus.sync_positions(goals,stopped)
        finally:bus.sync_all_state_position_trial=False
        bus.last_position_group_report={**report,'source':source}
        return report
    for sid,q in goals.items():
        if stopped():return None
        bus.write(sid,42,q.to_bytes(2,'little'))
    return dict(status='unicast_verified',verified_ids=list(goals),requested_goals=goals)
