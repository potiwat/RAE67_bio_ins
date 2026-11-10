"""Owner-only deferred RAM acceleration reduction. No device/thread of its own."""
class AccelerationRestore:
    def __init__(self):self.floor={};self.pending={};self.stable={};self.destination={};self.tolerance={};self.pinned=set();self.restoring=None
    def pin(self,sid,value,tolerance=22):
        if sid in self.pinned and self.floor.get(sid)==value:return
        self.protect(sid,value,tolerance);self.pinned.add(sid)
    def unpin(self,sid,value):
        self.pinned.discard(sid);self.stable.pop(sid,None);self.destination.pop(sid,None)
        if not self.defer(sid,value):
            self.floor.pop(sid,None);self.pending.pop(sid,None)
    def protect(self,sid,value,tolerance=22):
        # A new slower behavior must retain the prior braking floor until settled.
        if self.floor.get(sid,value)>value:return
        self.tolerance[sid]=tolerance
        self.floor[sid]=value;self.pending.pop(sid,None);self.stable.pop(sid,None)
    def defer(self,sid,value):
        if sid not in self.floor or value>=self.floor[sid]:return False
        if self.pending.get(sid)!=value:self.stable[sid]=0
        self.pending[sid]=value;return True
    def service(self,rows,write):
        for row in rows:
            sid=row['id']
            if sid not in self.pending:continue
            if sid in self.pinned:continue
            goal=row.get('goal_raw')
            healthy=(not row.get('status_raw') and not row.get('mode') and row.get('torque_raw')==1)
            arrived=(healthy and type(goal)is int and not row.get('speed_raw') and not row.get('moving_raw')
                     and abs(row['position_raw']-goal)<=self.tolerance[sid])
            same=self.destination.get(sid)==goal;self.destination[sid]=goal
            self.stable[sid]=(self.stable.get(sid,0)+1 if same else 1) if arrived else 0
            if self.stable[sid]<3:continue
            value=self.pending[sid]
            # Bypass only this deferral; the bus write guard/readback remains active.
            floor=self.floor.pop(sid)
            self.restoring=(sid,value)
            try:write(sid,41,bytes((value,)))
            except Exception:
                self.floor[sid]=floor
                raise
            finally:self.restoring=None
            self.pending.pop(sid);self.stable.pop(sid,None);self.destination.pop(sid,None)
