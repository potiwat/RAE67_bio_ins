"""Explicit free-path loaded-ID2 cap400 test; no automatic-clearance authority."""
import json,time,os,sys
from pathlib import Path

def main(output,root=None,cancelled=lambda:False,staircase=False):
 root=Path(root)if root is not None else Path('/home/menulis/projects/lelamp/camera_tracking');cwd=os.getcwd();os.chdir(root)
 sys.path[:0]=[str(root),str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from normal_gaze_motor import open_bus,decode_state
 from shared.experiments.central_feedback_shadow_20261110.read_response_port import ReadResponsePort
 from shared.experiments.presentation_safety_play_20261110.id2_probe_io import LoadedProbeIO
 from shared.experiments.presentation_safety_play_20261110.native_stop import GroupStop
 out=Path(output);out.mkdir(exist_ok=False,parents=True);profile=json.loads((root/'shared/experiments/presentation_safety_play_20261110/profile.json').read_text())
 report=dict(scope='ID2_LOADED_CAP400_FREE_PATH_ONLY_NO_FOAM',status='STARTING',supports_automatic_clearance=False,pid_tuning=False,contact_tested=False,preload_goal_retained=True)
 report['diagnostic_plan']='two_one_tick_staircases_pm16_300ms'if staircase else'original_pm4_pm16'
 rows=[];captures=[];warnings=[];limits={};source=None;bus=None;io=None;abort_writer=None;aborted=False
 def abort():return cancelled()or(out/'ABORT').exists()
 def snapshot(stage):
  start=time.monotonic();result=[]
  for i in range(1,6):
   raw=bus.read(i,33,38);r=decode_state(i,raw);r.update(time_s=time.monotonic(),stage=stage,torque_limit_raw=int.from_bytes(raw[15:17],'little'),raw33_70_hex=raw.hex());rows.append(r);result.append(r)
  if time.monotonic()-start>.2:raise RuntimeError('ID2 diagnostic all-five feedback deadline')
  return result
 def check_pid():
  actual={str(i):list(bus.read(i,21,3))for i in range(1,6)}
  expected={str(i):[profile['startup_pid_by_id'][str(i)][k]for k in('p','d','i')]for i in range(1,6)}
  if actual!=expected or actual!=report['pid_before']:raise RuntimeError('Source PID differs; no adjustment')
  return actual
 def guard(current,check_io=True,recovery=False):
  for r in current:
   i=r['id'];before=source[i];floor=max(6. if i==2 else 4.5,limits.get(i,dict(native_min_V=5.5))['native_min_V']+.5)
   if r['mode']or r['torque_raw']!=1 or r['status_raw']or r['voltage_V']<floor:raise RuntimeError('Native support/supply guard ID'+str(i))
   if r['voltage_V']<6.:warnings.append(dict(id=i,time_s=r['time_s'],voltage_V=r['voltage_V'],action='NON_DRIVEN_SUPPORTED_WITHIN_NATIVE_MARGIN'))
   if recovery and abort_writer is not None and not(i==2 and io is not None and io.restored):
    # GroupStop may be holding another axis that was correcting its load.
    # Its verified brake profile supersedes the pre-test profile until restore.
    abort_writer.guard_feedback(r)
   elif i!=2 and(any(r[k]!=before[k]for k in('goal_raw','target_speed_raw','acceleration_raw','torque_limit_raw'))or abs(r['internal_target_raw']-before['goal_raw'])>2 or abs(r['position_raw']-before['position_raw'])>3):raise RuntimeError('Frozen-axis support/reference changed ID'+str(i))
  if check_io and io is not None and io.prepared:io.read()
 def settle(label,require_origin=False,initial=False,recovery=False):
  deadline=time.monotonic()+2.
  while time.monotonic()<deadline:
   if not recovery and abort():raise RuntimeError('ID2 diagnostic cancelled')
   a=snapshot(label);guard(a,recovery=recovery);r=next(r for r in a if r['id']==2)
   if require_origin and r['goal_raw']!=io.anchor_goal:io.still=[]
   elif initial and abs(r['position_raw']-io.anchor_q)>3:io.still=[]
   elif io.observe_still(r):return
   time.sleep(.05)
  raise RuntimeError('Loaded temporal static support not established')
 def stop_independently():
  nonlocal abort_writer
  if abort_writer is not None:raise RuntimeError('One abort capture only; no ratcheting')
  # This path intentionally does NOT call io.read(): an accepted write may
  # have lost its readback. Fresh native GroupStop must cancel it first.
  windows={i:(min(r['goal_raw'],r['position_raw'])-22,max(r['goal_raw'],r['position_raw'])+22)for i,r in source.items()};windows[2]=io.feedback_window
  abort_writer=GroupStop(windows,clock=time.monotonic,contact_axis=2);captures.append(abort_writer.audit)
  known_goals={i:r['goal_raw']for i,r in source.items()};known_goals[2]=io.goal
  abort_writer.commit(bus,known_goals,lambda:False)
  deadline=time.monotonic()+2.;still=[]
  while time.monotonic()<deadline:
   a=snapshot('ABORT_CAPTURE_HOLD');guard(a,check_io=False,recovery=True)
   for r in a:abort_writer.guard_feedback(r)
   r=next(r for r in a if r['id']==2)
   if r['speed_raw']or r['moving_raw']or r['internal_target_raw']!=r['goal_raw']:still=[]
   else:
    still.append((r['time_s'],r['position_raw']))
    if len(still)>=4 and still[-1][0]-still[0][0]>=.15-1e-9 and max(q for _,q in still)-min(q for _,q in still)<=2 and abort_writer.restore(True):break
   time.sleep(.05)
  else:raise RuntimeError('Abort native hold not verified')
  io.adopt_stop(abort_writer);settle('ABORT_LOADED_SUPPORT',recovery=True);check_pid();io.restore(original_goal=False)
 try:
  bus=open_bus();bus.port=ReadResponsePort(bus.port);first=snapshot('ENTRY');source={r['id']:r for r in first};report['source']=source
  report['pid_before']={str(i):list(bus.read(i,21,3))for i in range(1,6)};check_pid()
  for i,r in source.items():
   body=bytes((i,4,2,14,2));v=bus._read_response(bytes((255,255))+body+bytes((~sum(body)&255,)),i,2)
   if len(v)!=2 or not 0<v[1]<v[0]:raise RuntimeError('Native voltage bounds invalid')
   limits[i]=dict(native_min_V=v[1]/10,native_max_V=v[0]/10)
   if r['speed_raw']or r['moving_raw']or r['internal_target_raw']!=r['goal_raw']or r['torque_limit_raw']!=1000:raise RuntimeError('All-five known stationary source required')
  guard(first)
  if source[2]['goal_raw']!=2835:raise RuntimeError('Authorized ID2 held goal2835 required')
  if any(abs(source[i]['position_raw']-profile['normal_raw'][str(i)])>profile.get('normal_tolerances_ticks',{}).get(str(i),22)for i in(2,3,4,5)):raise RuntimeError('Normal support posture required for this diagnostic')
  io=LoadedProbeIO(bus,(2815,2861),abort,time.monotonic);io.prepare(entry_source=source[2]);settle('CAP400_SUPPORT',require_origin=True,initial=True);report['cap400_support_verified']=True
  begin=time.monotonic();previous=begin;offsets=(0,4,0,-4,0,16,0,-16,0);hold_s=2.
  if staircase:
   cycle=tuple(range(0,17))+tuple(range(15,-1,-1))+tuple(range(-1,-17,-1))+tuple(range(-15,1))
   offsets=cycle+cycle[1:];hold_s=.3
  report['planned_offsets_ticks']=offsets;report['planned_hold_s']=hold_s
  while True:
   now=time.monotonic()
   if abort()or now-previous>.2:raise RuntimeError('ID2 diagnostic cancelled/control gap')
   previous=now;elapsed=now-begin;stage=min(len(offsets)-1,int(elapsed//hold_s));a=snapshot(stage);guard(a);target=io.anchor_goal+offsets[stage];goal=io.goal+max(-1,min(1,target-io.goal))
   if goal!=io.goal:io.command(goal)
   if elapsed>=len(offsets)*hold_s:break
   time.sleep(.05)
  deadline=time.monotonic()+2.
  while io.goal!=io.anchor_goal:
   if abort()or time.monotonic()>deadline:raise RuntimeError('Original preload goal not reached')
   guard(snapshot('FINAL_ORIGINAL_GOAL'));io.command(io.goal+(1 if io.anchor_goal>io.goal else -1));time.sleep(.05)
  settle('FINAL_ORIGINAL_PRELOAD',require_origin=True);check_pid();io.restore();report['status']='PASS'
 except BaseException as e:
  aborted=True;report.update(status='FAIL',error=repr(e))
  if io is not None and io.prepared and not io.restored:
   try:stop_independently();report['abort_supported_hold_restored']=True
   except BaseException as recovery:report['recovery_error']=repr(recovery)
 finally:
  report['profile_config_restored']=False;report['active_static_hold_verified']=False
  if bus is not None:
   try:
    pids={str(i):list(bus.read(i,21,3))for i in range(1,6)};report['pid_after']=pids;report['pid_unchanged']=pids==report.get('pid_before');final=snapshot('FINAL_READONLY');report['final_native']=final
    report['profile_config_restored']=source is not None and all(all(r[k]==source[r['id']][k]for k in('mode','torque_raw','status_raw','target_speed_raw','acceleration_raw','torque_limit_raw'))for r in final)
    guard(final,check_io=False,recovery=aborted and abort_writer is not None)
    if io is not None and io.restored and not io.uncertain_write and report['pid_unchanged']:
     r=next(r for r in final if r['id']==2);report['active_static_hold_verified']=io._static_ok(r)and(io.abort_adopted if aborted else r['goal_raw']==io.anchor_goal)
    if not report['profile_config_restored']or not report['active_static_hold_verified']:report['status']='FAIL'
   except BaseException as final_error:report.update(status='FAIL',final_proof_error=repr(final_error))
   finally:bus.close()
  report['needs_inspection']=not(report['profile_config_restored']and report['active_static_hold_verified'])
  report['native_captures']=captures;report['writes']=[]if io is None else io.audit;report['supply_warnings']=warnings;report['native_supply_limits']=limits
  (out/'feedback.jsonl').write_text(chr(10).join(json.dumps(r)for r in rows)+chr(10));(out/'RESULT.json').write_text(json.dumps(report,indent=2));os.chdir(cwd)
  print(json.dumps({k:report.get(k)for k in('status','error','profile_config_restored','active_static_hold_verified','pid_unchanged','needs_inspection')}),flush=True)
 return report

if __name__=='__main__':
 import argparse,signal,threading
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--authorized-cap400-id2',action='store_true');p.add_argument('--staircase',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
 if not(a.execute and a.authorized_cap400_id2):raise SystemExit('Explicit scoped loaded ID2 cap400 authorization required')
 stop=threading.Event();signal.signal(signal.SIGTERM,lambda *args:stop.set());signal.signal(signal.SIGINT,lambda *args:stop.set())
 r=main(a.output,cancelled=stop.is_set,staircase=a.staircase);raise SystemExit(0 if r['status']=='PASS'else 1)
