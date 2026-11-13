"""Observed foam-only ID1 trial with optional recovery. Not safety certified."""
import time,math

class Gate:
 def __init__(self):self.raw=False;self.stable=False;self.since=None;self.count=0;self.started=False
 def update(self,pressed,now):
  if pressed!=self.raw:self.raw=pressed;self.since=now
  if self.since is not None and now-self.since>=.06 and self.stable!=self.raw:
   was=self.stable;self.stable=self.raw
   if was and not self.stable:self.count+=1;self.started=self.count>=5

def checked_row(r,now,braking):
 age=now-r['sampled_monotonic_s']
 if (not math.isfinite(age) or not 0<=age<=.18 or r['id']!=1 or r['mode']!=0 or r['status_raw']!=0
     or r['torque_raw'] not in ((1,2) if braking else (1,)) or r['cap']!=160 or not 1678<=r['position_raw']<=2360):
  raise RuntimeError('Foam trial feedback invalid; not clearance evidence')

def endpoint_arrived(r,target):
 # Recorded stationary endpoint residual: 10 ticks, duty34..38, current1.
 # Keep the existing <12-tick position tolerance and run the contact guard first.
 return (r['goal_raw']==r['internal_target_raw']==target and abs(r['position_raw']-target)<12 and not r['speed_raw'] and not r['moving_raw'] and (r['load_raw']&1023)<64 and r['current_raw']<3)

def first_target(actual):return 1691 if actual>2019 else 2347

def diagnostic_setup(normal,actual):
 if type(actual)is not int or not 1691<=actual<=2331:raise RuntimeError('Insufficient bounded forward diagnostic space')
 return dict(normal=dict(normal),diagnostic_yaw=actual)

def qualification_due(r,active_s,issued):
 return not issued and active_s>=.8 and 1740<=r['position_raw']<=2298 and 100<=r['speed_raw']&32767<=600

class HandoffAssist:
 def __init__(self,target,now):self.target=target;self.start=now;self.stamp=None;self.moving=0;self.q_first=None
 def restore_ready(self,r,now):
  if now<self.start:raise RuntimeError('Handoff clock regression')
  if r['sampled_monotonic_s']==self.stamp:return False
  self.stamp=r['sampled_monotonic_s'];remaining=self.target-r['position_raw'];sign=1 if remaining>0 else -1
  velocity=(r['speed_raw']&32767)*(-1 if r['speed_raw']&32768 else 1)
  if abs(remaining)>64 and sign*velocity>=100:
   if not self.moving:self.q_first=r['position_raw']
   self.moving+=1
  else:self.moving=0;self.q_first=None
  if now-self.start>1. and abs(remaining)>64 and not self.moving:raise RuntimeError('Handoff motion not established; assist not extended')
  return now-self.start>=.15 and self.moving>=2 and sign*(r['position_raw']-self.q_first)>=2

def normal_start_goals(rows,normal):
 if [r['id'] for r in rows]!=list(range(1,6)):raise RuntimeError('Incomplete Normal setup feedback')
 if any(r['mode'] or r['torque_raw']!=1 or r['status_raw'] or r['speed_raw'] or r['moving_raw'] for r in rows):raise RuntimeError('Normal setup requires healthy stationary holds')
 if any(r['goal_raw']!=normal[r['id']] or abs(r['position_raw']-normal[r['id']])>34 for r in rows if r['id'] in (2,3,4)):raise RuntimeError('Body is outside known Normal holds; inspect before moving')
 if not 1691<=rows[0]['position_raw']<=2347 or abs(rows[4]['position_raw']-normal[5])>34:raise RuntimeError('Outside reviewed Normal setup range')
 return {i:normal[i] for i in (1,5) if rows[i-1]['goal_raw']!=normal[i]}

