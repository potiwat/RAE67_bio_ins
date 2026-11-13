"""One controller instance: align only its live owned-probe read envelope."""
def install(adapter):
 c=adapter.m.controller;original=c.feedback_window
 def feedback_window(sid):
  p=adapter.auto_id1;io=getattr(p,'io',None)
  original_bounds=original(sid)
  w=adapter.stop_writer
  if (getattr(adapter,'return_dispatch',False)and adapter.core.phase=='WAIT_CLEARANCE'and
      w is not None and w.verified and w.bus is adapter.m.bus):
   # Normal's constructor clears behavior flags before taking its source
   # snapshot. Carry the verified FIVE-axis hold envelope through that
   # authorized transaction; PoseRoute then installs its own bounded path.
   return tuple(w.windows[sid])
  if (adapter.m.operator_stopped and adapter.core.phase in('STOPPING','LATCHED','CLOSED')and
      sid==getattr(p,'sid',None)and io is not None and io.prepared and
      w is not None and w.verified and w.bus is adapter.m.bus):
   # H/Q must be able to capture an already verified probe hold outside
   # the interrupted emotion's old read window. This grants no play/return
   # command: it preserves only the union of existing supported read bounds.
   lo,hi=w.windows[sid]
   return min(original_bounds[0],lo),max(original_bounds[1],hi)
  if ((adapter.m.operator_stopped or getattr(adapter,'return_dispatch',False))and adapter.core.phase=='WAIT_CLEARANCE'and
      sid==getattr(p,'sid',None) and io is not None and io.prepared):
   if p.active:return tuple(io.window)
   if getattr(io,'restored',False)and w is not None and w.verified:return tuple(w.windows[sid])
  return original_bounds
 c.feedback_window=feedback_window
