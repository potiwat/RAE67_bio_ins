"""Read-only Pi SSH session follow, preserving raw bytes for the ROS13 bridge.

No GPIO, UART, motion or LED commands. SSH loss never becomes a fake source row.
"""
import argparse,base64,hashlib,json,math,re,subprocess,time
from pathlib import Path

MAX_FRAME=131072

def decode(frame):
    try:return base64.b64decode(frame['raw_b64'],validate=True)
    except (KeyError,ValueError) as e:raise ValueError('invalid frame encoding') from e

def mirror_stream(stream,out,expected_pair):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    count=0;total=0;last_s=None;metadata=None;ended=False;digest=hashlib.sha256()
    with (out/'trace.jsonl').open('xb') as trace:
        while True:
            line=stream.readline(MAX_FRAME+1)
            if not line:break
            if len(line)>MAX_FRAME or not line.endswith(b'\n'):raise ValueError('oversized/partial transport frame')
            frame=json.loads(line);kind=frame.get('kind')
            if kind=='heartbeat':continue
            if kind=='metadata':
                if metadata is not None or count:raise ValueError('duplicate metadata')
                raw=decode(frame);metadata=json.loads(raw)
                if metadata.get('pair_id')!=expected_pair or metadata.get('origin')!='live_robot':raise ValueError('unexpected source pair/origin')
                (out/'metadata.json').write_bytes(raw)
                continue
            if metadata is None:raise ValueError('metadata required first')
            if kind=='row':
                if frame.get('index')!=count or count>=20000:raise ValueError('noncontiguous source sequence/row limit')
                raw=decode(frame)
                if len(raw)>65536 or not raw.endswith(b'\n'):raise ValueError('oversized/partial source row')
                row=json.loads(raw);stamp=row.get('time_s')
                if type(stamp) not in (int,float) or not math.isfinite(stamp) or last_s is not None and stamp<last_s:raise ValueError('invalid/regressing source clock')
                total+=len(raw)
                if total>128*1024*1024:raise ValueError('source byte limit')
                trace.write(raw);trace.flush();digest.update(raw);count+=1;last_s=stamp
                continue
            if kind=='summary':
                raw=decode(frame);summary=json.loads(raw)
                if summary.get('written')!=count or summary.get('trace_sha256')!=digest.hexdigest():raise ValueError('source summary count/hash mismatch')
                # Expose finalization only after raw bytes are flushed and verified.
                trace.flush();(out/'summary.json').write_bytes(raw);ended=True
                break
            raise ValueError('unknown transport frame')
    if not ended:raise ValueError('SSH stream ended without verified summary')
    return dict(stream_complete=True,byte_identical=True,rows=count,bytes=total,trace_sha256=digest.hexdigest(),
                source_capture_complete=summary.get('capture_complete',summary.get('complete')),
                source_clean_complete=summary.get('complete'),transport='live_read_only_SSH_follow',physical_actuation_via_ros=False)


REMOTE_FOLLOW=r'''
import base64,hashlib,json,sys,time
from pathlib import Path
root=Path('/home/menulis/projects/lelamp/camera_tracking/bio_inspire/results/lab07_sessions')
pair=sys.argv[1];timeout=float(sys.argv[2]);deadline=time.monotonic()+timeout
def send(kind,raw=None,**extra):
    if raw is not None:extra['raw_b64']=base64.b64encode(raw).decode()
    print(json.dumps(dict(kind=kind,**extra),separators=(',',':')),flush=True)
selected=None;last_beat=0.
while selected is None:
    for file in sorted(root.glob('*/metadata.json')):
        try:meta=json.loads(file.read_bytes())
        except (OSError,ValueError):continue
        if meta.get('pair_id')==pair:
            if selected is not None:raise ValueError('ambiguous pair ID')
            selected=file.parent
    if selected is not None:break
    if time.monotonic()>deadline:raise TimeoutError('waiting for matching live session')
    if time.monotonic()-last_beat>=.5:send('heartbeat',stage='waiting_for_Start');last_beat=time.monotonic()
    time.sleep(.05)
send('metadata',(selected/'metadata.json').read_bytes())
count=0;pending=b'';total=0
with (selected/'trace.jsonl').open('rb') as trace:
    while True:
        chunk=trace.readline(65537)
        if chunk:
            pending+=chunk;total+=len(chunk)
            if len(pending)>65536 or total>128*1024*1024 or count>=20000:raise ValueError('bounded source limit')
            if not pending.endswith(b'\n'):continue
            send('row',pending,index=count);count+=1;pending=b''
        elif (selected/'summary.json').exists():
            if pending:raise ValueError('partial final row')
            send('summary',(selected/'summary.json').read_bytes());break
        elif time.monotonic()>deadline:raise TimeoutError('live source not finalized')
        else:
            if time.monotonic()-last_beat>=.5:send('heartbeat',stage='following',rows=count);last_beat=time.monotonic()
            time.sleep(.02)
'''

def run(out,pair,*,socket='/tmp/lelamp-codex-20261106.sock',timeout=680.):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',pair):raise ValueError('invalid pair identifier')
    if not 30<=timeout<=1800:raise ValueError('bounded timeout required')
    out=Path(out)
    if out.exists():raise FileExistsError(out)
    cmd=['ssh','-S',socket,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile=/mnt/c/Users/USER/.ssh/known_hosts','-o','ConnectTimeout=5',
         '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3','menulis@172.20.10.2',
         'python3','-',pair,str(float(timeout))]
    # Pair and timeout are restricted above; remote script itself is sent as stdin.
    err=out.parent/(out.name+'_ssh.stderr.log');err.parent.mkdir(parents=True,exist_ok=True)
    with err.open('xb') as log:
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log)
        try:
            p.stdin.write(REMOTE_FOLLOW.encode());p.stdin.close()
            report=mirror_stream(p.stdout,out,pair)
            code=p.wait(timeout=10)
            if code:raise RuntimeError('remote follower failed: '+str(code))
            (out/'transport_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            return report
        except BaseException as error:
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            if out.exists():(out/'transport_error.json').write_text(json.dumps(dict(status='INCOMPLETE',error=str(error),physical_actuation_via_ros=False)),encoding='utf-8')
            raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--pair-id',required=True)
    parser.add_argument('--timeout',type=float,default=680.)
    args=parser.parse_args();print(json.dumps(run(args.out,args.pair_id,timeout=args.timeout),indent=2))
