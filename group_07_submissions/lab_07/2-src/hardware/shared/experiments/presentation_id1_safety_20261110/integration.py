"""Only this Python process receives the worker hooks; source files stay intact."""
import inspect,textwrap
from pathlib import Path
from .adapter import Adapter,SafetyInterrupt
from .owner import Owner
from shared.experiments.resistance_id1_20261109.capped_trial import CapSession

def forward_key(m,key,original):
 # GUI thread only queues; UART and the V handler stay on the sole worker.
 if key in (ord('v'),ord('V')):
  with m.lock:m.keys.append(ord('v'))
  return
 return original(m,key)

def patched_worker(source):
 source=textwrap.dedent(source)
 init='    try:\n        while not self.stopping.is_set():'
 pre='            obs=None if result is None else result.get(\'observation\')'
 post='            feedback_ms=(time.perf_counter()-t)*1000'
 end="            self._publish(feedback_ms)\n            if getattr(self,'normal_measurement',None) is not None:self.normal_measurement.record"
 if any(source.count(s)!=1 for s in (init,pre,post,end)):raise RuntimeError('Accepted worker changed; safety hook not installed')
 source=source.replace(end,'            self.id1_safety.arm_if_ready()\n'+end)
 source=source.replace(init,'    try:\n        self.id1_safety=_SafetyOwner(self,_SafetyOutput)\n        while not self.stopping.is_set():')
 skip="""            if self.urgent_stop.is_set():
                self._key(ord('h'));self.urgent_stop.clear()
            if self.id1_safety.service():
                self._publish(0.)
                deadline=next_control_deadline(deadline,self.now())
                self.stopping.wait(max(0,deadline-self.now()))
                continue
"""
 source=source.replace(pre,skip+pre)
 skip2="""
            if self.id1_safety.observe():
                self._publish(feedback_ms)
                deadline=next_control_deadline(deadline,self.now())
                self.stopping.wait(max(0,deadline-self.now()))
                continue"""
 source=source.replace(post,post+skip2)
 loop='        while not self.stopping.is_set():\n'
 start=source.index(loop)+len(loop);end=source.index('    except BaseException as error:',start)
 body=source[start:end]
 handler="""            except _SafetyInterrupt as signal:
                self.id1_safety.handle_interrupt(signal)
                self._publish(0.)
                deadline=next_control_deadline(deadline,self.now())
                self.stopping.wait(max(0,deadline-self.now()))
"""
 return source[:start]+'            try:\n'+textwrap.indent(body,'    ')+handler+source[end:]

def install(root,output):
 from bio_inspire.runtime import camera_motor as mod
 original_open=mod.open_bus
 def open_safe():
  b=original_open()
  try:
   # Existing startup checks PID equality; Adapter forbids any correction write.
   session=CapSession(b);session.install();Adapter(b);return b
  except BaseException:b.close();raise
 mod.open_bus=open_safe
 source=patched_worker(inspect.getsource(mod.CameraMotor._run));namespace=dict(mod.__dict__,_SafetyOwner=Owner,_SafetyOutput=Path(output),_SafetyInterrupt=SafetyInterrupt)
 exec(compile(source,str(Path(__file__).with_name('worker_hook.py')),'exec'),namespace)
 mod.CameraMotor._run=namespace['_run']
 old_key=mod.CameraMotor._key
 def key(m,key):
  owner=getattr(m,'id1_safety',None)
  if owner is not None:
   if key in (ord('h'),ord(' ')):owner.manual_stop()
   elif key in (ord('v'),ord('V')):owner.request_test();return
  return old_key(m,key)
 mod.CameraMotor._key=key
 old_public_key=mod.CameraMotor.key
 mod.CameraMotor.key=lambda m,key:forward_key(m,key,old_public_key)
 old_publish=mod.CameraMotor._publish
 def publish(m,feedback_ms):
  old_publish(m,feedback_ms)
  owner=getattr(m,'id1_safety',None)
  if owner is not None:
   with m.lock:m._view['id1_safety']=owner.status()
 mod.CameraMotor._publish=publish
 import play_view
 old_draw=play_view.draw
 def draw(cv,image,result,motor=None,start_error=''):
  out=old_draw(cv,image,result,motor,start_error)
  status=None if motor is None else motor.snapshot_view().get('id1_safety')
  title='EXPERIMENT - ID1 SAFETY'+(' / '+status['phase'] if status else '')
  line=status['reason'] if status else 'Start/M: Normal; V:1000/8 brake test; NO FOAM before log review'
  while len(line)>12 and cv.getTextSize(line,cv.FONT_HERSHEY_SIMPLEX,.34,1)[0][0]>out.shape[1]-16:line=line[:-4]+'...'
  out=cv.copyMakeBorder(out,0,46,0,0,cv.BORDER_CONSTANT,value=(20,45,65))
  cv.putText(out,title,(8,out.shape[0]-27),cv.FONT_HERSHEY_SIMPLEX,.36,(100,220,255),1)
  cv.putText(out,line,(8,out.shape[0]-9),cv.FONT_HERSHEY_SIMPLEX,.34,(240,240,240),1)
  return out
 play_view.draw=draw

