"""Receive STS unicast WRITE status before any follow-up READ.

No transmit function: existing guarded bus remains the only write gateway.
Protocol reference: Waveshare Servo Communication Protocol, WRITE DATA response.
"""
import time


def receive_write_ack(port,sid,request,timeout=.3):
    end=time.monotonic()+timeout;buffer=bytearray()
    while time.monotonic()<end:
        buffer.extend(port.read(port.in_waiting or 1))
        while len(buffer)>=4:
            start=buffer.find(b'\xff\xff')
            if start<0:
                buffer[:]=buffer[-1:];break
            if start:del buffer[:start]
            if len(buffer)<4:break
            length=buffer[3]
            if not 2<=length<=80:
                del buffer[0];continue
            if len(buffer)<length+4:break
            frame=bytes(buffer[:length+4]);del buffer[:length+4]
            if frame==request:continue
            if frame[2]!=sid or length!=2 or sum(frame[2:])&255!=255:continue
            if frame[4]:raise RuntimeError(f'ID{sid} WRITE status={frame[4]}')
            return
    raise TimeoutError(f'ID{sid} WRITE address {request[5]}: acknowledgement missing/corrupt')
