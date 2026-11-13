"""Fresh all-ID telemetry plus advisory-only detector, no new stop authority."""
import json,time,hashlib
from pathlib import Path
from collections import Counter
from normal_gaze_motor import decode_state
from shared.experiments.all_joint_baseline_20261110.recorder import Recorder
from shared.experiments.central_safety_shadow_20261110.detector import CentralDetector
from .scheduler import FeedbackScheduler

class Session:
 def __init__(self,bus,output,config):
  self.bus=bus;self.recorder=Recorder(output);self.detector=CentralDetector(config);self.counts=Counter();self.owner=None;self.closing=False
  self.shadow=(self.recorder.out/'shadow_decisions.jsonl').open('w');self.original_read=bus.read;self.original_close=bus.close
  try:
   self.recorder.pid_before={str(i):list(self.original_read(i,21,3))for i in range(1,6)}
   self.recorder.native_before={str(i):self.original_read(i,33,38).hex()for i in range(1,6)}
  except BaseException as e:self.shadow.close();self.recorder.close(repr(e));raise
  self.scheduler=FeedbackScheduler(bus,self.feedback,stopped=self.stopped)
  original_write=self.scheduler.original_write
  def guarded_write(sid,address,data):
   if address not in (40,41,42,46):raise ValueError('Shadow feedback version forbids PID/EEPROM/cap writes')
   result=original_write(sid,address,data);self.recorder.event('WRITE',id=sid,address=address,data_hex=data.hex());return result
  self.scheduler.original_write=guarded_write
  bus.central_feedback=self;bus.all_joint_baseline=self.recorder;bus.close=self.close
 def stopped(self):return self.owner is not None and (self.owner.stopping.is_set() or self.owner.urgent_stop.is_set())
 def bind(self,motor):
  self.owner=motor;self.recorder.motor=motor
  self.recorder.event('CENTRAL_SAMPLING_STARTED',soft_target_s=.08,hard_gap_s=.20,new_stop_authority=False)
  self.scheduler.start()
 def feedback(self,sid,data,stamp):
  self.recorder.sample(sid,33,38,data,stamp)
  if self.owner is None or self.stopped() or self.closing:return
  r=decode_state(sid,data);row=dict(time_s=stamp,**r,**self.recorder.context(),complete_feedback=True)
  result=self.detector.update(row);self.counts[result['decision']]+=1
  self.shadow.write(json.dumps(dict(**result,behavior_for_report_only=row['behavior']))+'\n')
  # Only recommendations/logging. Never call hold/brake/torque/pose from here.
  if result['decision']in ('WOULD_HOLD_DATA','WOULD_STOP_RESISTANCE'):self.shadow.flush()
 def status(self):return dict(**self.recorder.status(),sampling=self.scheduler.status(),shadow_counts=dict(self.counts),new_joint_stop_enabled=False)
 def begin_close(self):
  if self.closing:return
  self.closing=True;self.scheduler.active=False
  self.recorder.event('CLOSING',note='Retain all raw reads; exclude post-Q cleanup from active-play cadence')
 def close(self):
  self.begin_close();error=None
  try:
   r=self.recorder;r.pid_after={str(i):list(self.original_read(i,21,3))for i in range(1,6)};r.native_after={str(i):self.original_read(i,33,38).hex()for i in range(1,6)}
   if r.pid_after!=r.pid_before:raise RuntimeError('PID changed; no automatic correction')
   if any(r.native_before[i][30:34]!=r.native_after[i][30:34]for i in r.native_before):raise RuntimeError('Torque limit changed externally; no automatic correction')
  except Exception as e:error=repr(e)
  finally:
   try:
    self.shadow.flush();self.shadow.close()
    (self.recorder.out/'sampling_summary.json').write_text(json.dumps(dict(sampling=self.scheduler.status(),breaches=self.scheduler.breaches,shadow_counts=dict(self.counts),new_stop_authority=False,error=error),indent=2))
    self.recorder.close(error)
   finally:self.original_close()
  if error:raise RuntimeError(error)
