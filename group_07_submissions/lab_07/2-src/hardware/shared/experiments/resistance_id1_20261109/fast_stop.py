"""ID1-only ACK-driven braking spike; no changes to production transport."""
import time
from write_ack import receive_write_ack

def feedback_without_drain(bus):
 # Reuse the existing checksum/status/length-validated READ parser with a local
 # port facade. No mutation of the bus, global transport, or production files.
 from types import SimpleNamespace
 class Port:
  def __getattr__(self,name):return getattr(bus.port,name)
  def flush(self):pass
 body=bytes((1,4,2,33,38));packet=bytes((255,255))+body+bytes((~sum(body)&255,))
 return type(bus)._read_response(SimpleNamespace(port=Port()),packet,1,38)

def fast_stop(bus,ack=receive_write_ack,clock=time.monotonic,read_feedback=None,pulse=False,brake_acc=0,run_acc=3):
 if type(run_acc)is not int or run_acc not in (3,4):raise ValueError('Unreviewed running acceleration')
 if type(brake_acc) is not int or brake_acc not in (0,254) or brake_acc==254 and not pulse:raise ValueError('Unreviewed brake profile')
 if read_feedback is None:read_feedback=lambda:feedback_without_drain(bus)
 if bus.read(1,18,1)!=bytes((12,)) or bus.read(1,55,1)!=bytes((1,)):raise RuntimeError('Original phase and lock required')
 b=bus.read(1,33,38);q=int.from_bytes(b[23:25],'little');velocity=int.from_bytes(b[25:27],'little');magnitude=velocity&32767
 sign=-1 if velocity&32768 else 1;capture=q-sign*6
 if (b[0]!=0 or b[7]!=1 or b[8]!=run_acc or b[32]!=0 or int.from_bytes(b[13:15],'little')!=600
     or int.from_bytes(b[15:17],'little')!=160 or magnitude>600
     or not bus.windows[1][0]<=q<=bus.windows[1][1] or magnitude>=100 and not bus.windows[1][0]<=capture<=bus.windows[1][1]):
  raise RuntimeError('Fast brake precondition failed: '+repr(dict(expected_run_acc=run_acc,mode=b[0],torque=b[7],acc=b[8],status=b[32],speed_limit=int.from_bytes(b[13:15],'little'),cap=int.from_bytes(b[15:17],'little'),position=q,velocity_raw=velocity)))
 port=bus.port;packets=[];timings=[];reference=clock()
 capture_encoder=q;control=[]
 def send(data):
  body=bytes((1,len(data)+3,3,40))+data;p=bytes((255,255))+body+bytes((~sum(body)&255,))
  port.reset_input_buffer();begin=clock()
  if port.write(p)!=len(p):raise IOError('Partial fast brake write')
  queued=clock()
  # Receiving a valid status ACK proves transmission and acceptance. A blocking
  # tcdrain/flush before reading it adds avoidable host delay on this Pi.
  ack(port,1,p);timings.append(dict(begin_s=begin,queued_s=queued,ack_s=clock()));packets.append(list(p))
 send(bytes((2,)));deadline=clock()+.02
 while True:
  confirmed=read_feedback();actual=int.from_bytes(confirmed[23:25],'little')
  if confirmed[0]!=0 or confirmed[32]!=0 or int.from_bytes(confirmed[15:17],'little')!=160:raise RuntimeError('Fast damping health failure')
  if confirmed[7]==2 and abs(int.from_bytes(confirmed[34:36],'little')-actual)<=2:break
  if clock()>deadline:raise RuntimeError('Damping trajectory reset unconfirmed; no active re-enable')
 timings[-1]['damping_reset_confirmed_s']=clock()
 if magnitude<100:
  return dict(method='low_speed_damping',reason='fresh brake sample below pulse velocity threshold',reference_s=reference,pre_feedback=list(b),packets=packets,timings=timings,run_acc=run_acc,active_pulse_sent=False)
 if pulse:capture_encoder=actual;capture=actual-sign*16
 if abs(actual-capture)>16 or not bus.windows[1][0]<=capture<=bus.windows[1][1]:raise RuntimeError('Fast capture exceeded authorized16tick bound')
 send(bytes((1,brake_acc))+capture.to_bytes(2,'little')+bytes((0,0))+(600).to_bytes(2,'little'))
 if pulse:
  from normal_gaze_motor import decode_state
  end=clock()+.12
  while True:
   block=read_feedback();r=decode_state(1,block);r['cap']=int.from_bytes(block[15:17],'little');control.append(r)
   if r['mode']!=0 or r['torque_raw']!=1 or r['status_raw']!=0 or r['cap']!=160:
    send(bytes((2,)));raise RuntimeError('Pulse feedback health failure')
   velocity=r['speed_raw'];v=-(velocity&32767) if velocity&32768 else velocity
   if sign*v<=50 or clock()>=end:break
  send(bytes((2,)))
  check=read_feedback()
  if check[7]!=2:raise RuntimeError('Pulse damping end unconfirmed')
  return dict(method='velocity_terminated_bounded_pulse',brake_acc=brake_acc,hold_goal=q,capture_goal=capture,capture_encoder=capture_encoder,reference_s=reference,write_flushed_s=None,flush_used=False,packets=packets,timings=timings,pre_feedback=list(b),control_feedback=control)
 check=bus.read(1,33,38)
 if check[7:15]!=bytes((1,0))+capture.to_bytes(2,'little')+bytes((0,0))+(600).to_bytes(2,'little'):
  raise RuntimeError('Fast brake final readback mismatch')
 return dict(method='acked_reset_counter_hold',hold_goal=q,capture_goal=capture,reference_s=reference,write_begin_s=reference,write_flushed_s=None,
             flush_used=False,completion_basis='each WRITE validated by status ACK',packets=packets,timings=timings,pre_feedback=list(b),readback_s=clock())
