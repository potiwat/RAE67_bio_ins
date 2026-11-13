import json,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from .async_log import LogSpool,StatusPath

class Tests(unittest.TestCase):
 def test_slow_atomic_rename_cannot_block_motor_owner_status_registration(self):
  with tempfile.TemporaryDirectory()as folder:
   p=Path(folder)/'status.json';old=LogSpool();new=LogSpool();entered=threading.Event();release=threading.Event();original=Path.replace
   def delayed(path,target):
    if old.status_generation in path.name:
     entered.set();release.wait(1.)
    return original(path,target)
   try:
    with patch.object(Path,'replace',delayed):
     proxy=StatusPath(p,old);tmp=proxy.with_suffix('.tmp');tmp.write_text('old');tmp.replace(proxy)
     self.assertTrue(entered.wait(1.))
     start=time.perf_counter();proxy=StatusPath(p,new);tmp=proxy.with_suffix('.tmp');tmp.write_text('new');tmp.replace(proxy)
     elapsed=time.perf_counter()-start
     release.set();old.finish();new.finish()
     self.assertLess(elapsed,.05,'Disk rename held a lock needed by the motor owner')
   finally:release.set();old.finish();new.finish()
   self.assertEqual(p.read_text(),'new')
 def test_retired_delayed_writer_cannot_overwrite_new_owner_status(self):
  with tempfile.TemporaryDirectory()as folder:
   p=Path(folder)/'status.json';old=LogSpool();new=LogSpool();entered=threading.Event();release=threading.Event();original=Path.write_text
   def delayed(path,text,*args,**kw):
    if text=='old':entered.set();release.wait(2)
    return original(path,text,*args,**kw)
   try:
    with patch.object(Path,'write_text',delayed):
     proxy=StatusPath(p,old);tmp=proxy.with_suffix('.tmp');tmp.write_text('old');tmp.replace(proxy);self.assertTrue(entered.wait(1))
     proxy=StatusPath(p,new);tmp=proxy.with_suffix('.tmp');tmp.write_text('new');tmp.replace(proxy);new.finish()
     release.set();old.finish()
   finally:release.set();old.finish();new.finish()
   self.assertEqual(p.read_text(),'new');self.assertEqual(old.status_superseded,1)
 def test_slow_status_disk_does_not_block_owner_and_flushes_utf8(self):
  with tempfile.TemporaryDirectory()as folder:
   p=Path(folder)/'status.json';spool=LogSpool();proxy=StatusPath(p,spool)
   entered=threading.Event();release=threading.Event();original=Path.write_text;threads=[]
   def delayed(path,text,*args,**kw):
    threads.append(threading.get_ident());entered.set();release.wait(2)
    return original(path,text,*args,**kw)
   try:
    with patch.object(Path,'write_text',delayed):
     start=time.perf_counter();tmp=proxy.with_suffix('.tmp');tmp.write_text(json.dumps({'ไทย':1},ensure_ascii=False),encoding='utf-8');tmp.replace(proxy)
     self.assertLess(time.perf_counter()-start,.05);self.assertTrue(entered.wait(1));self.assertFalse(p.exists())
     release.set();spool.finish()
   finally:release.set();spool.finish()
   self.assertEqual(json.loads(p.read_text(encoding='utf-8')),{'ไทย':1})
   self.assertTrue(all(t!=threading.get_ident()for t in threads));self.assertTrue(spool.status()['evidence_valid'])
 def test_existing_fsm_csv_renders_on_owner_and_persists_frozen_rows(self):
  from types import SimpleNamespace as NS
  from bio_inspire.runtime.automatic_fsm import AutomaticFSM
  with tempfile.TemporaryDirectory()as folder:
   p=Path(folder)/'fsm.csv';spool=LogSpool();proxy=StatusPath(p,spool)
   f=AutomaticFSM();row=dict(kind='button',old_state='normal',new_state='interested');f.fsm=NS(events=[row])
   f.save_csv(proxy,None);row['new_state']='MUTATED_AFTER_RENDER';spool.finish()
   text=p.read_text(encoding='utf-8');self.assertIn('interested',text);self.assertNotIn('MUTATED_AFTER_RENDER',text)
