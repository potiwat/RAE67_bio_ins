"""Process-only passive recorder; original files and feedback remain unchanged."""
import inspect,textwrap
from pathlib import Path
from .recorder import attach_bus

def patched_worker(source):
 source=textwrap.dedent(source);needle='    try:\n        while not self.stopping.is_set():'
 if source.count(needle)!=1:raise RuntimeError('Runtime anchor changed')
 return source.replace(needle,'    try:\n        self.bus.all_joint_baseline.motor=self\n        while not self.stopping.is_set():')

def install(root,output):
 from bio_inspire.runtime import camera_motor as mod
 original=mod.open_bus
 def open_recorded():
  b=original()
  try:
   recorder=attach_bus(b,output)
   (recorder.out/'provenance.json').write_bytes(Path(__file__).with_name('manifest.json').read_bytes())
   recorder.event('BASELINE_OPEN',observer_only=True,resistance_protection_enabled=False)
   return b
  except BaseException:b.close();raise
 mod.open_bus=open_recorded
 scope=dict(mod.__dict__);exec(compile(patched_worker(inspect.getsource(mod.CameraMotor._run)),str(__file__),'exec'),scope);mod.CameraMotor._run=scope['_run']
 publish=mod.CameraMotor._publish
 def published(m,feedback_ms):
  publish(m,feedback_ms);r=getattr(m.bus,'all_joint_baseline',None)
  if r is not None:
   with m.lock:m._view['all_joint_baseline']=r.status()
 mod.CameraMotor._publish=published
 import play_view
 draw=play_view.draw
 def rendered(cv,image,result,motor=None,start_error=''):
  out=draw(cv,image,result,motor,start_error);s=None if motor is None else motor.snapshot_view().get('all_joint_baseline')
  lines=['BASELINE ID1-5 - RECORD ONLY - NO OBSTRUCTION TEST']
  if s:
   states=list(s['states_done'].items())
   for group in (states[:3],states[3:]):lines.append(' / '.join(k.upper()+(' OK' if v else ' --') for k,v in group))
   lines.append('BASELINE COMPLETE - Q saves' if s['complete'] else 'Need: '+str(s['next_state'])+' | Sleepy fold: '+str(s['fold_phase']))
  else:lines+=['Start/M begins continuous logging','Original motion / PID / torque limits unchanged','Q saves all raw feedback and CSV']
  out=cv.copyMakeBorder(out,0,87,0,0,cv.BORDER_CONSTANT,value=(45,35,20))
  for n,line in enumerate(lines):
   while len(line)>12 and cv.getTextSize(line,cv.FONT_HERSHEY_SIMPLEX,.31,1)[0][0]>out.shape[1]-16:line=line[:-4]+'...'
   cv.putText(out,line,(8,out.shape[0]-69+n*20),cv.FONT_HERSHEY_SIMPLEX,.31,(235,230,180),1)
  return out
 play_view.draw=rendered
