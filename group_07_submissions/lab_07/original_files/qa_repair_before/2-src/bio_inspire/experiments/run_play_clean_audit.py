"""Compact reproducible offline evidence; no physical motors or ROS changes."""
import argparse,hashlib,json,time,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_demo_acceptance as baseline
from . import test_play_sweep as sweep


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();root=baseline.ROOT
    if not out.is_relative_to(root/'bio_inspire/results'):raise ValueError('Project results only')
    out.mkdir(parents=True,exist_ok=False)
    profile_hash=hashlib.sha256(baseline.PROFILE.read_bytes()).hexdigest()
    cases=[];original=baseline.run_runtime
    def record(*args,**kwargs):
        result=original(*args,**kwargs)
        tail=[v for v in result['trace'] if v['time_s']>=result['duration_s']-2]
        cases.append(dict(duration_s=result['duration_s'],condition=result['condition'],
                  input_sha256=result['input_sha256'],states=result['behaviors'],
                  controller_states=result['controller_states'],bounds_violations=result['bounds_violations'],
                  forbidden_writes=len(result['forbidden_writes']),
                  final_states=sorted({v['fsm']['state'] for v in tail}),
                  final_behaviors=sorted({v['behavior'] for v in tail})))
        return result
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(baseline.Tests),
                            unittest.defaultTestLoader.loadTestsFromTestCase(sweep.Tests)])
    start=time.perf_counter()
    with patch.object(baseline,'run_runtime',record):result=unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged=hashlib.sha256(baseline.PROFILE.read_bytes()).hexdigest()==profile_hash
    sources=[p for directory in ('bio_inspire/runtime','shared/runtime') for p in (root/directory).glob('*.py') if not p.name.startswith('test_')]
    sources+=[Path(__file__),Path(sweep.__file__),root/'bio_inspire/experiments/runtime_integration.py',baseline.PROFILE]
    report=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,cases=len(cases),
                virtual_seconds=sum(c['duration_s'] for c in cases),elapsed_s=time.perf_counter()-start,
                scope='Actual CameraMotor with synthetic inputs and ideal feedback; not mechanical/vision proof',
                hardware_access=False,accepted_profile_unchanged=unchanged,case_reports=cases,
                source_hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print('PLAY_CLEAN_AUDIT',report['passed'],report['cases'],'cases',report['virtual_seconds'],'virtual seconds')
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
