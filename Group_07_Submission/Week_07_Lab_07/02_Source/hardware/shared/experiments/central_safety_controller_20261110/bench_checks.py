"""Pure checks for the measurement runner; no device imports or writes."""
from collections import deque
import math,json

def owner_released(m):
 worker=getattr(m,'watchdog',None)
 return worker is None or not worker.is_alive()

def run_ok(r):
 return r.get('status')=='CAPTURE_COMPLETE' and all(r.get(k)is True for k in ('runtime_cleanup_confirmed','ram_restored','pid_unchanged','protected_unchanged')) and not any(r.get(k)for k in ('error','cleanup_error','restoration_error'))

def representative_motion(row,now,direction='negative',minimum=500,axis=4):
 if type(axis)is not int or axis not in(2,3,4,5):raise ValueError('Only statically checked trigger axes2/3/4/5')
 if type(minimum)is not int or minimum not in{2:(100,200),3:(100,200),4:(100,500),5:(100,300)}[axis]:raise ValueError('Unsupported measurement trigger speed')
 if direction not in ('negative','positive'):raise ValueError('Direction must be explicit')
 if not row or row.get('id')!=axis:return False
 stamp=row.get('sampled_monotonic_s');speed=row.get('speed_raw')
 if type(stamp)not in(int,float)or not math.isfinite(stamp)or not 0<=now-stamp<=.1:return False
 if type(speed)is not int or not 0<=speed<=65535:return False
 return row.get('mode')==0 and row.get('torque_raw')==1 and row.get('status_raw')==0 and row.get('moving_raw')==1 and (speed&32767)>=minimum and bool(speed&32768)==(direction=='negative')

class RestorationGate:
 def __init__(self):self.history=deque()
 def update(self,rows,now):
  if (not math.isfinite(now)or len(rows)!=5 or {r.get('id')for r in rows}!=set(range(1,6))
      or any(r.get('mode')!=0 or r.get('torque_raw')!=1 or r.get('status_raw')!=0 or r.get('speed_raw')!=0 or r.get('moving_raw')!=0 for r in rows)):
   self.history.clear();return False
  if self.history and not 0<now-self.history[-1][0]<=.2:self.history.clear()
  self.history.append((now,{r['id']:r['position_raw']for r in rows}))
  while len(self.history)>1 and now-self.history[1][0]>=.2:self.history.popleft()
  return len(self.history)>=3 and now-self.history[0][0]>=.2-1e-9 and all(max(q[i]for _,q in self.history)-min(q[i]for _,q in self.history)<=2 for i in range(1,6))

def atomic_json(path,value):
 tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)

def restoration_connection(open_bus,operation):
 """Never lose a final receipt because restoration transport itself failed."""
 b=None;result={}
 try:
  b=open_bus();result.update(operation(b))
 except BaseException as e:result['restoration_error']=str(e)
 finally:
  if b is not None:
   try:b.close()
   except BaseException as e:result['restoration_error']=(result.get('restoration_error','')+'; restore transport close failed: '+str(e)).lstrip('; ')
 return result
