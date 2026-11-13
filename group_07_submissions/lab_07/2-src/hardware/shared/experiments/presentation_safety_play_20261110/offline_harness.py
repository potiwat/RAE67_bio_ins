"""Run the real CameraMotor constructor + worker against a memory UART.

All device access is replaced before initialization. No Pi/network/GUI calls.
"""
import json,sys,threading,time,io,contextlib
from pathlib import Path
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from .offline_plant import Clock,Plant,Input,Distance,Led,PumpEvent
from .led import build_driver
from shared.experiments.central_safety_controller_20261110.runtime import hooks,Adapter
# Load process-local patch targets before patch.dict(sys.modules) below.
# unittest restores that entire mapping, not only the replaced serial key;
# lazy imports otherwise leave stale namespace-package module attributes
# and later cases silently exercise an unpatched duplicate module.
from bio_inspire.runtime import presentation_led,presentation_tempo,state_rhythms,sleepy_trial,angry_approach

ROOT=Path(__file__).resolve().parents[3]
PROFILE=ROOT/'bio_inspire/hardware/presentation_20261107/play_C1_angry_body25_trial.json'
CONFIG=ROOT/'shared/hardware/central_safety_shadow_20261110/replay_1794249877891145300/full_baseline_candidate_config.json'
if not CONFIG.exists():CONFIG=Path(__file__).with_name('config.json')

def run(output,scenario=None,seconds=25.,enabled_ids=(),brake_axis=None,fast_frame=False,dark=False):
 if brake_axis is not None and(type(brake_axis)is not int or brake_axis not in(2,3,4,5)):raise ValueError('Offline candidate brake axes2/3/4/5 only')
 from bio_inspire.runtime import camera_motor as mod
 import physical_distance,physical_button,physical_touch,led_ring
 profile=json.loads(PROFILE.read_text());clock=Clock();plant=Plant(profile,clock);distance=Distance(clock);inputs={};start=clock()
 if brake_axis is not None:
  apply=plant.apply
  def allowed_damping(i,address,data):
   if i==brake_axis and address==40 and data==b'\2':
    plant.ram[i][40]=2;plant.ram[i][67:69]=plant.ram[i][56:58]
    plant.mutations.append(dict(time_s=clock(),id=i,address=40,data_hex='02'));return
   return apply(i,address,data)
  plant.apply=allowed_damping
 output=Path(output);output.mkdir(parents=True,exist_ok=True);profile_path=output/'profile.json';profile_path.write_bytes(PROFILE.read_bytes())
 world=SimpleNamespace(clock=clock,plant=plant,distance=distance,inputs=inputs,motor=None,start=start,observed_states=set(),clearance=False,
  scenario=scenario,cycles=0,max_seconds=seconds,triggered=False)
 def make_input(name,*a):
  x=Input(*a);x.refresh(clock()-1.);x.refresh(clock()-.5);inputs[name]=x;return x
 def pump():
  m=world.motor
  if m is None:return
  world.cycles+=1;world.observed_states.add(m.behavior_trial)
  if scenario:scenario(world)
  for x in inputs.values():x.refresh(clock())
  m.poll();m.apply(dict(observation=dict(status='TRACKING',box=(.3,.2,.3,.5),error_xy=(0.,0.),captured_s=clock(),processed_s=clock(),source_id=world.cycles),intent=dict(mode='FOLLOW',error_xy=(0.,0.))))
  if clock()-start>=seconds:m.stopping.set()
 log=io.StringIO()
 class VirtualLed(build_driver()):
  # Real validator and show_color, with only the physical SPI surface replaced.
  def __init__(self):
   super().__init__();self.pixels=SimpleNamespace(brightness=.03,fill=lambda color:None,show=lambda:None,deinit=lambda:None)
  def close(self):self.pixels=None;self.spi=None
 with ExitStack()as stack:
  stack.enter_context(contextlib.redirect_stdout(log))
  stack.enter_context(patch.dict(sys.modules,{'serial':SimpleNamespace(Serial=plant.serial)}))
  stack.enter_context(patch.object(threading.Thread,'start',lambda self:None))
  stack.enter_context(patch.object(mod.CameraMotor,'now',staticmethod(clock)))
  stack.enter_context(patch.object(time,'monotonic',clock))
  stack.enter_context(patch.object(physical_distance,'PhysicalDistance',lambda:distance))
  stack.enter_context(patch.object(physical_button,'PhysicalButton',lambda *a:make_input('button',*a)))
  stack.enter_context(patch.object(physical_touch,'PhysicalTouch',lambda *a:make_input('touch',*a)))
  from .auto_recovery import DarkLed
  stack.enter_context(patch.object(led_ring,'LedRing',DarkLed if dark else VirtualLed))
  sessions=stack.enter_context(hooks(ROOT,output/'sessions',json.loads(CONFIG.read_text()),clock,enabled_ids=enabled_ids,simulation=True,clearance_proof=lambda event:world.clearance))
  if brake_axis is not None:
   from .damping_id4 import DampingBrake
   hold=Adapter.hold
   def braking(a,epoch):
    a.stop_writer=DampingBrake(a.m.controller.feedback_window(brake_axis),axis=brake_axis,fast_frame=fast_frame)
    return hold(a,epoch)
   stack.enter_context(patch.object(Adapter,'hold',braking))
  m=mod.CameraMotor(profile_path,operator_start=True);world.motor=m
  m.stopping=PumpEvent(clock,pump);pump();m._run()
  adapter=sessions[-1].brake_capture
  result=dict(evidence='OFFLINE_REAL_RUNTIME_MEMORY_UART_NOT_PHYSICAL_TEST',brake_axis=brake_axis,fast_frame=fast_frame,phase=adapter.core.phase,error=adapter.core.error,
   controller_state=m.controller.state,controller_error=m.controller.last_error,events=adapter.core.events,stops=adapter.packet_events,
   reset=getattr(adapter,'reset_snapshot',None),states=sorted(world.observed_states),cleanup_confirmed=m.cleanup_confirmed,
   plant_frames=len(plant.frames),mutations=plant.mutations,final_goals={i:int.from_bytes(a[42:44],'little')for i,a in plant.ram.items()},normal=dict(m.controller.normal),
   elapsed_s=clock()-start,cycles=world.cycles,profile_source=str(PROFILE),source_profile_unchanged=profile_path.read_bytes()==PROFILE.read_bytes())
 (output/'console.log').write_text(log.getvalue(),encoding='utf-8');(output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 return result,world

if __name__=='__main__':
 r,w=run(ROOT/'shared/experiments/central_safety_controller_20261110/results/smoke',seconds=4.)
 print(json.dumps({k:v for k,v in r.items()if k not in('mutations','reset')},indent=2))
