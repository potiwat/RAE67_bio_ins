"""Skip redundant host tcdrain only for validated READ request packets.

The retained parser must still receive and validate the servo reply. Motor WRITE
and SyncWrite flush behavior is unchanged. One owner, no cache, no timeout edits.
"""
class ReadResponsePort:
 def __init__(self,port):self.port=port;self.last_read=False;self.read_drains_skipped=0
 def __getattr__(self,name):return getattr(self.port,name)
 def write(self,data):
  p=bytes(data)
  self.last_read=(len(p)==8 and p[:2]==b'\xff\xff' and p[2] in range(1,6)
                  and p[3:5]==bytes((4,2)) and sum(p[2:])&255==255)
  return self.port.write(data)
 def flush(self):
  if self.last_read:self.read_drains_skipped+=1;return
  return self.port.flush()
