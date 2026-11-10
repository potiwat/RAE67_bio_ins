"""Run offline release acceptance and retain compact, reproducible evidence."""
import argparse,hashlib,json,time,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_demo_acceptance as tests

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    root=tests.ROOT;out=args.out.resolve()
    if not out.is_relative_to(root/'bio_inspire/results'):raise ValueError('Evidence must stay in project results')
    out.mkdir(parents=True,exist_ok=False)
    cases=[];original=tests.run_runtime
    def record(*a,**kw):
        r=original(*a,**kw)
        cases.append(dict(duration_s=r['duration_s'],condition=r['condition'],input_sha256=r['input_sha256'],
            behaviors=r['behaviors'],controller_states=r['controller_states'],bounds_violations=r['bounds_violations'],
            forbidden_write_count=len(r['forbidden_writes']),writes_after_stop=len(r['position_writes_after_stop']),
            requested_fault={k:kw[k] for k in ('stop_s','camera_stall','bus_fault_s') if k in kw},
            errors=sorted({v['error'] for v in r['trace'] if v.get('error')})))
        return r
    began=time.perf_counter()
    with patch.object(tests,'run_runtime',record):
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(tests.Tests))
    files=[p for d in ('bio_inspire/runtime','shared/runtime') for p in (root/d).glob('*.py') if not p.name.startswith('test_')]
    files+=[Path(tests.__file__),Path(__file__),tests.PROFILE,root/'bio_inspire/experiments/runtime_integration.py']
    report=dict(physical_robot=False,scope='Actual CameraMotor with virtual sensors and ideal one-tick motor feedback; no dynamics/vision/load proof',
        tests_run=result.testsRun,passed=result.wasSuccessful(),case_count=len(cases),virtual_seconds=sum(c['duration_s'] for c in cases),
        elapsed_pc_seconds=time.perf_counter()-began,cases=cases,
        source_hashes={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print('OFFLINE_ACCEPTANCE',report['passed'],report['case_count'],'cases',report['virtual_seconds'],'virtual seconds')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
