"""Read-only source-profile invariant; temporary probe caps never mean play."""
def require_default_caps(bus):
 caps={i:int.from_bytes(bus.read(i,33,38)[15:17],'little')for i in range(1,6)}
 if any(v!=1000 for v in caps.values()):raise RuntimeError('Trial source torque caps not restored: '+str(caps))
 return caps
