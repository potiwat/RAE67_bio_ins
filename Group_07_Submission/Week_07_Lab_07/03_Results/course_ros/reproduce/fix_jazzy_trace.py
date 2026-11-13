"""Apply the verified trace-only compatibility change to a fresh course package copy."""
import argparse
from pathlib import Path
from hashlib import sha256
import difflib
import json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("package",type=Path,help="private copy of the pinned lab_07 package")
parser.add_argument("--record",type=Path,help="optional directory for diff and hash receipt")
args=parser.parse_args()
path=args.package/"lamp_week07/ros_nodes.py"
old=path.read_bytes()
oldhash=sha256(old).hexdigest()
pin=json.loads((Path(__file__).resolve().parent/"source_provenance.json").read_bytes())
assert oldhash==pin["files"]["lamp_week07/ros_nodes.py"]["sha256"],"Requires the original pinned source bytes"
before=b"('servo_command',servo,servo.data)"
after=b"('servo_command',servo,list(servo.data))"
assert old.count(before)==1
new=old.replace(before,after)
path.write_bytes(new)
if args.record:
    args.record.mkdir(exist_ok=True,parents=True)
    diff="".join(difflib.unified_diff(old.decode().splitlines(keepends=True),new.decode().splitlines(keepends=True),
                    fromfile="a/lamp_week07/ros_nodes.py",tofile="b/lamp_week07/ros_nodes.py"))
    (args.record/"jazzy_trace.patch").write_text(diff,encoding="utf-8",newline="\n")
    (args.record/"source_change.json").write_text(json.dumps(dict(scope="JSON trace copy only",original_sha256=oldhash,
        executed_sha256=sha256(new).hexdigest(), replacements=1),indent=2)+"\n",encoding="utf-8")
print(f"CSV adapter {oldhash} -> {sha256(new).hexdigest()}")
