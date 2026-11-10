import errno,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from bio_inspire.experiments.ros13_record import rows

class Scripted:
    def __init__(self,parts):self.parts=list(parts);self.position=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):
        item=self.parts.pop(0) if self.parts else b''
        if isinstance(item,Exception):raise item
        self.position+=len(item);return item
    def readline(self,*args):return self.read(*args)
    def seek(self,n):self.position=n

class Tests(unittest.TestCase):
    def test_live_enodata_is_transient_but_other_io_errors_are_not(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'summary.json').write_text('{}')
            source=Scripted([OSError(errno.ENODATA,'No data available'),b'{"index":0}\n',b''])
            with patch.object(Path,'open',return_value=source):
                self.assertEqual(list(rows(p,True,1.)),[{'index':0}])
            for live,error in ((False,errno.ENODATA),(True,errno.EIO)):
                with patch.object(Path,'open',return_value=Scripted([OSError(error,'test')])):
                    with self.assertRaises(OSError):list(rows(p,live,1.))

    def test_utf8_chunk_boundary_and_partial_final_row(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'summary.json').write_text('{}')
            raw=(json.dumps({'text':'ทดสอบ'},ensure_ascii=False)+'\n').encode()
            source=Scripted([raw[:11],OSError(errno.ENODATA,'waiting'),raw[11:],b''])
            with patch.object(Path,'open',return_value=source):
                self.assertEqual(list(rows(p,True,1.)),[{'text':'ทดสอบ'}])
            with patch.object(Path,'open',return_value=Scripted([b'{"index":0}',b''])):
                with self.assertRaisesRegex(ValueError,'partial'):list(rows(p,True,1.))

    def test_real_finalized_file_replay_and_live_return_identical_rows(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);raw=[{'i':n,'time_s':n*.05} for n in range(20)]
            (p/'trace.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in raw),encoding='utf-8')
            (p/'summary.json').write_text('{}')
            self.assertEqual(list(rows(p,False,1.)),raw)
            self.assertEqual(list(rows(p,True,1.)),raw)

    def test_enodata_retries_are_bounded_by_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            with patch.object(Path,'open',return_value=Scripted([OSError(errno.ENODATA,'waiting')])),patch('bio_inspire.experiments.ros13_record.time.monotonic',side_effect=[0.,2.]):
                with self.assertRaises(TimeoutError):list(rows(p,True,1.))

if __name__=='__main__':unittest.main()
