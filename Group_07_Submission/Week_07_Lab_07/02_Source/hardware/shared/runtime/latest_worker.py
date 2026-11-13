"""One replaceable pending job, one latest result; no unbounded frame queue."""
import threading


class LatestWorker:
    def __init__(self,function):
        self.function=function;self.condition=threading.Condition()
        self.pending=None;self.result=None;self.error=None;self.closed=False;self.sequence=0
        self.thread=threading.Thread(target=self._run,name='latest-vision',daemon=True)
        self.thread.start()
    def submit(self,value):
        with self.condition:
            if self.error is not None:raise RuntimeError('Vision worker failed') from self.error
            if self.closed:raise RuntimeError('Worker closed')
            self.sequence+=1;self.pending=(self.sequence,value);self.condition.notify()
            return self.sequence
    def latest(self):
        with self.condition:
            if self.error is not None:raise RuntimeError('Vision worker failed') from self.error
            return self.result
    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.closed or self.pending is not None)
                if self.closed:return
                sequence,value=self.pending;self.pending=None
            try:result=self.function(value)
            except BaseException as error:
                with self.condition:self.error=error;self.closed=True
                return
            with self.condition:self.result=(sequence,result)
    def close(self):
        with self.condition:self.closed=True;self.pending=None;self.condition.notify()
        self.thread.join(timeout=1)
