"""ID1 stop-command qualification, isolated from all presentation runtime."""
import time
from write_ack import receive_write_ack

def atomic_hold(bus,ack=receive_write_ack,clock=time.monotonic,brake_acc=3,brake_speed=600):
 if type(brake_acc) is not int or brake_acc not in (0,3):raise ValueError('Unreviewed brake acceleration')
 if type(brake_speed) is not int or brake_speed not in (1,600) or brake_speed==1 and brake_acc!=0:raise ValueError('Unreviewed brake speed')
 b=bus.read(1,33,38)
 q=int.from_bytes(b[23:25],'little')
 if (len(b)!=38 or b[0]!=0 or b[7]!=1 or b[32]!=0 or b[8]!=3
     or int.from_bytes(b[13:15],'little')!=600 or int.from_bytes(b[15:17],'little')!=160
     or not bus.windows[1][0]<=q<=bus.windows[1][1]):
  raise RuntimeError('Atomic hold requires healthy capped ID1 with original motion parameters')
 data=bytes((brake_acc,))+q.to_bytes(2,'little')+bytes((0,0))+brake_speed.to_bytes(2,'little')
 body=bytes((1,len(data)+3,3,41))+data;packet=bytes((255,255))+body+bytes((~sum(body)&255,))
 port=bus.port;port.reset_input_buffer();before=clock()
 if port.write(packet)!=len(packet):raise IOError('Partial atomic motion write')
 port.flush();sent=clock();ack(port,1,packet);acked=clock()
 check=bus.read(1,33,38)
 if check[8:15]!=data:raise RuntimeError('Atomic hold readback mismatch')
 return dict(hold_goal=q,write_begin_s=before,write_flushed_s=sent,ack_s=acked,readback_s=clock(),register41_47=list(data),pre_feedback=list(b))

