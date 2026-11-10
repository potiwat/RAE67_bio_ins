"""Run with sourced Jazzy; no hardware. Covers actual ROS wire conversion."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
from .ros13_record import rows


class FileTests(unittest.TestCase):
    def test_partial_final_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'trace.jsonl').write_text('{"time_s":0}')
            with self.assertRaisesRegex(ValueError,'partial final'):list(rows(p,False,1.))

    def test_oversized_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'trace.jsonl').write_text('x'*65537+'\n')
            with self.assertRaisesRegex(ValueError,'size/line'):list(rows(p,False,1.))


@unittest.skipUnless(importlib.util.find_spec('rclpy'),'requires sourced ROS Jazzy')
class WireTests(unittest.TestCase):
    def test_all13_ros_messages_roundtrip_to_canonical_fields(self):
        from rosidl_runtime_py.utilities import get_message
        from rclpy.serialization import serialize_message,deserialize_message
        from .ros13 import Encoder,TOPICS
        from .ros13_record import message_for,canonical_message
        from .test_ros13 import fixture
        row,meta=fixture();classes={t:get_message(kind) for t,kind in TOPICS.items()}
        for packet in Encoder(meta).encode(row,0):
            t=packet['topic'];msg=message_for(packet,classes)
            decoded=deserialize_message(serialize_message(msg),classes[t])
            # Exercise canonical JSON including octet level and array fields.
            self.assertIsInstance(json.loads(canonical_message(decoded)),dict)
        self.assertEqual(len(classes),13)


if __name__=='__main__':unittest.main()
