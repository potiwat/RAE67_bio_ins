"""Check the one-line logging correction against native Jazzy std_msgs and CDR."""
from pathlib import Path
import sys,hashlib,json
from std_msgs.msg import Float32MultiArray,MultiArrayDimension
from rclpy.serialization import serialize_message,deserialize_message

workspace=Path(sys.argv[1]).resolve()
msg=Float32MultiArray()
msg.data=[.27,.17,-.21]
dim=MultiArrayDimension();dim.label="tilt_extend_nod_rad";dim.size=3;dim.stride=3
msg.layout.dim=[dim];msg.layout.data_offset=0
before=serialize_message(msg)
try:json.dumps({"data":msg.data})
except TypeError as exc:initial_error=str(exc)
else:raise AssertionError("The upstream trace error was not reproduced")
payload=json.loads(json.dumps({"data":list(msg.data)}))
after=serialize_message(msg)
wire=deserialize_message(after,Float32MultiArray)
assert before==after and msg==wire and payload["data"]==list(wire.data)
policy=hashlib.sha256((workspace/"completed_policy.py").read_bytes()).hexdigest()
meta=dict(message_type="std_msgs/msg/Float32MultiArray",python_data_type=str(type(msg.data)),
    unmodified_logger_error=initial_error,wire_bytes_before_sha256=hashlib.sha256(before).hexdigest(),
    wire_bytes_after_sha256=hashlib.sha256(after).hexdigest(),cdr_bytes=len(before),round_trip_equal=msg==wire,
    decoded_servo=list(wire.data),layout_label=wire.layout.dim[0].label,layout_size=wire.layout.dim[0].size,
    layout_stride=wire.layout.dim[0].stride,policy_sha256=policy)
(workspace/"session/wire_check.json").write_text(json.dumps(meta,indent=2)+"\n")
