import tempfile,unittest,json,csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from shared.experiments.all_joint_baseline_20261110.recorder import Recorder,attach_bus,STATES

def block():
 b=bytearray(38);b[7]=1;b[8]=3;b[9:11]=(2019).to_bytes(2,'little');b[13:15]=(600).to_bytes(2,'little');b[15:17]=(1000).to_bytes(2,'little');b[23:25]=(2016).to_bytes(2,'little');b[25:27]=(32768+150).to_bytes(2,'little');b[27:29]=(1024+45).to_bytes(2,'little');b[34:36]=(2018).to_bytes(2,'little');b[36:38]=(7).to_bytes(2,'little');return bytes(b)

class Tests(unittest.TestCase):
 def fixture(self,path):
  c=SimpleNamespace(state='READY',pose_route=None,sleepy_native_fold=None)
  m=SimpleNamespace(behavior_trial='normal',controller=c,automatic_fsm=None,operator_stopped=False)
  r=Recorder(path,clock=lambda:10.);r.motor=m;return r,m
 def test_real_values_units_and_signed_decodes_saved_without_motion(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));r.sample(2,33,38,block(),10.);r.close()
   v=json.loads((r.out/'feedback.jsonl').read_text().splitlines()[0]);self.assertEqual(v['current_raw'],7);self.assertEqual(v['load_signed_raw'],-45);self.assertEqual(v['speed_signed_raw'],-150);self.assertEqual(v['internal_error_ticks'],2)
   with (r.out/'JOINT_FEEDBACK.csv').open(encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f))),1)
 def test_missing_extended_feedback_is_logged_but_not_fabricated_or_counted(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));r.sample(1,33,34,block()[:34],10.);r.close()
   v=json.loads((r.out/'feedback.jsonl').read_text().splitlines()[0]);self.assertIsNone(v['current_raw']);self.assertEqual(r.coverage['normal'][1]['n'],0)
 def test_coverage_requires_all_five_ids_and_all_six_states_no_transition_relabel(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));t=10.
   for state in STATES:
    m.behavior_trial=state;m.controller.sleepy_native_fold={'phase':'breathing'}
    for n in range(36):
     for sid in range(1,6):r.sample(sid,33,38,block(),t+n*.1)
    t+=4.
   self.assertTrue(r.status()['complete']);m.behavior_trial='angry_transition';r.sample(1,33,38,block(),t);r.close()
   self.assertEqual(r.coverage['angry'][1]['n'],36)
 def test_sleepy_folding_and_faults_do_not_satisfy_complete(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));m.behavior_trial='sleepy';m.controller.sleepy_native_fold={'phase':'folding'}
   for n in range(40):r.sample(3,33,38,block(),10.+n*.1)
   self.assertEqual(r.coverage['sleepy'][3]['n'],0)
   m.behavior_trial='normal';m.controller.state='FAULT';r.sample(3,33,38,block(),15.);self.assertEqual(r.coverage['normal'][3]['n'],0);r.close()
 def test_long_gaps_are_not_counted_as_recorded_seconds(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));r.sample(1,33,38,block(),10.);r.sample(1,33,38,block(),20.);self.assertEqual(r.coverage['normal'][1]['seconds'],0.);r.close()
 def test_state_interruption_is_not_counted_as_normal_time(self):
  with tempfile.TemporaryDirectory() as d:
   r,m=self.fixture(Path(d));r.sample(1,33,38,block(),10.);m.behavior_trial='happy';r.sample(1,33,38,block(),10.1);m.behavior_trial='normal';r.sample(1,33,38,block(),10.2)
   self.assertEqual(r.coverage['normal'][1]['seconds'],0.);r.close()
 def test_bus_wrapper_does_not_add_reads_or_change_valid_writes(self):
  with tempfile.TemporaryDirectory() as d:
   b=SimpleNamespace(read=Mock(return_value=block()),write=Mock(),close=Mock());original=b.write
   r=attach_bus(b,Path(d),pid_before={});self.assertEqual(b.read(1,33,38),block());self.assertEqual(r.original_read.call_count,1)
   b.write(1,46,(1000).to_bytes(2,'little'));original.assert_called_once()
   for sid in range(1,6):
    with self.assertRaises(ValueError):b.write(sid,21,b'\10')
   r.close()
