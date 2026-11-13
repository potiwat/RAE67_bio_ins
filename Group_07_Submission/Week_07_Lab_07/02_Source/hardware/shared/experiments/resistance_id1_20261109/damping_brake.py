"""Explicitly authorized ID1-only damping experiment; never torque-off."""
import time
from write_ack import receive_write_ack

def _write(bus,address,data,ack,clock):
 body=bytes((1,len(data)+3,3,address))+data;p=bytes((255,255))+body+bytes((~sum(body)&255,))
 port=bus.port;port.reset_input_buffer();begin=clock()
 if port.write(p)!=len(p):raise IOError('Partial ID1 damping write')
 port.flush();sent=clock();ack(port,1,p)
 return begin,sent,clock()

def damping_stop(bus,ack=receive_write_ack,clock=time.monotonic):
 b=bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
 if b[0]!=0 or b[7]!=1 or b[8]!=3 or b[32]!=0 or int.from_bytes(b[13:15],'little')!=600 or int.from_bytes(b[15:17],'little')!=160 or not bus.windows[1][0]<=q<=bus.windows[1][1]:
  raise RuntimeError('Damping stop requires original healthy capped ID1')
 # A new position block can re-enable position control on this firmware.
 # Enter damping with its own single-register command, with no goal write.
 begin,sent,acked=_write(bus,40,bytes((2,)),ack,clock)
 check=bus.read(1,33,38)
 if check[7]!=2 or check[8]!=3 or int.from_bytes(check[13:15],'little')!=600:raise RuntimeError('Damping readback mismatch')
 return dict(hold_goal=q,write_begin_s=begin,write_flushed_s=sent,ack_s=acked,readback_s=clock(),register40=[2],pre_feedback=list(b),method='damping2')

def restore_position_hold(bus,ack=receive_write_ack,clock=time.monotonic,pause=time.sleep):
 b=bus.read(1,33,38);q=int.from_bytes(b[23:25],'little')
 if b[0]!=0 or b[7]!=2 or b[32]!=0 or b[25:27]!=bytes((0,0)) or int.from_bytes(b[15:17],'little')!=160 or not bus.windows[1][0]<=q<=bus.windows[1][1]:
  raise RuntimeError('No position re-enable without healthy stationary capped damping')
 # Single-register damping resets the internal target to the encoder on this
 # tested servo. Replace the old far goal with a fresh actual hold before
 # requesting enable. Goal writes may themselves re-enable position control.
 if abs(int.from_bytes(b[34:36],'little')-q)>2:raise RuntimeError('Damping native target not at actual position')
 bus.hold_actual(1);deadline=clock()+1.;good_since=None
 while clock()<deadline:
  b=bus.read(1,33,38);actual=int.from_bytes(b[23:25],'little');internal=int.from_bytes(b[34:36],'little')
  if b[0]!=0 or b[7] not in (1,2) or b[32]!=0 or int.from_bytes(b[15:17],'little')!=160:raise RuntimeError('Damping recovery health drift')
  good=(b[25:27]==bytes((0,0)) and abs(actual-q)<=2 and abs(int.from_bytes(b[9:11],'little')-actual)<=2 and abs(internal-actual)<=2)
  if good:
   if good_since is None:good_since=clock()
   if clock()-good_since>=.1:break
  else:good_since=None
  pause(.02)
 else:raise RuntimeError('Native target not settled in damping; position remains disabled')
 if b[7]==2:bus.armed.add(1);bus.write(1,40,bytes((1,)))
 b=bus.read(1,33,38)
 if b[7]!=1 or b[32]!=0:raise RuntimeError('Position hold enable unconfirmed')
 bus.write(1,41,bytes((3,)))
 if int.from_bytes(b[13:15],'little')!=600:bus.write(1,46,(600).to_bytes(2,'little'))
 b=bus.read(1,33,38)
 if b[8]!=3 or int.from_bytes(b[13:15],'little')!=600:raise RuntimeError('Original run parameters unconfirmed')
 return dict(position_hold_restored=True,goal=q,torque_raw=b[7],acceleration_raw=b[8])

def reset_hold_stop(bus,ack=receive_write_ack,clock=time.monotonic):
 result=damping_stop(bus,ack=ack,clock=clock);q=result['hold_goal'];b=bus.read(1,33,38)
 actual=int.from_bytes(b[23:25],'little')
 if b[0]!=0 or b[7]!=2 or b[32]!=0 or int.from_bytes(b[15:17],'little')!=160 or abs(actual-q)>16 or abs(int.from_bytes(b[34:36],'little')-actual)>2:
  raise RuntimeError('Active brake capture outside authorized bound or damping not reset')
 data=bytes((1,0))+q.to_bytes(2,'little')+bytes((0,0))+(600).to_bytes(2,'little')
 begin,sent,acked=_write(bus,40,data,ack,clock)
 if bus.read(1,33,38)[7:15]!=data:raise RuntimeError('Active brake hold readback mismatch')
 result.update(method='damping_reset_then_active_hold',capture_goal=q,capture_encoder=actual,capture_write_begin_s=begin,capture_write_flushed_s=sent,capture_ack_s=acked,register40_47=list(data))
 return result

def damping_limit(bus,value,ack=receive_write_ack,clock=time.monotonic):
 if type(value) is not int or value not in (160,1000):raise ValueError('Unreviewed damping limit')
 b=bus.read(1,33,38)
 if b[0]!=0 or b[7]!=2 or b[32]!=0 or int.from_bytes(b[15:17],'little') not in (160,1000):raise RuntimeError('Limit change requires confirmed damping, never position drive')
 _write(bus,48,value.to_bytes(2,'little'),ack,clock)
 b=bus.read(1,33,38)
 if b[7]!=2 or int.from_bytes(b[15:17],'little')!=value:raise RuntimeError('Damping limit readback mismatch')
