"""Repeatable input scenarios; contact and clearance are synthetic test evidence."""
def contact_in_state(state,axis,after=None):
 def scenario(w):
  t=w.clock()-w.start;m=w.motor;a=m.bus.central_feedback.brake_capture
  if not w.triggered:
   if state=='interested':w.inputs['button'].pressed=2<t<2.4
   if state=='happy':w.inputs['touch'].pressed=2<t<20
   if state=='angry':w.inputs['touch'].pressed=any(s<t<s+.22 for s in (2,2.55,3.1))
   if state=='afraid' and t>2:w.distance.cm=15
   if m.behavior_trial==state and m.controller.state in ('READY','FOLLOWING') and t>2:
    if not hasattr(w,'state_entered'):w.state_entered=w.clock()
    if w.clock()-w.state_entered>.3:
     w.triggered=True;w.trigger_time=w.clock();w.trigger_state=m.behavior_trial;w.plant.contact.add(axis)
  elif w.clock()-w.trigger_time>1.:
   w.plant.contact.clear();w.clearance=True;w.distance.cm=50
   for x in w.inputs.values():x.pressed=False
  if after:after(w)
  if a.core.phase=='NORMAL_PARKED':
   if not hasattr(w,'park_time'):w.park_time=w.clock()
   # Verify a parked Normal does not reactivate an old dance or idle state.
   if w.clock()-w.park_time>1.:m.stopping.set()
 return scenario
