"""Isolated trial banner for the existing simple camera view; no hardware access."""
def status_lines(sessions,motor):
 if motor is None or getattr(motor,'lab07_pair_id',None)!='resistance_id1_R2_pilot':return None
 if motor.operator_stopped or motor.fault_message():return None
 if motor.snapshot_view().get('state') in ('FAULT','STOPPED','NORMAL_STARTUP'):return None
 gate=getattr(motor,'lab07_start_gate',None)
 if gate is not None and not gate.started:
  return ('TRIAL READY - press base button',f'{getattr(gate,"count",0)}/5 presses | H: stop | Q: close')
 p=next((p for owner,p in sessions.attempts if owner is motor),None)
 if p is None or p.started is None:return ('PREPARING MOTOR READBACK','Wait for trial start | H: stop | Q: close')
 if hasattr(p,'phase'):
  phase=p.phase;prefix='R5' if getattr(p,'automatic_retry',False) else 'R4' if hasattr(p,'cap_limit') else 'R3'
  if prefix=='R5':
   if phase=='LATCHED':return ('R5 HOLD - automatic retry unavailable','Q to save | No proof of clear path | H: stop')
   if phase=='STOP_CONFIRM':return ('R5 RESISTANCE_PAUSE - verifying stop','Waiting for stationary encoder | H: stop | Q: save')
   if phase=='PROBE':return (f'R5 SLOW PROBE {p.attempts}/3','Small motion test; may touch foam again | H: stop')
   if phase in ('SETTLE','RESTORE'):return ('R5 PROBE PASSED - verifying hold','Resume after fresh readback | H: stop | Q: save')
  if hasattr(p,'cap_limit') and phase=='LATCHED':return ('RESISTANCE_PAUSE - capped trial','No automatic retry | H: stop | Q: save')
  if phase=='COMPLETE':return (prefix+' COMPLETE - Q to save','Support lamp, then Q to save / close')
  if phase=='LATCHED':return ('RESISTANCE_PAUSE - retries exhausted','3/3 attempts used | H: stop | Q: save')
  if phase=='WAIT':return ('RESISTANCE_PAUSE - holding','Auto probe after wait | H: stop | Q: save')
  if phase=='PROBE':return (f'R3 SLOW PROBE {p.attempts}/3','Testing small movement | H: stop | Q: save')
  if phase=='SETTLE':return ('R3 PROBE PASSED - settling','Waiting for motor to settle | H: stop')
  return (prefix+' SWEEP RUNNING',f'ACTIVE {p.active_s:.1f} / 45.0 s | '+(f'cap {p.cap_limit}/1000' if hasattr(p,'cap_limit') else f'probes {p.attempts}/3'))
 if p.complete:return ('R2 COMPLETE','Support lamp, then Q to save / close')
 if p.guard.state=='RESISTANCE_PAUSE':return ('RESISTANCE_PAUSE','Remove foam, then R | H: stop | Q: save')
 elapsed=p.samples[-1]['elapsed_s'] if p.samples else 0.
 return ('R2 SWEEP RUNNING',f'ACTIVE {elapsed:.1f} / 45.0 s | H: stop | Q: save')

def draw(original,sessions,cv,image,result,motor=None,start_error=''):
 out=original(cv,image,result,motor,start_error)
 lines=None if start_error else status_lines(sessions,motor)
 if lines is None:return out
 width=out.shape[1];cv.rectangle(out,(0,0),(width-1,47),(28,32,38),-1)
 for text,y,scale in ((lines[0],20,.48),(lines[1],40,.38)):
  size=cv.getTextSize(text,cv.FONT_HERSHEY_SIMPLEX,scale,1)[0][0]
  if size>width-20:scale*=max(1,width-20)/size
  cv.putText(out,text,(10,y),cv.FONT_HERSHEY_SIMPLEX,scale,(240,240,240),1,cv.LINE_AA)
 return out