def resume_sweep(bus,target,ack=None,native_probe=False,handoff_acc=3):
 from .damping_brake import _write
 from write_ack import receive_write_ack
 if type(target)is not int or target not in (1691,2347):raise ValueError('Resume target outside sweep endpoints')
 if type(handoff_acc)is not int or handoff_acc not in (3,4) or handoff_acc==4 and not native_probe:raise ValueError('Unreviewed handoff profile')
 b=bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
 probe_speed,probe_acc=(600,3) if native_probe else (17,1)
 if b[0]!=0 or b[7]!=1 or b[8]!=probe_acc or b[32]!=0 or int.from_bytes(b[13:15],'little')!=probe_speed or int.from_bytes(b[15:17],'little')!=160 or not 1691<=q<=2347:raise RuntimeError('Resume requires healthy bounded capped probe')
 # One position-profile WRITE: no intermediate actual-position hold/stop.
 data=bytes((handoff_acc,))+target.to_bytes(2,'little')+bytes((0,0))+(600).to_bytes(2,'little')
 if native_probe and handoff_acc==3:_write(bus,42,target.to_bytes(2,'little'),ack or receive_write_ack,time.monotonic)
 else:_write(bus,41,data,ack or receive_write_ack,time.monotonic)
 b=bus.read(1,33,38)
 if b[8:15]!=data or b[0]!=0 or b[7]!=1 or b[32]!=0 or int.from_bytes(b[15:17],'little')!=160:raise RuntimeError('Resume motion-profile readback mismatch')
 return dict(target=target,acc=handoff_acc,speed=600,actual_hold_sent=False,native_profile_unchanged=native_probe and handoff_acc==3)

