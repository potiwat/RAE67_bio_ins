import sys
import unittest
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from write_ack import receive_write_ack

REQUEST=bytes.fromhex('ffff0105032ae307e2')


class ReceivePort:
    def __init__(self,chunks):self.chunks=deque(bytearray(c) for c in chunks)
    @property
    def in_waiting(self):return len(self.chunks[0]) if self.chunks else 0
    def read(self,n):
        if not self.chunks:return b''
        part=bytes(self.chunks[0][:n]);del self.chunks[0][:n]
        if not self.chunks[0]:self.chunks.popleft()
        return part


class WriteAckTests(unittest.TestCase):
    def test_consumes_complete_success_reply_before_next_transaction(self):
        port=ReceivePort([bytes.fromhex('ffff010200fc')])
        receive_write_ack(port,1,REQUEST,.002)
        self.assertEqual(port.in_waiting,0)
    def test_fragmented_write_echo_is_not_mistaken_for_status(self):
        port=ReceivePort([REQUEST[:3],REQUEST[3:],b'\xff',b'\xff\x01\x02',b'\x00\xfc'])
        receive_write_ack(port,1,REQUEST,.002)
        self.assertEqual(port.in_waiting,0)
    def test_wrong_id_and_bad_checksum_cannot_acknowledge_write(self):
        for response in ['ffff020200fb','ffff01020000']:
            with self.subTest(response=response),self.assertRaises(TimeoutError):
                receive_write_ack(ReceivePort([bytes.fromhex(response)]),1,REQUEST,.001)
    def test_servo_status_error_is_not_retried_or_ignored(self):
        with self.assertRaisesRegex(RuntimeError,'status=32'):
            receive_write_ack(ReceivePort([bytes.fromhex('ffff010220dc')]),1,REQUEST,.002)
    def test_missing_ack_is_not_reported_as_write_success(self):
        with self.assertRaises(TimeoutError):receive_write_ack(ReceivePort([]),1,REQUEST,.001)


if __name__=='__main__':unittest.main()
