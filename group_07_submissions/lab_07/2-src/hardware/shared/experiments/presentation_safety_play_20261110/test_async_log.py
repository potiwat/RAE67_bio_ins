import threading,unittest
from .async_log import LogSpool


class File:
    def __init__(self,block=None,fail=False):
        self.items=[];self.block=block;self.fail=fail;self.closed=False
    def write(self,value):
        if self.block:self.block.wait(2)
        if self.fail:raise OSError('disk error')
        self.items.append(value);return len(value)
    def flush(self):self.items.append('FLUSH')
    def close(self):self.closed=True


class Tests(unittest.TestCase):
    def test_disk_stall_does_not_block_producer_and_finish_preserves_order(self):
        release=threading.Event();file=File(release);spool=LogSpool();stream=spool.stream(file)
        try:
            self.assertEqual(stream.write('a'),1)
            stream.flush();stream.write('b')
            self.assertFalse(release.is_set())
        finally:
            release.set();stream.close();spool.finish()
        self.assertEqual(file.items,['a','FLUSH','b'])
        self.assertTrue(file.closed)
        self.assertFalse(spool.worker.is_alive())

    def test_writer_failure_is_reported_and_resources_still_close(self):
        file=File(fail=True);spool=LogSpool();stream=spool.stream(file);stream.write('a')
        with self.assertRaisesRegex(RuntimeError,'disk error'):spool.finish()
        self.assertTrue(file.closed)
        self.assertFalse(spool.worker.is_alive())

    def test_logging_failure_does_not_interrupt_future_producer_or_motor_path(self):
        file=File(fail=True);spool=LogSpool();stream=spool.stream(file);stream.write('a')
        # Wait for the injected failure in the test, never in the controller.
        for _ in range(100):
            if spool.error:break
            threading.Event().wait(.001)
        self.assertIsNotNone(spool.error)
        self.assertEqual(stream.write('native stop event'),17)
        self.assertEqual(spool.dropped,1)
        self.assertFalse(spool.status()['evidence_valid'])
        with self.assertRaises(RuntimeError):spool.finish()

    def test_snapshot_is_written_on_writer_and_all_streams_drain(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory()as tmp:
            spool=LogSpool();a=File();b=File();sa=spool.stream(a);sb=spool.stream(b)
            sa.write('a');sb.write('b');path=Path(tmp)/'CENTRAL_SAFETY.json'
            spool.snapshot(path,'{"phase":"PLAY"}');spool.finish()
            self.assertEqual(path.read_text(),'{"phase":"PLAY"}')
            self.assertTrue(a.closed and b.closed)

    def test_full_queue_drops_evidence_without_blocking_and_closes_resources(self):
        entered=threading.Event();release=threading.Event()
        class BlockingFile(File):
            def write(self,value):
                entered.set();release.wait(2)
                return super().write(value)
        file=BlockingFile();spool=LogSpool(capacity=1);stream=spool.stream(file)
        try:
            stream.write('a');self.assertTrue(entered.wait(1))
            stream.write('b')
            self.assertEqual(stream.write('dropped'),7)
            self.assertEqual(spool.dropped,1)
            self.assertFalse(spool.status()['evidence_valid'])
        finally:
            release.set()
            with self.assertRaisesRegex(RuntimeError,'queue full'):spool.finish()
        self.assertEqual(file.items,['a','b'])
        self.assertTrue(file.closed);self.assertFalse(spool.worker.is_alive())

    def test_disk_failure_is_reported_only_after_native_close(self):
        import csv
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace as NS
        from .async_log import install
        with TemporaryDirectory()as tmp:
            order=[];raw=File();events=File();csvfile=File()
            recorder=NS(raw=raw,events=events,csvfile=csvfile,
                        csv=csv.DictWriter(csvfile,fieldnames=['value']),out=Path(tmp))
            session=NS(recorder=recorder,shadow=File(),bus=NS(close=lambda:order.append('native closed')))
            install(session);session.log_spool.error='injected disk failure'
            original_finish=session.log_spool.finish
            def finish():
                self.assertEqual(order,['native closed'])
                order.append('log drain');original_finish()
            session.log_spool.finish=finish
            with self.assertRaisesRegex(RuntimeError,'injected disk failure'):session.bus.close()
            self.assertEqual(order,['native closed','log drain'])
            self.assertTrue(raw.closed and events.closed and csvfile.closed)
            self.assertTrue((Path(tmp)/'ASYNC_LOGGING.json').exists())

    def test_real_adapter_native_fallback_survives_failed_event_logging(self):
        from types import SimpleNamespace as NS
        from .integration import adapter_class,consent
        spool=LogSpool();stream=spool.stream(File());spool.error='disk unavailable'
        calls=[]
        def hold(reason,all_axes=False):
            calls.append((reason,all_axes));stream.write('stop acknowledgement');return True
        a=object.__new__(adapter_class(consent()))
        a.auto_id1=NS(active=False,failed=False);a.needs_return_recovery=False;a.stop_writer=None
        a.safety_depth=0;a.clock=lambda:1.
        a.m=NS(controller=NS(hold=hold,state='READY'))
        a.core=NS(record=lambda *args,**kwargs:stream.write('fallback audit'))
        try:
            a.failure_hold('injected early reset failure')
            self.assertEqual(calls,[('injected early reset failure',True)])
            self.assertTrue(a.fallback_report['confirmed']);self.assertEqual(a.m.controller.state,'FAULT')
            self.assertEqual(spool.dropped,2)
        finally:
            with self.assertRaisesRegex(RuntimeError,'disk unavailable'):spool.finish()
