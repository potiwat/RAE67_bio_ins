"""VL53L1X input only; one I2C worker, no servo access or output actions."""
import threading
import time
import math


def valid_distance_sample(sample,now):
    cm=(sample or {}).get('distance_cm');stamp=(sample or {}).get('received_s')
    return (not (sample or {}).get('error') and type(cm) in (int,float) and math.isfinite(cm) and 0<=cm<=400
            and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<=.12+1e-9)


def distance_input_kind(sample,now):
    """Separate a completed no-return observation from missing input."""
    if valid_distance_sample(sample,now):return 'range'
    sample=sample or {};stamp=sample.get('received_s')
    if (sample.get('error') or type(stamp) not in (int,float) or not math.isfinite(stamp)
            or not 0<=now-stamp<=.12+1e-9 or sample.get('distance_cm') is not None):return 'fault'
    status=sample.get('range_status_raw');state=sample.get('measurement_state')
    if type(status)is not int:return 'fault'
    if state=='no_target' and status==4:return 'no_target'
    if state=='unreliable' and status in (5,6,7,12,13):return 'unreliable'
    return 'fault'


def read_distance_frame(sensor):
    # One result burst binds status and range to the same completed frame.
    # Registers match Adafruit; raw4=MSRCNOTARGET, raw9=RANGECOMPLETE
    # and raw8=MINCLIP in the ST/Pololu status conversion.
    if not hasattr(sensor,'_read_register'):
        cm=sensor.distance  # Compatibility for injected test/input adapters.
        return dict(distance_cm=cm,error=None if cm is not None else 'invalid measurement')
    data=sensor._read_register(0x0089,17)
    if len(data)!=17:raise OSError('Incomplete ToF result frame')
    status=data[0]&0x1f;mm=int.from_bytes(data[13:15],'big')
    state=('range' if status in (8,9) else 'no_target' if status==4 else
           'unreliable' if status in (5,6,7,12,13) else 'fault')
    return dict(distance_cm=mm/10. if state=='range' else None,
                measurement_state=state,range_status_raw=status,raw_range_mm=mm,
                error=None if state!='fault' else ('invalid measurement' if status in (0,18) else f'ToF hardware status {status}'))


def _device():
    import board,busio,adafruit_vl53l1x
    bus=busio.I2C(board.SCL,board.SDA)
    try:return adafruit_vl53l1x.VL53L1X(bus),bus
    except BaseException:bus.deinit();raise


class PhysicalDistance:
    def __init__(self,factory=_device,clock=None):
        self.clock=clock or (lambda:time.clock_gettime(time.CLOCK_BOOTTIME))
        self.factory=factory;self.stop=threading.Event();self.ready=threading.Event()
        self.lock=threading.Lock();self.sample=None
        self.thread=threading.Thread(target=self._run,name='ToF-input-only',daemon=True)
        self.thread.start()

    def latest(self):
        with self.lock:return None if self.sample is None else dict(self.sample)

    def _publish(self,cm,error,sequence,**metadata):
        with self.lock:self.sample=dict(distance_cm=cm,received_s=self.clock(),error=error,sequence=sequence,**metadata)
        self.ready.set()

    def _run(self):
        sensor=bus=None;sequence=0
        try:
            sensor,bus=self.factory();sensor.distance_mode=1;sensor.timing_budget=100
            sensor.start_ranging()
            while not self.stop.is_set():
                if sensor.data_ready:
                    frame=read_distance_frame(sensor);sensor.clear_interrupt();sequence+=1
                    self._publish(frame.pop('distance_cm'),frame.pop('error'),sequence,**frame)
                self.stop.wait(.01)
        except Exception as error:self._publish(None,str(error),sequence)
        finally:
            try:
                if sensor is not None:sensor.stop_ranging()
            finally:
                if bus is not None:bus.deinit()

    def wait_first_sample(self,timeout_s=5.):
        # Existing stand-alone hardware test uses a 5s no-data timeout.
        end=time.monotonic()+timeout_s
        while time.monotonic()<end and not self.stop.is_set():
            sample=self.latest()
            if distance_input_kind(sample,self.clock())!='fault':return
            error=(sample or {}).get('error')
            if error and error!='invalid measurement':raise RuntimeError('ToF: '+error)
            self.stop.wait(.01)
        raise RuntimeError('ToF: no valid initial measurement')

    def require_fresh(self):
        if distance_input_kind(self.latest(),self.clock())=='fault':raise RuntimeError('ToF: disconnected or measurement stream stale')

    def close(self):
        self.stop.set();self.thread.join(timeout=3.)
        if self.thread.is_alive():raise RuntimeError('ToF input worker did not close')
