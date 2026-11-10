import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from latest_worker import LatestWorker


class LatestTests(unittest.TestCase):
    def test_busy_detector_drops_old_pending_frames_and_never_blocks_submit(self):
        entered=threading.Event();release=threading.Event();done=threading.Event();seen=[]
        def detect(value):
            seen.append(value)
            if value==1:entered.set();release.wait(1)
            if value==3:done.set()
            return value*10
        worker=LatestWorker(detect)
        try:
            worker.submit(1);self.assertTrue(entered.wait(1))
            worker.submit(2);seq=worker.submit(3)
            self.assertIsNone(worker.latest())
            release.set();self.assertTrue(done.wait(1));worker.close()
            self.assertEqual(seen,[1,3]);self.assertEqual(worker.latest(),(seq,30))
        finally:release.set();worker.close()


if __name__=='__main__':unittest.main()
