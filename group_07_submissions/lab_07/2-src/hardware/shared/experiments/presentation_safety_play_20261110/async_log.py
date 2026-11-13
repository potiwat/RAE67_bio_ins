"""Trial-only bounded disk writer. Never reads/writes UART or motor state."""
import csv,json,queue,threading,time,io
_status_lock=threading.Lock()
_status_owners={}
_status_disk_locks={}


class LogSpool:
    def __init__(self,capacity=8192):
        self.queue=queue.Queue(capacity);self.handles=[];self.error=None
        self.queued=0;self.completed=0;self.dropped=0;self.max_disk_call_s=0.;self.finished=False
        self.status_generation=str(time.time_ns())+'_'+str(id(self));self.status_superseded=0
        self.worker=threading.Thread(target=self._run,name='lamp-log-disk',daemon=True)
        self.worker.start()

    def stream(self,file):
        self.handles.append(file)
        return Stream(self,file)

    def submit(self,target,operation,value=None):
        if self.finished:raise RuntimeError('Log spool is closed')
        # Logging failure must not interrupt a motor hold/stop transaction.
        # Invalidate evidence explicitly; report failure after native close.
        if self.error:self.dropped+=1;return False
        try:self.queue.put_nowait((target,operation,value));self.queued+=1;return True
        except queue.Full:
            self.error='Background log queue full; evidence cannot be retained'
            self.dropped+=1;return False

    def snapshot(self,path,text):self.submit(path,'snapshot',text)
    def status_text(self,path,text):self.submit(path,'status_utf8',text)

    def _run(self):
        closed=set()
        try:
            while True:
                task=self.queue.get()
                if task is None:break
                target,operation,value=task;start=time.monotonic()
                try:
                    if operation=='snapshot':
                        temp=target.with_suffix('.tmp');temp.write_text(value);temp.replace(target)
                    elif operation=='status_utf8':
                        temp=target.with_name(target.name+'.'+self.status_generation+'.tmp')
                        temp.write_text(value,encoding='utf-8',newline='')
                        # The motor owner registers status generations under
                        # _status_lock. Never hold it across ANY disk call.
                        # Serialize disk workers separately so an old delayed
                        # rename cannot overwrite a newer published owner.
                        key=str(target)
                        with _status_lock:
                            disk_lock=_status_disk_locks.setdefault(key,threading.Lock())
                        with disk_lock:
                            with _status_lock:current=_status_owners.get(key)==self.status_generation
                            if current:temp.replace(target)
                            else:temp.unlink(missing_ok=True);self.status_superseded+=1
                    elif operation=='write':target.write(value)
                    elif operation=='flush':target.flush()
                    elif operation=='close':target.close();closed.add(id(target))
                except Exception as error:
                    if self.error is None:self.error=repr(error)
                finally:
                    self.max_disk_call_s=max(self.max_disk_call_s,time.monotonic()-start)
                    self.completed+=1
        finally:
            for target in self.handles:
                if id(target)not in closed:
                    try:target.close()
                    except Exception as error:
                        if self.error is None:self.error=repr(error)

    def finish(self):
        if not self.finished:
            self.finished=True
            try:self.queue.put(None,timeout=5.)
            except queue.Full:raise RuntimeError('Log writer cannot drain during close')
        self.worker.join(5.)
        if self.worker.is_alive():raise RuntimeError('Log disk writer still blocked during close')
        if self.error:raise RuntimeError('Background log writer: '+self.error)

    def status(self):
        return dict(queued=self.queued,completed=self.completed,pending=self.queue.qsize(),
                    dropped=self.dropped,evidence_valid=self.error is None and self.dropped==0,
                    max_disk_call_s=self.max_disk_call_s,error=self.error,
                    writer_alive=self.worker.is_alive(),bounded_capacity=self.queue.maxsize)


class Stream:
    def __init__(self,spool,file):self.spool=spool;self.file=file;self.closed=False
    def write(self,value):
        if self.closed:raise ValueError('Log stream closed')
        self.spool.submit(self.file,'write',value);return len(value)
    def flush(self):
        if not self.closed:self.spool.submit(self.file,'flush')
    def close(self):
        if not self.closed:
            self.spool.submit(self.file,'close');self.closed=True


class StatusPath:
    """Owner builds a frozen JSON/CSV snapshot; disk thread persists it.

    Supports only the two atomic-write forms used by CameraMotor._publish
    and AutomaticFSM.save_csv. It never reads motor state in the disk thread.
    """
    def __init__(self,path,spool):
        self.path=path;self.spool=spool;self.pending=None
        with _status_lock:_status_owners[str(path)]=spool.status_generation
    def with_suffix(self,suffix):return StatusPath(self.path.with_suffix(suffix),self.spool)
    def with_name(self,name):return StatusPath(self.path.with_name(name),self.spool)
    def write_text(self,text,encoding='utf-8',**kw):
        if encoding!='utf-8':raise ValueError('Status snapshots require UTF8')
        self.pending=str(text);return len(text)
    def open(self,mode='w',**kw):
        if mode!='w' or kw.get('encoding','utf-8')!='utf-8':raise ValueError('Status snapshot write only')
        parent=self
        class Buffer(io.StringIO):
            def __exit__(self,kind,value,tb):
                if kind is None:parent.pending=self.getvalue()
                return super().__exit__(kind,value,tb)
        return Buffer(newline='')
    def replace(self,target):
        if not isinstance(target,StatusPath)or target.spool is not self.spool or self.pending is None:
            raise ValueError('Complete same-owner status snapshot required')
        self.spool.status_text(target.path,self.pending);self.pending=None
        return target


def install(session):
    """Capture data/timestamps on owner; defer only persistence, drain on Q."""
    if hasattr(session,'log_spool'):return
    spool=LogSpool();session.log_spool=spool;r=session.recorder
    for name in('raw','events','csvfile'):setattr(r,name,spool.stream(getattr(r,name)))
    r.csv=csv.DictWriter(r.csvfile,fieldnames=r.csv.fieldnames)
    session.shadow=spool.stream(session.shadow)
    original=session.bus.close
    def close():
        try:return original()
        finally:
            try:spool.finish()
            finally:
                (r.out/'ASYNC_LOGGING.json').write_text(json.dumps(spool.status(),indent=2))
    session.bus.close=close