def main():
 import sys,json,os,hashlib,subprocess,select,termios,tty,signal
 from pathlib import Path
 root=Path(__file__).resolve().parents[3];sys.path[:0]=[str(root/'shared/runtime'),str(root/'bio_inspire/runtime')]
 from normal_gaze_motor import open_bus,decode_state
 from write_ack import receive_write_ack
 from gpiozero import Button
 from .capped_trial import CapSession,EarlyGuard
 from .capped_retry import RetryCapSession
 from .foam_recovery import Recovery
 auto='--auto-resume' in sys.argv
 native_probe='--fixed-probe-profile' in sys.argv
 if native_probe and not auto:raise ValueError('Fixed probe profile requires explicit automatic trial')
 handoff_acc4='--handoff-acc4' in sys.argv
 if handoff_acc4 and not native_probe:raise ValueError('Handoff assist requires fixed-profile probe')
 probe_rest_s=.5 if '--short-probe-rest' in sys.argv else 2.
 if probe_rest_s==.5 and not auto:raise ValueError('Short rest requires explicit automatic trial')
 assist=None;qualification_assist_braked=False
 qualify='--qualify-fixed-probe' in sys.argv
 if qualify and not native_probe:raise ValueError('Open-path qualification requires fixed probe profile')
 probe_at_current='--probe-at-current' in sys.argv
 if probe_at_current and not qualify:raise ValueError('Current-pose diagnostic requires explicit open-path qualification')
 qualification_issued=False;qualification_resumed=None
 from .fast_stop import fast_stop
 from .damping_brake import _write,restore_position_hold
 assert not subprocess.getoutput('pgrep -af "[r]esistance_id1_20261109/pilot.py|[c]amera_preview.py|[o]pen_play.py|[o]pen_presentation.py|[r]esistance_id1_20261109.brake"').strip(),'Other motor owner active'
 expected=json.loads((root/'shared/hardware/resistance_id1_20261109/R2_STAGED.json').read_text())['source_hashes']
 assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in expected.items()),'Runtime drift'
 out=root/'shared/hardware/resistance_id1_20261109'/('FOAM_'+str(time.time_ns()));out.mkdir()
 summary=dict(trial='foam_auto_recovery' if auto else 'foam_observation_only',automatic_resume=auto,fixed_probe_profile=native_probe,time_criterion_passed=False,human_contact_validated=False,brake_acc=0,cap=160,run_speed=600,run_acc=3,events=[])
 summary['handoff_acc4_trial']=handoff_acc4
 summary['probe_rest_s']=probe_rest_s
 if qualify:summary.update(trial='fixed_profile_open_path_qualification',physical_obstruction_test=False)
 (out/'READY.json').write_text(json.dumps(dict(pid=os.getpid(),directory=str(out),waiting_button_releases=5)))
 trace=(out/'trace.jsonl').open('w');bus=None;cap=None;button=None;terminal=None;phase='WAIT_NORMAL';started=None;last_print=0.;target=2347;settled_since=None;damping_sent=False;recovery=None;active_s=0.;previous=time.monotonic();head_preparing=False
 def event(name,**values):
  row=dict(event=name,time_s=time.monotonic(),**values);summary['events'].append(row);print(name,values,flush=True)
 def row():
  z=bus.read(1,33,38);r=decode_state(1,z);r['cap']=int.from_bytes(z[15:17],'little')
  trace.write(json.dumps(dict(phase=phase,row=r))+'\n');trace.flush();return r
 def damp(reason):
  nonlocal damping_sent
  z=bus.read(1,33,38)
  if z[0]!=0 or z[32]!=0 or z[7] not in (1,2):raise RuntimeError('Cannot confirm known damping mode')
  _write(bus,40,bytes((2,)),receive_write_ack,time.monotonic);damping_sent=True;event('DAMPING_HOLD',reason=reason)
 def interrupted(*args):raise KeyboardInterrupt('Terminal interrupted')
 for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):signal.signal(sig,interrupted)
 try:
  bus=open_bus();bus.motion_speed=600;bus.windows[1]=(1691,2347);bus.extended_feedback_diagnostic=True
  rows=bus.snapshot();summary['preflight']=rows
  assert all(r['mode']==0 and r['torque_raw']==1 and r['status_raw']==0 and not r['speed_raw'] and not r['moving_raw'] for r in rows),'Healthy stationary pose required'
  assert bus.read(1,18,1)==bytes((12,)) and bus.read(1,55,1)==bytes((1,))
  pid={str(i):list(bus.read(i,21,3)) for i in range(1,6)};summary['pid_before']=pid
  assert pid=={'1':[8,16,0],'2':[32,20,0],'3':[24,26,0],'4':[5,0,0],'5':[7,3,0]}
  assert rows[0]['target_speed_raw']==600 and rows[0]['acceleration_raw']==3
  profile=root/'bio_inspire/hardware/normal_motion_20261106/P1_C0.json'
  assert hashlib.sha256(profile.read_bytes()).hexdigest()=='8d2558d8276a4ccb205e6ec4e407c595b1d9913cdc8e73b6dc73f2c949bf0205','Normal profile drift'
  normal={int(i):q for i,q in json.loads(profile.read_text())['normal_raw'].items()}
  if probe_at_current:
   setup=diagnostic_setup(normal,rows[0]['position_raw']);diagnostic_yaw=setup['diagnostic_yaw'];summary.update(trial='fixed_profile_current_pose_probe_diagnostic',diagnostic_yaw=diagnostic_yaw)
  button=Button(27,pull_up=True);gate=Gate();guard=EarlyGuard();last_all_axes=0.
  if sys.stdin.isatty():terminal=termios.tcgetattr(sys.stdin);tty.setcbreak(sys.stdin.fileno())
  event('READY')
  if probe_at_current:print('OPEN PATH / NO FOAM. M returns to NORMAL. Wait NORMAL_READY then button5: move to saved diagnostic yaw, then ONE forward probe <=16 ticks. NO full sweep. Wait PROBE_DIAGNOSTIC_COMPLETE then Q saves. H/SPACE pauses. Emergency available.',flush=True)
  else:
   print('M: prepare Normal first. Wait NORMAL_READY, then BASE BUTTON 5 RELEASES starts sweep. Q saves/closes; H/SPACE latches pause. NO HUMAN CONTACT. '+(f'CONTINUOUS AUTO RECOVERY: short slow probes with {probe_rest_s:g}s rests after stationary confirmation; may touch foam again. Q ends trial.' if auto else 'NO AUTO RESUME.'),flush=True)
   if qualify:print('OPEN PATH ONLY. NO FOAM. '+('Two scripted stops: normal run then ACC4 handoff; ' if handoff_acc4 else 'One scripted stop; ')+'gentle probe/resume; wait FREE_PROFILE_COMPLETE then Q.',flush=True)
  while True:
   now=time.monotonic();key=''
   if phase=='RUN':active_s+=now-previous
   previous=now
   if sys.stdin.isatty() and select.select([sys.stdin],[],[],0)[0]:key=sys.stdin.read(1).lower()
   if key in ('q','\x1b'):event('USER_Q');break
   if key in ('h',' '):
    if phase in ('RUN','RECOVERY','PREPARE','POSITIONING','WAIT_BUTTON'):
     damp('operator pause');phase='PAUSE';recovery=None;assist=None
     if head_preparing:bus.hold_actual(5);head_preparing=False
   if phase=='WAIT_NORMAL':
    if key=='m':
     fresh=bus.snapshot();goals=normal_start_goals(fresh,normal)
     cap=(RetryCapSession if auto else CapSession)(bus);cap.install()
     if 5 in goals:bus.windows[5]=(min(normal[5],fresh[4]['position_raw']),max(normal[5],fresh[4]['position_raw']));head_preparing=True
     for i,q in goals.items():bus.write(i,42,q.to_bytes(2,'little'))
     target=normal[1];phase='PREPARE';prep_started=time.monotonic();settled_since=None;guard=EarlyGuard();event('NORMAL_PREPARING',goals=goals)
   elif phase=='WAIT_BUTTON':
    old=gate.count;gate.update(button.is_pressed,now)
    if gate.count!=old:event('BUTTON_GATE',count=gate.count)
    if gate.started:
     r=row();checked_row(r,time.monotonic(),False);target=first_target(r['position_raw']);guard=EarlyGuard();settled_since=None
     started=time.monotonic()
     if probe_at_current:
      target=diagnostic_yaw;phase='POSITIONING';positioning_started=time.monotonic();bus.write(1,42,target.to_bytes(2,'little'));event('MOVING_TO_DIAGNOSTIC_POSE',target=target)
     else:phase='RUN';event('SWEEP_RUNNING',target=target);bus.write(1,42,target.to_bytes(2,'little'))
   else:
    r=row();checked_row(r,time.monotonic(),phase!='RUN')
    if now-last_all_axes>=1.:
     all_rows=bus.snapshot();trace.write(json.dumps(dict(phase=phase,all_axes=all_rows))+'\n');trace.flush();last_all_axes=now
     if any(x['mode']!=0 or x['status_raw']!=0 or x['torque_raw']!=1 for x in all_rows if x['id']!=1):raise RuntimeError('Held body joint health failure')
    if phase in ('RUN','PREPARE','POSITIONING'):
     result=guard.update(r,time.monotonic())
     if result['state']=='FAULT_HOLD':raise RuntimeError(result['reason'])
     scripted=(qualify and phase=='RUN' and qualification_due(r,active_s,qualification_issued))
     assist_brake=(qualify and assist is not None and not qualification_assist_braked and now-assist.start>=.08 and 150<=r['speed_raw']&32767<=600)
     if result['trip'] or scripted or assist_brake:
      if scripted:qualification_issued=True
      if assist_brake:qualification_assist_braked=True;summary['qualification_assist_brake_issued']=True
      event('SCRIPTED_HANDOFF_ACC4_STOP' if assist_brake else 'SCRIPTED_QUALIFICATION_STOP' if scripted else 'RESISTANCE_DETECTED',row=r)
      if 100<=r['speed_raw']&32767<=600:
       try:stop=fast_stop(bus,pulse=True,brake_acc=0,run_acc=4 if assist else 3);damping_sent=True;event('BRAKE_COMMAND',stop=stop)
       except Exception:
        damp('brake error');raise
      else:damp('low speed or stalled contact')
      if assist_brake:
       qualification_assist_braked=stop['method']=='velocity_terminated_bounded_pulse'
       summary['qualification_assist_brake_method']=stop['method']
      assist=None
      if auto and phase=='RUN':
       recovery=recovery or Recovery(target,native_probe=native_probe,rest_s=probe_rest_s);recovery.target=target;recovery.pause(time.monotonic(),new_contact=True);phase='RECOVERY'
      else:
       phase='PAUSE'
       if head_preparing:bus.hold_actual(5);head_preparing=False
      event('QUALIFICATION_PAUSE' if scripted or assist_brake else 'RESISTANCE_PAUSE',automatic_recovery=phase=='RECOVERY',instruction='Keep path clear for gentle probe.' if scripted or assist_brake else 'Remove foam. Short slow probe may follow.' if phase=='RECOVERY' else 'Remove foam; Q saves.')
     elif phase=='PREPARE':
      head=decode_state(5,bus.read(5,33,38))
      ready=endpoint_arrived(r,normal[1]) and head['goal_raw']==normal[5] and abs(head['position_raw']-normal[5])<=22 and not head['speed_raw'] and not head['moving_raw'] and head['mode']==0 and head['torque_raw']==1 and head['status_raw']==0
      if ready:
       if settled_since is None:settled_since=now
       if now-settled_since>=.15:head_preparing=False;phase='WAIT_BUTTON';gate=Gate();event('NORMAL_READY',instruction='Press and release base button 5 times.');settled_since=None
      else:settled_since=None
      if phase=='PREPARE' and now-prep_started>15.:raise RuntimeError('Normal setup did not settle; sweep not started')
     elif phase=='POSITIONING':
      if endpoint_arrived(r,diagnostic_yaw):
       if settled_since is None:settled_since=now
       if now-settled_since>=.15:
        damp('diagnostic pose reached');qualification_issued=True;target=2347
        recovery=Recovery(target,native_probe=True,rest_s=probe_rest_s);recovery.pause(time.monotonic(),new_contact=True);phase='RECOVERY';settled_since=None
        event('DIAGNOSTIC_POSE_REACHED',requested=diagnostic_yaw,actual=r['position_raw'],maximum_forward_goal=r['position_raw']+16)
      else:settled_since=None
      if phase=='POSITIONING' and now-positioning_started>15.:raise RuntimeError('Diagnostic position not reached; probe not started')
     elif qualify and qualification_resumed is not None and now-qualification_resumed>=2. and (not handoff_acc4 or qualification_assist_braked and assist is None):
      damp('open path qualification complete');phase='COMPLETE';summary['open_path_sequence_complete']=True;event('FREE_PROFILE_COMPLETE',instruction='Support lamp and Q saves.')
     elif qualify and not qualification_issued and active_s>10.:raise RuntimeError('No eligible open-path brake point; qualification incomplete')
     elif not auto and active_s>=45.:
      damp('45s complete');phase='COMPLETE';event('COMPLETE')
     else:
      if r['acceleration_raw']!=(4 if assist else 3) or r['target_speed_raw']!=600:raise RuntimeError('Run parameter drift')
      if assist is not None and (not qualify or qualification_assist_braked) and assist.restore_ready(r,time.monotonic()):
       bus.write(1,41,bytes((3,)));assist=None;event('HANDOFF_ACC3_RESTORED',row=r)
      arrived=endpoint_arrived(r,target)
      if arrived:
       if settled_since is None:settled_since=now
       if now-settled_since>=.15:
        if assist is not None:bus.write(1,41,bytes((3,)));assist=None;event('HANDOFF_ACC3_RESTORED',reason='stationary endpoint')
        target=1691 if target==2347 else 2347;bus.write(1,42,target.to_bytes(2,'little'));settled_since=None;event('REVERSE',target=target)
      else:settled_since=None
    elif phase=='RECOVERY':
     action=recovery.update(r,time.monotonic())
     if action=='PROBE':
      restore_position_hold(bus);damping_sent=False
      if not native_probe:bus.id1_probe_speed(17);bus.write(1,41,bytes((1,)))
      probe_row=row();checked_row(probe_row,time.monotonic(),False)
      if probe_row['acceleration_raw']!=recovery.probe_acc or probe_row['target_speed_raw']!=recovery.probe_speed:raise RuntimeError('Slow probe preparation unconfirmed')
      recovery.issued(time.monotonic(),probe_row['position_raw']);event('SLOW_PROBE',attempt=recovery.attempts,start=recovery.motion_start,target=recovery.probe_target,ramp_s=recovery.duration,acc=recovery.probe_acc,speed=recovery.probe_speed)
     elif action=='PAUSE':
      damp('probe resistance or timeout');event('PROBE_FAILED',attempt=recovery.attempts,reason=recovery.pause_reason,row=r);recovery.pause(time.monotonic())
      if probe_at_current:phase='COMPLETE';summary['probe_diagnostic_passed']=False;event('PROBE_DIAGNOSTIC_COMPLETE',passed=False,instruction='Support lamp and Q saves. No foam.')
     elif action=='RESUME':
      if probe_at_current:
       damp('current-pose diagnostic qualified');phase='COMPLETE';summary['probe_diagnostic_passed']=True;event('PROBE_DIAGNOSTIC_COMPLETE',passed=True,kind=recovery.resume_kind,instruction='Support lamp and Q saves. No full sweep.')
      else:
       acceleration=4 if handoff_acc4 and recovery.resume_kind=='moving' and abs(target-r['position_raw'])>=96 else 3
       handoff=resume_sweep(bus,target,native_probe=native_probe,handoff_acc=acceleration);guard=EarlyGuard();phase='RUN';settled_since=None;previous=time.monotonic()
       assist=HandoffAssist(target,time.monotonic()) if acceleration==4 else None
       event('AUTO_RESUME',attempt=recovery.attempts,kind=recovery.resume_kind,handoff=handoff,clearance_claim=False)
       if qualify:qualification_resumed=time.monotonic()
     elif action=='LATCH':phase='PAUSE';event('RECOVERY_LATCHED',attempts=recovery.attempts)
     if phase=='RECOVERY' and recovery.phase=='PROBING':
      probe_goal=recovery.command_goal(time.monotonic())
      if probe_goal!=r['goal_raw']:bus.write(1,42,probe_goal.to_bytes(2,'little'))
    if now-last_print>=1.:print(phase,recovery.phase if recovery and phase=='RECOVERY' else '', 'active',round(active_s,1),'CONTINUOUS' if auto else '/45s','ID1',r['position_raw'],'Q: save H: latch pause',flush=True);last_print=now
   if qualify and started is not None and phase in ('RUN','RECOVERY') and now-started>45.:
    damp('open-path qualification time limit');phase='COMPLETE';summary['open_path_sequence_complete']=False;event('QUALIFICATION_INCOMPLETE',instruction='No foam. Support lamp and Q saves.')
   time.sleep(.01)
 except BaseException as error:
  import traceback
  summary['error']=repr(error);summary['traceback']=traceback.format_exc();print('TRIAL_STOPPED',repr(error),flush=True)
 finally:
  try:
   if bus is not None and head_preparing:bus.hold_actual(5);head_preparing=False
   if bus is not None and cap is not None:
    try:
     if not damping_sent:damp('close')
     end=time.monotonic()+4.;since=None
     while time.monotonic()<end:
      r=row()
      if not r['speed_raw']:
       if since is None:since=time.monotonic()
       if time.monotonic()-since>=.3:break
      else:since=None
      time.sleep(.02)
     restore_position_hold(bus);event('POSITION_HOLD_RESTORED')
    finally:bus.close();summary['cap_audit']=cap.audit
   elif bus is not None:bus.close()
  except BaseException as error:summary['cleanup_error']=repr(error);print('CLEANUP_UNCONFIRMED',repr(error),flush=True)
  finally:
   if button is not None:button.close()
   if terminal is not None:termios.tcsetattr(sys.stdin,termios.TCSADRAIN,terminal)
   trace.close();summary['runtime_changed']=[n for n,h in expected.items() if hashlib.sha256((root/n).read_bytes()).hexdigest()!=h]
   (out/'summary.json').write_text(json.dumps(summary,indent=2));print('SAVED',str(out),flush=True)
 # Motor bus is closed and cleanup is recorded before waiting for acknowledgement.
 if (summary.get('error') or summary.get('cleanup_error')) and sys.stdin.isatty():
  print('STOPPED. Data saved; no automatic restart. Read the reason above. Q closes this window.',flush=True)
  try:
   tty.setcbreak(sys.stdin.fileno())
   while True:
    if select.select([sys.stdin],[],[],.2)[0]:
     key=sys.stdin.read(1).lower()
     if not key or key in ('q','\x1b'):break
  except (KeyboardInterrupt,OSError):pass
  finally:
   if terminal is not None:
    try:termios.tcsetattr(sys.stdin,termios.TCSADRAIN,terminal)
    except OSError:pass

if __name__=='__main__':main()
