"""GPIO27 input only. One debounced press; never actuates motors here."""
from collections import deque
import threading
import time
class ButtonEdge:
    def __init__(self,debounce_s):
        self.debounce_s=debounce_s;self.candidate=None;self.since=0.;self.stable=None;self.armed=False
    def update(self,pressed,now):
        pressed=bool(pressed)
        if pressed!=self.candidate:
            self.candidate=pressed;self.since=now;return False
        if now-self.since<self.debounce_s or self.stable==pressed:return False
        self.stable=pressed
        if not pressed:self.armed=True;return False
        fire=self.armed;self.armed=False;return fire

class BufferedInput:
    """Keep debounced edges while the sole motor owner is busy with UART."""
    def __init__(self,debounce_s):
        self.edge=ButtonEdge(debounce_s);self.pending=deque(maxlen=180)
        self.input_lock=threading.Lock();self.input_stop=threading.Event()
        self.sampler=None;self.sample_error=None;self.last_event_s=None
        self.raw_edges=deque(maxlen=24);self.accepted_times=deque(maxlen=24)
        self.raw_level=None;self.raw_since=None;self.samples=0;self.accepted_presses=0;self.discarded_presses=0
        self.overflow_presses=0;self.last_sample_s=None
        self.stable_edges=deque(maxlen=180);self.stable_sequence=0
    def sample(self,pressed,now):
        with self.input_lock:
            pressed=bool(pressed);self.samples+=1;self.last_sample_s=now
            if self.raw_level is None or pressed!=self.raw_level:
                self.raw_edges.append(dict(time_s=now,pressed=pressed,
                    previous_duration_s=None if self.raw_since is None else now-self.raw_since))
                self.raw_level=pressed;self.raw_since=now
            previous=self.edge.stable
            accepted=self.edge.update(pressed,now)
            if self.edge.stable is not previous:
                self.stable_sequence+=1
                self.stable_edges.append(dict(sequence=self.stable_sequence,time_s=now,pressed=self.edge.stable))
            if accepted:
                if len(self.pending)==self.pending.maxlen:self.overflow_presses+=1
                self.pending.append(self.edge.since);self.accepted_times.append(self.edge.since);self.accepted_presses+=1
    def start_sampling(self,read):
        def run():
            try:
                while not self.input_stop.is_set():
                    stamp=time.clock_gettime(time.CLOCK_BOOTTIME) if hasattr(time,'CLOCK_BOOTTIME') else time.monotonic()
                    self.sample(read(),stamp)
                    self.input_stop.wait(self.edge.debounce_s/3)
            except Exception as error:self.sample_error=error
        self.sampler=threading.Thread(target=run,name='lamp-digital-input',daemon=True);self.sampler.start()
    def poll(self,now):
        if self.sample_error is not None:raise RuntimeError('Digital input sampler: '+str(self.sample_error))
        with self.input_lock:
            if not self.pending:return False
            self.last_event_s=self.pending.popleft();return True
    def drain_events(self,now):
        if self.sample_error is not None:raise RuntimeError('Digital input sampler: '+str(self.sample_error))
        with self.input_lock:
            events=list(self.pending);self.pending.clear()
            if events:self.last_event_s=events[-1]
            return events
    def diagnostics(self):
        with self.input_lock:
            return dict(samples=self.samples,last_sample_s=self.last_sample_s,raw_pressed=self.raw_level,stable_pressed=self.edge.stable,
                        armed=self.edge.armed,accepted_presses=self.accepted_presses,
                        discarded_presses=self.discarded_presses,pending_count=len(self.pending),
                        overflow_presses=self.overflow_presses,
                        stable_sequence=self.stable_sequence,stable_edges=list(self.stable_edges),
                        accepted_source_times=list(self.accepted_times),raw_edges=list(self.raw_edges),
                        debounce_s=self.edge.debounce_s,sampler_error=None if self.sample_error is None else str(self.sample_error))
    def stop_sampling(self):
        self.input_stop.set()
        if self.sampler is not None:self.sampler.join()
        self.discard_pending()
    def discard_pending(self):
        with self.input_lock:
            self.discarded_presses+=len(self.pending);self.pending.clear()

class PhysicalButton(BufferedInput):
    def __init__(self,debounce_s):
        super().__init__(debounce_s)
        from gpiozero import Button
        from gpiozero.pins.lgpio import LGPIOFactory
        self.factory=LGPIOFactory();self.button=None
        try:self.button=Button(27,pull_up=True,bounce_time=None,pin_factory=self.factory)
        except BaseException:self.factory.close();raise
        self.start_sampling(lambda:self.button.is_pressed)
    def close(self):
        self.stop_sampling()
        try:
            if self.button is not None:self.button.close()
        finally:self.factory.close()
