"""Bounded three-process ROS2 replay; run with Python from sourced ROS Jazzy."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

from . import ahm_cpg_compare as model
from . import recorded_input_ros as replay
from .run_ahm_cpg_compare import protected_hashes,json_write


def read_jsonl(path):return [json.loads(line) for line in path.read_text().splitlines() if line]


def run(source,out,fast=False,source_kind='recorded_unknown'):
    source=Path(source).resolve();out=Path(out).resolve()
    if not source.is_relative_to(model.ROOT) or not out.is_relative_to(model.ROOT):raise ValueError('workspace paths required')
    capture=read_jsonl(source);frames=replay.capture_frames(capture)
    before=protected_hashes();out.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'ROS_DOMAIN_ID':'73','PYTHONDONTWRITEBYTECODE':'1'}
    processes=[];logs=[]
    try:
        for role in ('collector','controller','publisher'):
            log=(out/f'{role}.log').open('w');logs.append(log)
            cmd=[sys.executable,'-B','-m','bio_inspire.experiments.recorded_input_ros','--role',role,
                 '--source',str(source),'--out',str(out/f'{role}.jsonl'),'--domain','73']
            if fast:cmd.append('--fast')
            processes.append(subprocess.Popen(cmd,cwd=model.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT))
        deadline=time.monotonic()+85
        graph_saved=False
        while any(p.poll() is None for p in processes) and time.monotonic()<deadline:
            if any(p.poll() not in (None,0) for p in processes):raise RuntimeError('ROS child failed; inspect role logs')
            if not graph_saved and (out/'publisher.jsonl').exists() and (out/'publisher.jsonl').stat().st_size:
                graph=subprocess.run(['ros2','topic','list','-t','--no-daemon'],env=env,capture_output=True,text=True,timeout=6)
                (out/'ros_topics.txt').write_text(graph.stdout+'\n'+graph.stderr,encoding='utf-8');graph_saved=True
            time.sleep(.1)
        if any(p.poll() is None for p in processes):raise TimeoutError('ROS run exceeded85seconds')
        if any(p.returncode!=0 for p in processes):raise RuntimeError('ROS child nonzero exit')
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)
        for log in logs:log.close()
    pub=read_jsonl(out/'publisher.jsonl');control=read_jsonl(out/'controller.jsonl');collected=read_jsonl(out/'collector.jsonl')
    assert len(pub)==len(frames)
    assert control[-1]==collected[-1]==dict(end=True,count=len(frames))
    assert len(control)==len(collected)==len(frames)+1
    for k,(sent,a,b) in enumerate(zip(pub,control[:-1],collected[:-1])):
        assert sent['index']==a['index']==b['index']==k
        assert sent['frame']==a['frame']==b['frame']
        assert a==b
    values=[r['sample']['stimulus'] for r in collected[:-1]]
    for condition in ('C0','C1'):
        expected=model.simulate_samples(condition,values)[:-1]
        assert [r['cpg'][condition] for r in collected[:-1]]==expected
    after=protected_hashes();assert before==after
    summary=dict(status='PASS',scope='recorded logical inputs replayed through ROS2 on WSL; no actuator output',source_kind=source_kind,
                 raw_source=str(source.relative_to(model.ROOT)),raw_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 source_snapshots=len(capture),input_intervals=len(frames),model_dt_s=.05,
                 timing_convention='one recorded acquisition per model update; actual source timestamps retained; CPG model time k*.05 separately',
                 replay_mode='accelerated' if fast else 'wall-paced',input_clock='Pi CLOCK_BOOTTIME relative to capture origin',
                 host_clock='WSL monotonic receipt separately recorded; not synchronized physical latency',
                 paired_input_identical=True,teacher_model_batch_parity=True,stimulus_policy=replay.InputAdapter().stimulus_policy,
                 emotion_states=sorted({r['sample']['emotion'] for r in collected[:-1]}),
                 input_counts=dict(button_true=sum(r['button'] for r in pub_frame(pub)),touch_true=sum(r['touch'] for r in pub_frame(pub))),
                 faults=sum(r['sample']['fault'] for r in collected[:-1]),
                 protected_file_hashes=before,protected_files_unchanged=True,
                 physical_motion_measured=False,servo_command_published=False,rgb_command_published=False)
    json_write(out/'verification.json',summary)
    snapshots=out/'source_snapshot';snapshots.mkdir()
    for p in (Path(__file__),Path(replay.__file__),model.COURSE_PATH,model.CONTRACT_PATH,
              model.ROOT/'bio_inspire/experiments/pi_input_capture.py',model.ROOT/'bio_inspire/experiments/ahm_input_bridge.py',Path(model.__file__)):
        shutil.copyfile(p,snapshots/p.name)
    json_write(out/'manifest.json',dict(files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}))
    return summary


def pub_frame(rows):return [r['frame'] for r in rows]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fast',action='store_true')
    p.add_argument('--source-kind',choices=('real_pi_input','synthetic_smoke','recorded_unknown'),default='recorded_unknown')
    a=p.parse_args()
    print(json.dumps({k:v for k,v in run(a.source,a.out,a.fast,a.source_kind).items() if k!='protected_file_hashes'},ensure_ascii=False))