def main():
 import json,sys,hashlib,subprocess
 from pathlib import Path
 root=Path(__file__).resolve().parents[3]
 sys.path[:0]=[str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from normal_gaze_motor import open_bus,decode_state
 from shared.experiments.resistance_id1_20261109.capped_trial import CapSession
 assert not subprocess.getoutput('pgrep -af "[r]esistance_id1_20261109/pilot.py|[c]amera_preview.py|[o]pen_play.py|[o]pen_presentation.py"').strip(),'Other owner active'
 prior=json.loads((root/'shared/hardware/resistance_id1_20261109/R2_STAGED.json').read_text())
 hashes=prior['source_hashes']
 assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in hashes.items())
 brake_acc=0 if '--max-brake' in sys.argv else 3
 brake_speed=1 if '--slow-brake' in sys.argv else 600
 reset_hold='--reset-hold' in sys.argv
 damping='--damping' in sys.argv or reset_hold
 characterize='--characterize' in sys.argv
 max_damping='--max-damping' in sys.argv
 phase_zero='--phase-zero' in sys.argv
 fast='--fast-stop' in sys.argv
 pulse='--pulse-stop' in sys.argv
 velocity_zero='--velocity-zero' in sys.argv
 if velocity_zero:raise RuntimeError('Hardware-disqualified: this servo automatically releases torque on mode change; no further velocity-mode trial allowed')
 if velocity_zero and (fast or pulse or damping or phase_zero or characterize or max_damping):raise ValueError('Velocity-zero brake is isolated from other variants')
 if velocity_zero:brake_acc=0
 if pulse:fast=True
 if fast and (phase_zero or damping or characterize or max_damping):raise ValueError('Fast-stop spike is separate')
 if fast:brake_acc=0
 if '--brake254' in sys.argv:
  if not pulse:raise ValueError('ACC254 candidate requires bounded pulse experiment')
  brake_acc=254
 if phase_zero and (damping or characterize or max_damping):raise ValueError('Phase-zero trial is separate from damping variants')
 if phase_zero:brake_acc=0
 if max_damping and (not damping or reset_hold):raise ValueError('Higher limit only for damping mode')
 if characterize and (not damping or reset_hold):raise ValueError('Characterization is damping-only')
 if reset_hold:brake_acc=0
 out=root/'shared/hardware/resistance_id1_20261109'/('R6_BRAKE_'+str(time.time_ns()))
 out.mkdir();b=open_bus();b.motion_speed=600;session=None;phase_session=None;velocity_session=None;raw=[];events=[];result=dict(status='NOT_QUALIFIED',trials=[],directory=str(out),foam_allowed=False,brake_acc=brake_acc,brake_speed=0 if phase_zero or velocity_zero else brake_speed,damping_limit=1000 if max_damping else 160,method='native_velocity_zero' if velocity_zero else 'acked_reset_counter_hold' if fast else 'phase4_speed_zero' if phase_zero else 'damping_reset_then_active_hold' if reset_hold else 'damping2' if damping else 'atomic_position')
 def read():
  block=b.read(1,33,38);r=decode_state(1,block);r['cap']=int.from_bytes(block[15:17],'little')
  raw.append(r)
  if r['mode'] not in ((0,1) if velocity_zero else (0,)) or r['torque_raw'] not in ((1,2) if damping or pulse or velocity_zero else (1,)) or r['status_raw']!=0:raise RuntimeError('Native feedback health failure')
  expected_cap=1000 if max_damping and r['torque_raw']==2 else 160
  if r['cap']!=expected_cap:raise RuntimeError('Unexpected cap outside authorized damping phase')
  if not 1678<=r['position_raw']<=2360:raise RuntimeError('Encoder outside existing yaw window')
  return r
 try:
  b.extended_feedback_diagnostic=True;initial=b.snapshot();result['preflight']=initial
  assert all(r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 and r['moving_raw']==0 and r['speed_raw']==0 for r in initial)
  pid={str(i):list(b.read(i,21,3)) for i in range(1,6)};result['pid_before']=pid
  assert pid=={'1':[8,16,0],'2':[32,20,0],'3':[24,26,0],'4':[5,0,0],'5':[7,3,0]}
  assert initial[0]['acceleration_raw']==3 and initial[0]['target_speed_raw']==600
  b.windows[1]=(1691,2347);session=CapSession(b);session.install()
  if velocity_zero:
   from shared.experiments.resistance_id1_20261109.velocity_stop import VelocityStop
   velocity_session=VelocityStop(b);cap_write=session.write_cap
   def velocity_guarded_cap(value):
    if value==1000 and not velocity_session.audit['restored']:raise RuntimeError('Velocity mode not restored; cap160 retained')
    return cap_write(value)
   session.write_cap=velocity_guarded_cap
   origin=read()['position_raw'];static_stop=velocity_session.stop();static=[]
   for _ in range(8):
    r=read();static.append(r)
    if abs(r['position_raw']-origin)>4 or (r['speed_raw']&32767)>50:
     from shared.experiments.resistance_id1_20261109.damping_brake import _write
     _write(b,40,bytes((2,)),__import__('write_ack').receive_write_ack,time.monotonic)
     raise RuntimeError('Static zero-speed mode check moved; no dynamic trials')
    time.sleep(.02)
   velocity_session.restore();result['velocity_static_check']=dict(stop=static_stop,rows=static)
  if phase_zero:
   from shared.experiments.resistance_id1_20261109.phase_stop import PhaseStop
   phase_session=PhaseStop(b)
   cap_write=session.write_cap
   def guarded_cap(value):
    if value==1000 and not phase_session.audit['restored']:raise RuntimeError('Phase not restored; cap160 retained')
    return cap_write(value)
   session.write_cap=guarded_cap
   phase_session.apply();result['phase_audit']=phase_session.audit
  for index in range(6):
   direction=1 if index%2==0 else -1;target=2347 if direction>0 else 1691
   minimum_speed=(250,250,350,350,400,400)[index]
   if brake_acc in (0,254) or damping:
    # Start each direction at the opposite accepted endpoint: reproduce the full sweep,
    # rather than qualifying only low-speed starts near the middle.
    origin=1691 if direction>0 else 2347;b.write(1,42,origin.to_bytes(2,'little'))
    deadline=time.monotonic()+5.;since=None
    while True:
     r=read()
     good=(r['goal_raw']==r['internal_target_raw']==origin and abs(r['position_raw']-origin)<12 and not r['speed_raw'] and not r['moving_raw'] and r['current_raw']<3 and (r['load_raw']&1023)<32)
     if good:
      if since is None:since=r['sampled_monotonic_s']
      if r['sampled_monotonic_s']-since>=.15:break
     else:since=None
     if time.monotonic()>deadline:raise RuntimeError('Reposition not settled; no new stop trial')
     time.sleep(.02)
   r=read();start=r['position_raw']
   if abs(target-start)<120:raise RuntimeError('Insufficient room for representative stop')
   b.write(1,42,target.to_bytes(2,'little'));events.append(dict(event='native_move',index=index,time_s=time.monotonic(),start=start,target=target))
   deadline=time.monotonic()+3.
   while True:
    r=read()
    if (r['speed_raw']&32767)>=minimum_speed and direction*(r['position_raw']-start)>=80:break
    if time.monotonic()>deadline:raise RuntimeError('Representative speed not reached; stop not qualified')
    time.sleep(.02)
   measured_speed=r['speed_raw']&32767
   if velocity_zero:stop=velocity_session.stop()
   elif fast:
    from shared.experiments.resistance_id1_20261109.fast_stop import fast_stop
    stop=fast_stop(b,pulse=pulse,brake_acc=brake_acc)
   elif phase_zero:stop=phase_session.stop()
   elif damping:
    from shared.experiments.resistance_id1_20261109.damping_brake import damping_stop,restore_position_hold,reset_hold_stop,damping_limit
    if max_damping:session.active=False
    stop=reset_hold_stop(b) if reset_hold else damping_stop(b)
    if max_damping:
     damping_limit(b,1000);stop['higher_damping_applied_s']=time.monotonic()
   else:stop=atomic_hold(b,brake_acc=brake_acc,brake_speed=brake_speed)
   stop.update(event='planned_stop',index=index,direction=direction,measured_speed_raw=measured_speed);events.append(stop)
   anchor=stop.get('reference_s',stop['write_flushed_s'])
   control=stop.get('control_feedback',[]);raw.extend(control)
   stable_since=None;stopped_s=None;stable_position=None;peak=max([abs(r['position_raw']-stop['hold_goal']) for r in control]+[0.]);deadline=anchor+4.;after=[]
   while time.monotonic()<deadline:
    r=read();after.append(r);peak=max(peak,abs(r['position_raw']-stop['hold_goal']))
    if velocity_zero and (peak*360/4096>.7 or time.monotonic()>anchor+.25 and (r['speed_raw']&32767)>50) and r['torque_raw']==1:
     from shared.experiments.resistance_id1_20261109.damping_brake import _write
     _write(b,40,bytes((2,)),__import__('write_ack').receive_write_ack,time.monotonic)
     result['velocity_abort']='Stop envelope or time exceeded; damping fallback'
    stationary=(not r['speed_raw'] and not r['moving_raw'] and r['internal_target_raw']==r['goal_raw']==stop['hold_goal'] and abs(r['position_raw']-stop['hold_goal'])<=(8 if reset_hold else 4))
    if fast:stationary=(not r['speed_raw'] and not r['moving_raw'] and r['internal_target_raw']==r['goal_raw']==stop['capture_goal'] and abs(r['position_raw']-stop['hold_goal'])<=7)
    if damping and not reset_hold or pulse or velocity_zero:
     stationary=not r['speed_raw']
     if stable_position is not None and abs(r['position_raw']-stable_position)>2:stationary=False
    if stationary:
     if stable_since is None:stable_since=r['sampled_monotonic_s'];stable_position=r['position_raw']
     if r['sampled_monotonic_s']-stable_since>=.1 and stopped_s is None:stopped_s=stable_since-anchor
    else:stable_since=None;stopped_s=None;stable_position=None
    if stable_since is not None and r['sampled_monotonic_s']-stable_since>=1.:break
    time.sleep(.02)
   trial=dict(index=index,direction=direction,peak_excursion_ticks=peak,peak_excursion_deg=peak*360/4096,stationary_onset_after_write_s=stopped_s,stop=stop,feedback_samples=len(after),qualified=peak*360/4096<=.7 and stopped_s is not None and stopped_s<=.25)
   result['trials'].append(trial)
   if velocity_zero:velocity_session.restore();events.append(dict(event='position_mode_restored',index=index,time_s=time.monotonic()))
   if damping and not reset_hold or pulse:
    from shared.experiments.resistance_id1_20261109.damping_brake import restore_position_hold
    if max_damping:
     damping_limit(b,160);session.active=True
    recovered=restore_position_hold(b);events.append(dict(event='position_hold_restored',time_s=time.monotonic(),**recovered))
   if brake_acc in (0,254):
    latest=read()
    if latest['moving_raw'] or latest['speed_raw'] or abs(latest['position_raw']-latest['goal_raw'])>4 or latest['internal_target_raw']!=latest['goal_raw']:
     raise RuntimeError('Brake not stationary; ACC3 restore deferred')
    b.write(1,41,bytes((3,)));b.write(1,46,(600).to_bytes(2,'little'));restored=read();assert restored['acceleration_raw']==3 and restored['target_speed_raw']==600
    events.append(dict(event='run_acceleration_restored',index=index,time_s=time.monotonic(),value=3))
   if not trial['qualified'] and not characterize:result['status']='FAIL_STOP_QUALIFICATION';break
  else:result['status']='CHARACTERIZED_NOT_QUALIFIED' if characterize else 'PASS_PLANNED_STOPS_ONLY'
 except BaseException as error:
  result.update(status='ERROR_NOT_QUALIFIED',error=repr(error));raise
 finally:
  try:
   if session is not None:
    try:
     if velocity_session is not None and b.read(1,33,38)[0]==1:
      end=time.monotonic()+3.
      while b.read(1,33,38)[25:27]!=bytes((0,0)) and time.monotonic()<end:time.sleep(.02)
      velocity_session.restore()
     if (damping or fast) and b.read(1,33,38)[7]==2:
      from shared.experiments.resistance_id1_20261109.damping_brake import restore_position_hold
      if max_damping:damping_limit(b,160);session.active=True
      restored=restore_position_hold(b);result['damping_recovered']=restored
     b.hold_actual(1)
     if brake_acc in (0,254):
      deadline=time.monotonic()+3.
      while True:
       last=read()
       if not last['moving_raw'] and not last['speed_raw'] and abs(last['position_raw']-last['goal_raw'])<=4 and last['internal_target_raw']==last['goal_raw']:
        if last['acceleration_raw'] in (0,254):b.write(1,41,bytes((3,)))
        if last['target_speed_raw']!=600:b.write(1,46,(600).to_bytes(2,'little'))
        final=read();result['acc_restored']=final['acceleration_raw']==3;result['speed_restored']=final['target_speed_raw']==600;break
       if time.monotonic()>deadline:result['acc_restored']=False;break
       time.sleep(.02)
    finally:
     try:
      if phase_session is not None:
       try:phase_session.restore()
       except Exception as error:result['phase_restore_error']=repr(error)
       result['phase_audit']=phase_session.audit
      if velocity_session is not None:result['velocity_audit']=velocity_session.audit
     finally:b.close();result['cap_audit']=session.audit
   else:b.close()
  finally:
   result['runtime_changed']=[n for n,h in hashes.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
   (out/'samples.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in raw))
   (out/'events.json').write_text(json.dumps(events,indent=2));(out/'result.json').write_text(json.dumps(result,indent=2))
   print(json.dumps(result),flush=True)

if __name__=='__main__':main()
