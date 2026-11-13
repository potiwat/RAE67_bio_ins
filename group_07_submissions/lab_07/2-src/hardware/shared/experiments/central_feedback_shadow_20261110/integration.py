import inspect,textwrap,json
from pathlib import Path
from .live import Session

def patched_worker(source):
 source=textwrap.dedent(source);start='    try:\n        while not self.stopping.is_set():'
 end="            self._publish(feedback_ms)\n            if getattr(self,'normal_measurement',None) is not None:self.normal_measurement.record"
 closing="    finally:\n        trial=getattr(self,'automatic_trial',None)"
 if any(source.count(n)!=1 for n in(start,end,closing)):raise RuntimeError('Accepted worker changed')
 source=source.replace(closing,"    finally:\n        self.bus.central_feedback.begin_close()\n        trial=getattr(self,'automatic_trial',None)")
 source=source.replace(start,'    try:\n        self.bus.central_feedback.bind(self)\n        while not self.stopping.is_set():\n            self.bus.central_feedback.scheduler.service()')
 keys='            for key in keys:self._key(key)\n'
 if source.count(keys)!=1:raise RuntimeError('Key dispatch anchor changed')
 source=source.replace(keys,keys+"            brake=getattr(self.bus.central_feedback,'brake_capture',None)\n            if callable(getattr(brake,'service',None)) and brake.requested is not None and brake.phase!='WAIT_V':\n                brake.service(self)\n                self._publish(0.)\n                deadline=next_control_deadline(deadline,self.now())\n                self.stopping.wait(max(0,deadline-self.now()))\n                continue\n")
 return source.replace(end,'            self.bus.central_feedback.scheduler.service()\n'+end)

def install(root,output):
 from .happy_hormone import install as install_happy_hormone
 install_happy_hormone()
 from .cpg_led import install as install_cpg_led
 install_cpg_led()
 from bio_inspire.runtime import camera_motor as mod
 original=mod.open_bus;here=Path(__file__).parent;config=json.loads((here/'config.json').read_text())
 def open_shadow():
  b=original()
  try:
   session=Session(b,output,config);(session.recorder.out/'provenance.json').write_bytes((here/'manifest.json').read_bytes());return b
  except BaseException:b.close();raise
 mod.open_bus=open_shadow
 scope=dict(mod.__dict__);exec(compile(patched_worker(inspect.getsource(mod.CameraMotor._run)),str(__file__),'exec'),scope);mod.CameraMotor._run=scope['_run']
 original_publish=mod.CameraMotor._publish
 def publish(m,ms):
  original_publish(m,ms)
  with m.lock:m._view['central_feedback']=m.bus.central_feedback.status()
 mod.CameraMotor._publish=publish
 import play_view
 original_draw=play_view.draw
 def draw(cv,image,result,motor=None,start_error=''):
  out=original_draw(cv,image,result,motor,start_error);s=None if motor is None else motor.snapshot_view().get('central_feedback');lines=['CENTRAL FEEDBACK ID1-5 / SHADOW ONLY / NO FOAM']
  if s:
   items=list(s['states_done'].items())
   for group in(items[:3],items[3:]):lines.append(' / '.join(k.upper()+(' OK'if v else' --')for k,v in group))
   gaps=s['sampling']['max_gap_s'];lines.append('Max gaps ms: '+' / '.join(str(i)+':'+str(round(gaps.get(i,gaps.get(str(i),0))*1000))for i in range(1,6)))
   lines.append('SAMPLING COMPLETE - Q saves'if s['complete']else'Need: '+str(s['next_state'])+' | Sleepy fold: '+str(s['fold_phase']))
  else:lines+=['Start/M; same original motion profile','Complete six states once; Q saves all feedback','No new resistance stops / PID unchanged','Sampling timeout remains 200 ms']
  out=cv.copyMakeBorder(out,0,105,0,0,cv.BORDER_CONSTANT,value=(35,42,25))
  for n,line in enumerate(lines):
   while len(line)>12 and cv.getTextSize(line,cv.FONT_HERSHEY_SIMPLEX,.31,1)[0][0]>out.shape[1]-16:line=line[:-4]+'...'
   cv.putText(out,line,(8,out.shape[0]-87+n*19),cv.FONT_HERSHEY_SIMPLEX,.31,(220,240,220),1)
  return out
 play_view.draw=draw
