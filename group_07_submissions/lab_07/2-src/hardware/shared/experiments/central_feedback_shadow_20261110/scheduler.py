"""Cooperative real READ scheduler on the existing sole UART thread."""
import threading,time

class FeedbackScheduler:
 soft_period_s=.080
 hard_gap_s=.200
 def __init__(self,bus,on_feedback,clock=time.monotonic,stopped=lambda:False):
  self.bus=bus;self.on_feedback=on_feedback;self.clock=clock;self.stopped=stopped
  self.original_read=bus.read;self.original_write=bus.write;self.original_sync=bus.sync_positions
  self.active=False;self.depth=0;self.owner_thread=None;self.last={};self.max_gap={i:0. for i in range(1,6)};self.read_counts={i:0 for i in range(1,6)};self.breaches=[];self.extra_reads=0
  bus.read=self.read;bus.write=self.write;bus.sync_positions=self.sync
 def start(self):
  self.owner_thread=threading.get_ident();self.active=True
  # Monitoring epoch begins on the worker, from actual new READs. No cached
  # payloads or modified measurement timestamps are ever returned to callers.
  self.last.clear()
  for sid in range(1,6):
   if self.stopped():break
   self._actual(sid,33,38)
 def _check_thread(self):
  if self.active and threading.get_ident()!=self.owner_thread:raise RuntimeError('Central feedback requires the sole UART worker')
 def _actual(self,sid,address,count):
  self._check_thread();self.depth+=1
  try:
   data=self.original_read(sid,address,count);stamp=self.clock()
   if address==33 and count==38:
    if self.active and not self.stopped():
     previous=self.last.get(sid)
     if previous is not None:
      gap=stamp-previous;self.max_gap[sid]=max(self.max_gap[sid],gap)
      if gap>self.hard_gap_s:self.breaches.append(dict(id=sid,start_s=previous,end_s=stamp,gap_s=gap))
     self.last[sid]=stamp;self.read_counts[sid]+=1
    self.on_feedback(sid,data,stamp)
   return data
  finally:self.depth-=1
 def service(self):
  if not self.active or self.depth or self.stopped():return
  self._check_thread()
  # Earliest-last-read first, bounded burst: avoid write starvation if the
  # device becomes slow. A real long atomic transaction still reports breach.
  for _ in range(5):
   if self.stopped():break
   sid=min(range(1,6),key=lambda i:self.last.get(i,float('-inf')))
   if self.clock()-self.last.get(sid,float('-inf'))<self.soft_period_s:break
   self._actual(sid,33,38);self.extra_reads+=1
 def read(self,sid,address,count):
  self.service();return self._actual(sid,address,count)
 def write(self,sid,address,data):
  self.service();return self.original_write(sid,address,data)
 def sync(self,goals,cancelled):
  self.service();return self.original_sync(goals,cancelled)
 def status(self):
  return dict(soft_target_s=self.soft_period_s,hard_gap_s=self.hard_gap_s,max_gap_s=dict(self.max_gap),read_counts=dict(self.read_counts),gap_breaches=len(self.breaches),extra_reads=self.extra_reads,single_uart_owner=True,feedback_cached=False)
