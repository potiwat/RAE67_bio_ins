import base64,hashlib,io,json,tempfile,unittest
from pathlib import Path
from bio_inspire.experiments.live_session_mirror import mirror_stream

def packet(kind,data=None,**extra):
    if data is not None:extra['raw_b64']=base64.b64encode(data).decode()
    return json.dumps({'kind':kind,**extra}).encode()+b'\n'

def frames(rows=None,summary_overrides=None):
    meta=json.dumps(dict(run_id='test_run',pair_id='live_test',origin='live_robot',condition='C1')).encode()
    rows=rows or [b'{"time_s":1.0}\n',b'{"time_s":1.1}\n']
    summary=dict(written=len(rows),trace_sha256=hashlib.sha256(b''.join(rows)).hexdigest(),complete=True)
    summary.update(summary_overrides or {})
    return packet('metadata',meta)+b''.join(packet('row',r,index=i) for i,r in enumerate(rows))+packet('summary',json.dumps(summary).encode())

class Tests(unittest.TestCase):
    def test_preserves_exact_source_bytes_and_rejects_existing_directory(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'mirror';report=mirror_stream(io.BytesIO(frames()),out,'live_test')
            self.assertEqual((out/'trace.jsonl').read_bytes(),b'{"time_s":1.0}\n{"time_s":1.1}\n')
            self.assertEqual(report['rows'],2);self.assertTrue(report['byte_identical'])
            self.assertTrue(report['stream_complete'])
            with self.assertRaises(FileExistsError):mirror_stream(io.BytesIO(frames()),out,'live_test')

    def test_link_failure_preserves_partial_without_pretending_source_finalized(self):
        raw=frames();raw=raw[:raw.rfind(b'{"kind": "summary"')]
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'mirror'
            with self.assertRaisesRegex(ValueError,'summary'):mirror_stream(io.BytesIO(raw),out,'live_test')
            self.assertTrue((out/'trace.jsonl').exists());self.assertFalse((out/'summary.json').exists())

    def test_hash_and_count_mismatch_cannot_create_final_summary(self):
        for overrides in ({'trace_sha256':'0'*64},{'written':3}):
            with tempfile.TemporaryDirectory() as t:
                out=Path(t)/'mirror'
                with self.assertRaises(ValueError):mirror_stream(io.BytesIO(frames(summary_overrides=overrides)),out,'live_test')
                self.assertFalse((out/'summary.json').exists())

    def test_sequence_gaps_duplicate_metadata_and_wrong_pair_rejected(self):
        wrong=frames().replace(b'"index": 1',b'"index": 7')
        first=frames().splitlines(keepends=True)[0]
        for stream,pair in ((wrong,'live_test'),(first+frames(),'live_test'),(frames(),'other_pair')):
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(ValueError):mirror_stream(io.BytesIO(stream),Path(t)/'mirror',pair)

    def test_partial_lines_non_json_and_source_clock_regression_rejected(self):
        for rows in ([b'{"time_s":1.0}'],[b'not-json\n'],[b'{"time_s":2}\n',b'{"time_s":1}\n']):
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(ValueError):mirror_stream(io.BytesIO(frames(rows=rows)),Path(t)/'mirror','live_test')

    def test_heartbeat_is_not_inserted_as_an_owner_sample(self):
        raw=frames().splitlines(keepends=True)
        stream=raw[0]+packet('heartbeat',remote_elapsed_s=3)+b''.join(raw[1:])
        with tempfile.TemporaryDirectory() as t:
            report=mirror_stream(io.BytesIO(stream),Path(t)/'mirror','live_test')
            self.assertEqual(report['rows'],2)

    def test_live_rows_visible_before_summary_arrives(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'mirror';lines=frames().splitlines(keepends=True)
            class LiveStream:
                def readline(inner,limit):
                    if len(lines)==1:
                        self.assertTrue((out/'metadata.json').exists())
                        self.assertEqual(len((out/'trace.jsonl').read_bytes().splitlines()),2)
                        self.assertFalse((out/'summary.json').exists())
                    return lines.pop(0) if lines else b''
            self.assertTrue(mirror_stream(LiveStream(),out,'live_test')['stream_complete'])

    def test_limits_reject_oversized_frame_and_infinite_source_time(self):
        for data in (b' '*131073+b'\n',frames(rows=[b'{"time_s":NaN}\n'])):
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(ValueError):mirror_stream(io.BytesIO(data),Path(t)/'mirror','live_test')

if __name__=='__main__':unittest.main()
